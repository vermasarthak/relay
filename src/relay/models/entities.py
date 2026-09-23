from datetime import datetime, timezone
import uuid
import enum
from sqlalchemy import (
    Column, String, Text, Integer, Float, Boolean, DateTime, ForeignKey, 
    Enum, JSON, Index, UniqueConstraint
)
from sqlalchemy.orm import relationship
from relay.core.clock import get_clock
from relay.db.session import Base

def utc_now():
    return get_clock().now()

def gen_id(prefix=""):
    return f"{prefix}{uuid.uuid4().hex[:16]}"

class UserRole(str, enum.Enum):
    ADMIN = "admin"
    REVIEWER = "reviewer"
    MEMBER = "member"

class TicketStatus(str, enum.Enum):
    RECEIVED = "received"
    ANALYZING = "analyzing"
    AWAITING_REVIEW = "awaiting_review"
    APPROVED = "approved"
    EXECUTING = "executing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    NEEDS_RECONCILIATION = "needs_reconciliation"
    REJECTED = "rejected"
    ABSTAINED = "abstained"

class ActionType(str, enum.Enum):
    DRAFT_REPLY = "draft_reply"
    CANCEL_SUBSCRIPTION = "cancel_subscription"
    REFUND = "refund"
    ABSTAIN = "abstain"

class ProposalStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"

class JobStatus(str, enum.Enum):
    PENDING = "pending"
    LEASED = "leased"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRY_SCHEDULED = "retry_scheduled"

