import pytest
import time
from datetime import datetime, timedelta, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from relay.db.session import Base
from relay.models.entities import (
    Tenant, User, Membership, UserRole, CustomerAccount, Document, DocumentVersion,
    Ticket, Proposal, ProposalStatus, Approval, ActionReceipt, ActionType, TicketStatus, Job, JobStatus
)
from relay.worker.durable_worker import DurableWorker
from relay.sandbox.provider import sandbox_provider
from relay.core.security import compute_args_hash, hash_password

TEST_DB_URL = "sqlite:///:memory:"

@pytest.fixture(scope="function")
def session():
    engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = TestingSessionLocal()

    tenant = Tenant(id="ten_test", name="Test Corp", slug="testcorp")
    db.add(tenant)
    user = User(id="usr_admin", email="admin@test.com", full_name="Admin", hashed_password=hash_password("pw"))
    db.add(user)
    db.flush()

    db.add(Membership(tenant_id=tenant.id, user_id=user.id, role=UserRole.ADMIN))

    doc = Document(id="doc_refund", tenant_id=tenant.id, title="Refund Policy", category="policy", current_version=1)
    db.add(doc)
    db.flush()
    ver = DocumentVersion(document_id=doc.id, version=1, content="Refunds eligible within 14 days.")
    db.add(ver)

    acc = CustomerAccount(
        tenant_id=tenant.id,
        customer_email="alice@customer.com",
        customer_name="Alice Customer",
        plan_tier="standard",
        subscription_status="active",
        monthly_rate_cents=2900,
        days_since_billing=5
    )
    db.add(acc)
    db.commit()
    yield db
    db.close()

def test_approval_invalidation_on_proposal_edit(session):
    # Setup approved proposal
    ticket = Ticket(
        tenant_id="ten_test",
        external_ticket_id="TKT-INV-1",
        customer_email="alice@customer.com",
        customer_name="Alice",
        subject="Refund please",
        body="Refund me $29",
        status=TicketStatus.APPROVED
    )
    session.add(ticket)
    session.flush()

    orig_args = {"amount_cents": 2900}
    orig_hash = compute_args_hash(orig_args)
    proposal = Proposal(
        tenant_id="ten_test",
        ticket_id=ticket.id,
        version=1,
        action_type=ActionType.REFUND,
        action_arguments=orig_args,
        args_hash=orig_hash,
        explanation="Approved refund",
        status=ProposalStatus.APPROVED
    )
    session.add(proposal)
    session.flush()

    approval = Approval(
        tenant_id="ten_test",
        proposal_id=proposal.id,
        proposal_version=1,
        args_hash=orig_hash,
        is_approved=True
    )
    session.add(approval)
    session.commit()

    # Now tamper/edit proposal args without renewing approval
    proposal.action_arguments = {"amount_cents": 99999} # maliciously increased

    exec_job = Job(
        tenant_id="ten_test",
        ticket_id=ticket.id,
        job_type="execute_sandbox_action",
        status=JobStatus.PENDING,
        idempotency_key="job_exec_tamper_test",
        payload={"proposal_id": proposal.id}
    )
    session.add(exec_job)
    session.commit()

    worker = DurableWorker(session, worker_id="wrk_sec")
    job = worker.claim_next_job()
    assert job is not None
    # Worker execution should fail and reset ticket to awaiting_review
    res = worker.execute_job(job.id)
    assert res is False
    session.refresh(ticket)
    assert ticket.status == TicketStatus.AWAITING_REVIEW

def test_underwriting_policy_change_invalidates_execution(session):
    ticket = Ticket(
        tenant_id="ten_test",
        external_ticket_id="TKT-POL-1",
        customer_email="alice@customer.com",
        customer_name="Alice",
        subject="Refund",
        body="Refund $29",
        status=TicketStatus.APPROVED
    )
    session.add(ticket)
    session.flush()

    args = {"amount_cents": 2900}
    args_hash = compute_args_hash(args)
    proposal = Proposal(
        tenant_id="ten_test",
        ticket_id=ticket.id,
        version=1,
        action_type=ActionType.REFUND,
        action_arguments=args,
        args_hash=args_hash,
        explanation="Refund under policy",
        policy_version_snapshot={"doc_refund": 1},
        status=ProposalStatus.APPROVED
    )
    session.add(proposal)
    session.flush()

    approval = Approval(
        tenant_id="ten_test",
        proposal_id=proposal.id,
        proposal_version=1,
        args_hash=args_hash,
        is_approved=True
    )
    session.add(approval)

    # Admin updates policy version to v2 before worker runs
    doc = session.query(Document).filter(Document.id == "doc_refund").first()
    doc.current_version = 2
    session.commit()

    exec_job = Job(
        tenant_id="ten_test",
        ticket_id=ticket.id,
        job_type="execute_sandbox_action",
        status=JobStatus.PENDING,
        idempotency_key="job_exec_pol_test",
        payload={"proposal_id": proposal.id}
    )
    session.add(exec_job)
    session.commit()

    worker = DurableWorker(session, worker_id="wrk_pol")
    job = worker.claim_next_job()
    assert job is not None
    res = worker.execute_job(job.id)
    assert res is False
    session.refresh(ticket)
    assert ticket.status == TicketStatus.AWAITING_REVIEW

