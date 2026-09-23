import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from relay.api.main import app
from relay.db.session import Base, get_db
from relay.models.entities import (
    Tenant, User, Membership, UserRole, CustomerAccount, Document, DocumentVersion,
    Ticket, Proposal, Approval, ActionType, TicketStatus
)
from relay.core.security import hash_password
from relay.worker.durable_worker import DurableWorker

from sqlalchemy.pool import StaticPool

TEST_DB_URL = "sqlite:///:memory:"

@pytest.fixture(scope="function")
def db_session():
    engine = create_engine(
        TEST_DB_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()

    # Seed minimal fixture
    ten_a = Tenant(id="ten_a", name="Tenant A", slug="ten_a")
    ten_b = Tenant(id="ten_b", name="Tenant B", slug="ten_b")
    session.add_all([ten_a, ten_b])
    
    usr_a = User(id="usr_a", email="alice@a.com", full_name="Alice A", hashed_password=hash_password("pw123"))
    usr_b = User(id="usr_b", email="bob@b.com", full_name="Bob B", hashed_password=hash_password("pw123"))
    session.add_all([usr_a, usr_b])
    session.flush()

    session.add_all([
        Membership(tenant_id=ten_a.id, user_id=usr_a.id, role=UserRole.ADMIN),
        Membership(tenant_id=ten_b.id, user_id=usr_b.id, role=UserRole.ADMIN)
    ])

    doc_a = Document(id="doc_a1", tenant_id=ten_a.id, title="Refund Policy", category="policy", current_version=1)
    session.add(doc_a)
    session.flush()
    ver_a = DocumentVersion(document_id=doc_a.id, version=1, content="Refunds allowed within 14 days of billing.")
    session.add(ver_a)

    acc_a = CustomerAccount(
        tenant_id=ten_a.id,
        customer_email="cust@a.com",
        customer_name="Customer One",
        plan_tier="pro",
        subscription_status="active",
        monthly_rate_cents=2900,
        days_since_billing=3
    )
    session.add(acc_a)
    session.commit()

    yield session
    session.close()

@pytest.fixture(scope="function")
def client(db_session):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()

def test_multi_tenant_isolation_and_cross_tenant_rejection(client, db_session):
    # 1. Login Alice (Tenant A)
    res_a = client.post("/api/v1/auth/login", json={"email": "alice@a.com", "password": "pw123"})
    assert res_a.status_code == 200
    token_a = res_a.json()["access_token"]

    # 2. Ingest Ticket in Tenant A
    headers_a = {"Authorization": f"Bearer {token_a}", "x-tenant-id": "ten_a"}
    tkt_payload = {
        "external_ticket_id": "TKT-100",
        "customer_email": "cust@a.com",
        "customer_name": "Customer One",
        "subject": "Please cancel my subscription",
        "body": "I would like to cancel my plan immediately."
    }
    tkt_res = client.post("/api/v1/tickets", headers=headers_a, json=tkt_payload)
    assert tkt_res.status_code == 200
    tkt_id = tkt_res.json()["id"]

    # 3. Attempt cross-tenant access using Bob's credentials (Tenant B) to fetch Alice's ticket
    res_b = client.post("/api/v1/auth/login", json={"email": "bob@b.com", "password": "pw123"})
    token_b = res_b.json()["access_token"]
    
    # Bob tries with his tenant -> 404
    headers_b = {"Authorization": f"Bearer {token_b}", "x-tenant-id": "ten_b"}
    cross_res = client.get(f"/api/v1/tickets/{tkt_id}/resolution", headers=headers_b)
    assert cross_res.status_code == 404

    # Bob tries to forge Alice's tenant header -> 403 Forbidden
    headers_forged = {"Authorization": f"Bearer {token_b}", "x-tenant-id": "ten_a"}
    forbidden_res = client.get(f"/api/v1/tickets/{tkt_id}/resolution", headers=headers_forged)
    assert forbidden_res.status_code == 403

def test_full_resolution_workflow(client, db_session):
    # 1. Login Alice
    res = client.post("/api/v1/auth/login", json={"email": "alice@a.com", "password": "pw123"})
    token = res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}", "x-tenant-id": "ten_a"}

    # 2. Ingest Ticket
    tkt_res = client.post("/api/v1/tickets", headers=headers, json={
        "external_ticket_id": "TKT-101",
        "customer_email": "cust@a.com",
        "customer_name": "Customer One",
        "subject": "Cancel subscription",
        "body": "Please cancel my subscription."
    })
    tkt_id = tkt_res.json()["id"]

    # 3. Run Durable Worker to analyze ticket
    worker = DurableWorker(db_session, worker_id="test_worker")
    job = worker.claim_next_job()
    assert job is not None
    assert job.job_type == "analyze_ticket"
    assert worker.execute_job(job.id) is True

    # 4. Fetch Resolution Detail & Verify Proposal
    res_detail = client.get(f"/api/v1/tickets/{tkt_id}/resolution", headers=headers)
    assert res_detail.status_code == 200
    data = res_detail.json()
    assert len(data["evidence"]) >= 1
    assert data["active_proposal"] is not None
    assert data["active_proposal"]["action_type"] == "cancel_subscription"
    prop_id = data["active_proposal"]["id"]

    # 5. Approve Proposal
    decide_res = client.post(
        f"/api/v1/tickets/{tkt_id}/proposals/{prop_id}/decide",
        headers=headers,
        json={"is_approved": True, "reviewer_notes": "Verified customer intent."}
    )
    assert decide_res.status_code == 200
    assert decide_res.json()["ticket_status"] == "approved"

    # 6. Run Worker for Sandbox Execution Job
    exec_job = worker.claim_next_job()
    assert exec_job is not None
    assert exec_job.job_type == "execute_sandbox_action"
    assert worker.execute_job(exec_job.id) is True

    # 7. Verify Final Execution Receipt
    final_detail = client.get(f"/api/v1/tickets/{tkt_id}/resolution", headers=headers).json()
    assert final_detail["ticket"]["status"] == "succeeded"
    assert len(final_detail["receipts"]) == 1
    assert final_detail["receipts"][0]["verified"] is True
    assert final_detail["receipts"][0]["status"] == "succeeded"