class Tenant(Base):
    __tablename__ = "tenants"

    id = Column(String(64), primary_key=True, default=lambda: gen_id("ten_"))
    name = Column(String(128), nullable=False)
    slug = Column(String(64), unique=True, nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    users = relationship("Membership", back_populates="tenant", cascade="all, delete-orphan")
    tickets = relationship("Ticket", back_populates="tenant", cascade="all, delete-orphan")
    documents = relationship("Document", back_populates="tenant", cascade="all, delete-orphan")
    accounts = relationship("CustomerAccount", back_populates="tenant", cascade="all, delete-orphan")

class User(Base):
    __tablename__ = "users"

    id = Column(String(64), primary_key=True, default=lambda: gen_id("usr_"))
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(128), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    memberships = relationship("Membership", back_populates="user", cascade="all, delete-orphan")

class Membership(Base):
    __tablename__ = "memberships"

    id = Column(String(64), primary_key=True, default=lambda: gen_id("mem_"))
    tenant_id = Column(String(64), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(64), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(Enum(UserRole), default=UserRole.MEMBER, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    tenant = relationship("Tenant", back_populates="users")
    user = relationship("User", back_populates="memberships")

    __table_args__ = (UniqueConstraint("tenant_id", "user_id", name="uq_tenant_user"),)

class CustomerAccount(Base):
    __tablename__ = "customer_accounts"

    id = Column(String(64), primary_key=True, default=lambda: gen_id("acc_"))
    tenant_id = Column(String(64), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    customer_email = Column(String(255), nullable=False, index=True)
    customer_name = Column(String(128), nullable=False)
    plan_tier = Column(String(64), default="standard", nullable=False) # e.g., pro, enterprise
    subscription_status = Column(String(64), default="active", nullable=False) # active, past_due, canceled
    monthly_rate_cents = Column(Integer, default=2900, nullable=False)
    days_since_billing = Column(Integer, default=5, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    tenant = relationship("Tenant", back_populates="accounts")
    __table_args__ = (UniqueConstraint("tenant_id", "customer_email", name="uq_tenant_customer_email"),)

class Document(Base):
    __tablename__ = "documents"

    id = Column(String(64), primary_key=True, default=lambda: gen_id("doc_"))
    tenant_id = Column(String(64), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    category = Column(String(64), nullable=False) # policy, faq, runbook
    current_version = Column(Integer, default=1, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    tenant = relationship("Tenant", back_populates="documents")
    versions = relationship("DocumentVersion", back_populates="document", cascade="all, delete-orphan")

class DocumentVersion(Base):
    __tablename__ = "document_versions"

    id = Column(String(64), primary_key=True, default=lambda: gen_id("dver_"))
    document_id = Column(String(64), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    version = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    summary = Column(String(512), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    document = relationship("Document", back_populates="versions")
    __table_args__ = (UniqueConstraint("document_id", "version", name="uq_doc_version"),)

class Ticket(Base):
    __tablename__ = "tickets"

    id = Column(String(64), primary_key=True, default=lambda: gen_id("tkt_"))
    tenant_id = Column(String(64), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    external_ticket_id = Column(String(128), nullable=False) # Customer reference
    customer_email = Column(String(255), nullable=False, index=True)
    customer_name = Column(String(128), nullable=False)
    subject = Column(String(255), nullable=False)
    body = Column(Text, nullable=False)
    category = Column(String(64), default="general", nullable=False)
    status = Column(Enum(TicketStatus), default=TicketStatus.RECEIVED, nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    tenant = relationship("Tenant", back_populates="tickets")
    proposals = relationship("Proposal", back_populates="ticket", cascade="all, delete-orphan")
    jobs = relationship("Job", back_populates="ticket", cascade="all, delete-orphan")
    events = relationship("AuditEvent", back_populates="ticket", cascade="all, delete-orphan")

    __table_args__ = (UniqueConstraint("tenant_id", "external_ticket_id", name="uq_tenant_external_ticket"),)

class EvidenceReference(Base):
    __tablename__ = "evidence_references"

    id = Column(String(64), primary_key=True, default=lambda: gen_id("evi_"))
    tenant_id = Column(String(64), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    ticket_id = Column(String(64), ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False, index=True)
    source_type = Column(String(32), nullable=False) # policy_doc, customer_account, system_rule
    source_id = Column(String(64), nullable=False) # doc_ver ID or account ID
    source_title = Column(String(255), nullable=False)
    excerpt = Column(Text, nullable=False)
    relevance_score = Column(Float, default=1.0, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

class Proposal(Base):
    __tablename__ = "proposals"

    id = Column(String(64), primary_key=True, default=lambda: gen_id("prop_"))
    tenant_id = Column(String(64), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    ticket_id = Column(String(64), ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False, index=True)
    version = Column(Integer, default=1, nullable=False)
    action_type = Column(Enum(ActionType), nullable=False)
    action_arguments = Column(JSON, nullable=False) # validated JSON e.g. {"amount_cents": 2900, "reason": "in_policy"}
    args_hash = Column(String(64), nullable=False) # SHA256 of canonical action_arguments
    explanation = Column(Text, nullable=False)
    missing_information = Column(Text, nullable=True)
    cited_evidence_ids = Column(JSON, default=list, nullable=False) # List of EvidenceReference IDs
    policy_version_snapshot = Column(JSON, default=dict, nullable=False) # Mapping of doc_id -> version
    account_state_snapshot = Column(JSON, default=dict, nullable=False) # Mapping of account_id -> {status, plan, rate}
    status = Column(Enum(ProposalStatus), default=ProposalStatus.PENDING, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    created_by = Column(String(64), default="relay_ai_pipeline", nullable=False)

    ticket = relationship("Ticket", back_populates="proposals")
    approval = relationship("Approval", back_populates="proposal", uselist=False, cascade="all, delete-orphan")

class Approval(Base):
    __tablename__ = "approvals"

    id = Column(String(64), primary_key=True, default=lambda: gen_id("appr_"))
    tenant_id = Column(String(64), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    proposal_id = Column(String(64), ForeignKey("proposals.id", ondelete="CASCADE"), nullable=False, unique=True)
    proposal_version = Column(Integer, nullable=False)
    args_hash = Column(String(64), nullable=False)
    decided_by_user_id = Column(String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    is_approved = Column(Boolean, nullable=False)
    rejection_reason = Column(Text, nullable=True)
    reviewer_notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    proposal = relationship("Proposal", back_populates="approval")
    user = relationship("User")

class Job(Base):
    __tablename__ = "jobs"

    id = Column(String(64), primary_key=True, default=lambda: gen_id("job_"))
    tenant_id = Column(String(64), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    ticket_id = Column(String(64), ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False, index=True)
    job_type = Column(String(64), nullable=False) # analyze_ticket, execute_sandbox_action, reconcile_action
    status = Column(Enum(JobStatus), default=JobStatus.PENDING, nullable=False, index=True)
    payload = Column(JSON, default=dict, nullable=False)
    
    # Durable leasing fields
    fencing_token = Column(Integer, default=0, nullable=False)
    worker_id = Column(String(64), nullable=True)
    leased_until = Column(DateTime(timezone=True), nullable=True, index=True)
    attempt_count = Column(Integer, default=0, nullable=False)
    max_attempts = Column(Integer, default=5, nullable=False)
    next_attempt_at = Column(DateTime(timezone=True), default=utc_now, nullable=False, index=True)
    idempotency_key = Column(String(128), unique=True, nullable=False, index=True)
    
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    ticket = relationship("Ticket", back_populates="jobs")
    receipts = relationship("ActionReceipt", back_populates="job", cascade="all, delete-orphan")
    attempts = relationship("JobAttempt", back_populates="job", cascade="all, delete-orphan")

class JobAttempt(Base):
    __tablename__ = "job_attempts"

    id = Column(String(64), primary_key=True, default=lambda: gen_id("att_"))
    job_id = Column(String(64), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    attempt_number = Column(Integer, nullable=False)
    worker_id = Column(String(64), nullable=False)
    fencing_token = Column(Integer, nullable=False)
    status = Column(String(32), nullable=False) # success, failed, timeout
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    job = relationship("Job", back_populates="attempts")

class ActionReceipt(Base):
    __tablename__ = "action_receipts"

    id = Column(String(64), primary_key=True, default=lambda: gen_id("rcpt_"))
    tenant_id = Column(String(64), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    job_id = Column(String(64), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    action_type = Column(Enum(ActionType), nullable=False)
    idempotency_key = Column(String(128), nullable=False, index=True)
    provider = Column(String(64), default="relay_local_sandbox", nullable=False)
    provider_transaction_id = Column(String(128), nullable=True)
    status = Column(String(32), nullable=False) # succeeded, rejected, timeout, reconciled
    request_payload = Column(JSON, nullable=False)
    response_payload = Column(JSON, nullable=False)
    verified = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    job = relationship("Job", back_populates="receipts")

class AuditEvent(Base):
    __tablename__ = "audit_events"

    id = Column(String(64), primary_key=True, default=lambda: gen_id("evt_"))
    tenant_id = Column(String(64), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    ticket_id = Column(String(64), ForeignKey("tickets.id", ondelete="CASCADE"), nullable=True, index=True)
    event_type = Column(String(64), nullable=False) # ticket_ingested, proposal_generated, proposal_approved, action_executed, reconciliation_triggered
    actor = Column(String(128), nullable=False) # user ID, worker ID, or system
    correlation_id = Column(String(64), nullable=False, index=True)
    details = Column(JSON, default=dict, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    ticket = relationship("Ticket", back_populates="events")