def test_provider_timeout_post_commit_and_reconciliation(session):
    ticket = Ticket(
        tenant_id="ten_test",
        external_ticket_id="TKT-REC-1",
        customer_email="alice@customer.com",
        customer_name="Alice",
        subject="Cancel plan",
        body="Cancel please",
        status=TicketStatus.APPROVED
    )
    session.add(ticket)
    session.flush()

    args = {"customer_email": "alice@customer.com"}
    args_hash = compute_args_hash(args)
    proposal = Proposal(
        tenant_id="ten_test",
        ticket_id=ticket.id,
        version=1,
        action_type=ActionType.CANCEL_SUBSCRIPTION,
        action_arguments=args,
        args_hash=args_hash,
        explanation="Cancel plan",
        policy_version_snapshot={},
        status=ProposalStatus.APPROVED
    )
    session.add(proposal)
    session.flush()

    approval = Approval(
        tenant_id="ten_test",
        proposal_id=proposal.id,
        proposal_version=1,
        args_hash=args_hash,
        is_approved=True
    )
    session.add(approval)

    exec_job = Job(
        tenant_id="ten_test",
        ticket_id=ticket.id,
        job_type="execute_sandbox_action",
        status=JobStatus.PENDING,
        idempotency_key="idemp_timeout_test_key_001",
        payload={"proposal_id": proposal.id, "simulation_mode": "timeout_post_commit"}
    )
    session.add(exec_job)
    session.commit()

    worker = DurableWorker(session, worker_id="wrk_rec")
    job = worker.claim_next_job()
    assert worker.execute_job(job.id) is True

    # Check ticket entered NEEDS_RECONCILIATION
    session.refresh(ticket)
    assert ticket.status == TicketStatus.NEEDS_RECONCILIATION

    # Trigger Reconciliation Job
    reconcile_job = Job(
        tenant_id="ten_test",
        ticket_id=ticket.id,
        job_type="reconcile_action",
        status=JobStatus.PENDING,
        idempotency_key="job_reconcile_001",
        payload={"target_idempotency_key": "idemp_timeout_test_key_001"}
    )
    session.add(reconcile_job)
    session.commit()

    rec_claim = worker.claim_next_job()
    assert worker.execute_job(rec_claim.id) is True

    # Verified succeeded after reconciliation
    session.refresh(ticket)
    assert ticket.status == TicketStatus.SUCCEEDED

def test_account_state_change_invalidates_execution(session):
    ticket = Ticket(
        tenant_id="ten_test",
        external_ticket_id="TKT-ACC-1",
        customer_email="alice@customer.com",
        customer_name="Alice",
        subject="Cancel plan",
        body="Cancel plan",
        status=TicketStatus.APPROVED
    )
    session.add(ticket)
    session.flush()

    args = {"customer_email": "alice@customer.com"}
    args_hash = compute_args_hash(args)
    proposal = Proposal(
        tenant_id="ten_test",
        ticket_id=ticket.id,
        version=1,
        action_type=ActionType.CANCEL_SUBSCRIPTION,
        action_arguments=args,
        args_hash=args_hash,
        explanation="Cancel plan",
        account_state_snapshot={"acc_alice": {"subscription_status": "active", "plan_tier": "standard"}},
        status=ProposalStatus.APPROVED
    )
    session.add(proposal)
    session.flush()

    approval = Approval(
        tenant_id="ten_test",
        proposal_id=proposal.id,
        proposal_version=1,
        args_hash=args_hash,
        is_approved=True
    )
    session.add(approval)

    # Customer account is modified out-of-band before worker execution
    acc = session.query(CustomerAccount).filter(CustomerAccount.customer_email == "alice@customer.com").first()
    proposal.account_state_snapshot = {acc.id: {"subscription_status": "active", "plan_tier": "standard"}}
    acc.subscription_status = "canceled"
    session.commit()

    exec_job = Job(
        tenant_id="ten_test",
        ticket_id=ticket.id,
        job_type="execute_sandbox_action",
        status=JobStatus.PENDING,
        idempotency_key="job_exec_acc_test",
        payload={"proposal_id": proposal.id}
    )
    session.add(exec_job)
    session.commit()

    worker = DurableWorker(session, worker_id="wrk_acc")
    job = worker.claim_next_job()
    assert job is not None
    res = worker.execute_job(job.id)
    assert res is False
    session.refresh(ticket)
    assert ticket.status == TicketStatus.AWAITING_REVIEW

