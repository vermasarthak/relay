from fastapi import FastAPI, Depends, HTTPException, Header, Response, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
import uuid

from relay.core.config import settings
from relay.db.session import get_db, Base, engine
from relay.models.entities import (
    Tenant, User, Membership, Ticket, TicketStatus, Document, DocumentVersion,
    EvidenceReference, Proposal, ProposalStatus, Approval, Job, JobStatus,
    ActionReceipt, AuditEvent, ActionType
)
from relay.schemas.dto import (
    UserLoginRequest, UserResponse, TenantResponse, TicketCreateRequest,
    TicketResponse, ProposalResponse, ProposalEditRequest, ApprovalDecisionRequest,
    ResolutionDetailResponse, EvidenceItemResponse, ActionReceiptResponse
)
from relay.core.security import (
    hash_password, verify_password, create_session_token,
    get_current_user_and_tenant, AuthenticatedContext, compute_args_hash
)

# Auto-create tables for local testing
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Relay API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- HEALTH, READINESS & METRICS ---

@app.get("/healthz")
def health_check():
    return {"status": "ok", "service": "relay_api", "timestamp": settings.app_env}

@app.get("/ready")
def readiness_check(db: Session = Depends(get_db)):
    try:
        # Check database connectivity
        db.execute(Base.metadata.tables["tenants"].select().limit(1))
        return {"status": "ready", "database": "connected"}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Database not ready: {str(e)}")

@app.get("/api/v1/metrics")
def get_operational_metrics(
    ctx: AuthenticatedContext = Depends(get_current_user_and_tenant),
    db: Session = Depends(get_db)
):
    """Real-time operational queue and reconciliation backlog metrics."""
    total_tickets = db.query(Ticket).filter(Ticket.tenant_id == ctx.tenant.id).count()
    awaiting_review = db.query(Ticket).filter(
        Ticket.tenant_id == ctx.tenant.id,
        Ticket.status == TicketStatus.AWAITING_REVIEW
    ).count()
    reconciliation_backlog = db.query(Ticket).filter(
        Ticket.tenant_id == ctx.tenant.id,
        Ticket.status == TicketStatus.NEEDS_RECONCILIATION
    ).count()
    pending_jobs = db.query(Job).filter(
        Job.tenant_id == ctx.tenant.id,
        Job.status == JobStatus.PENDING
    ).count()
    failed_jobs = db.query(Job).filter(
        Job.tenant_id == ctx.tenant.id,
        Job.status == JobStatus.FAILED
    ).count()

    return {
        "tenant_id": ctx.tenant.id,
        "total_tickets": total_tickets,
        "awaiting_review": awaiting_review,
        "reconciliation_backlog": reconciliation_backlog,
        "pending_jobs": pending_jobs,
        "failed_jobs": failed_jobs
    }

# --- AUTH ROUTES ---

@app.post("/api/v1/auth/login")
def login(req: UserLoginRequest, response: Response, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == req.email, User.is_active == True).first()
    if not user or not verify_password(req.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    memberships = db.query(Membership).filter(Membership.user_id == user.id).all()
    tenant_ids = [m.tenant_id for m in memberships]

    token = create_session_token(user.id, user.email, tenant_ids)

    # Set secure HttpOnly cookie
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        httponly=True,
        secure=settings.app_env == "production",
        samesite="lax",
        max_age=settings.session_expire_hours * 3600
    )

    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "email": user.email,
            "full_name": user.full_name,
            "tenants": [
                {"tenant_id": m.tenant.id, "name": m.tenant.name, "role": m.role.value}
                for m in memberships
            ]
        }
    }

@app.get("/api/v1/auth/me")
def get_me(ctx: AuthenticatedContext = Depends(get_current_user_and_tenant)):
    return {
        "user_id": ctx.user.id,
        "email": ctx.user.email,
        "full_name": ctx.user.full_name,
        "active_tenant": {
            "id": ctx.tenant.id,
            "name": ctx.tenant.name,
            "role": ctx.role
        }
    }

# --- TICKET ROUTES ---

@app.post("/api/v1/tickets", response_model=TicketResponse)
def ingest_ticket(
    req: TicketCreateRequest,
    ctx: AuthenticatedContext = Depends(get_current_user_and_tenant),
    db: Session = Depends(get_db)
):
    # Idempotent Ingestion Check
    existing = db.query(Ticket).filter(
        Ticket.tenant_id == ctx.tenant.id,
        Ticket.external_ticket_id == req.external_ticket_id
    ).first()

    if existing:
        return existing

    ticket = Ticket(
        tenant_id=ctx.tenant.id,
        external_ticket_id=req.external_ticket_id,
        customer_email=req.customer_email,
        customer_name=req.customer_name,
        subject=req.subject,
        body=req.body,
        category=req.category or "general",
        status=TicketStatus.RECEIVED
    )
    db.add(ticket)
    db.flush()

    # Enqueue Analysis Job
    idempotency_key = f"job_analyze_{ticket.id}"
    job = Job(
        tenant_id=ctx.tenant.id,
        ticket_id=ticket.id,
        job_type="analyze_ticket",
        status=JobStatus.PENDING,
        idempotency_key=idempotency_key,
        payload={"ticket_id": ticket.id}
    )
    db.add(job)

    # Audit event
    event = AuditEvent(
        tenant_id=ctx.tenant.id,
        ticket_id=ticket.id,
        event_type="ticket_ingested",
        actor=ctx.user.id,
        correlation_id=ticket.id,
        details={"external_id": req.external_ticket_id, "customer_email": req.customer_email}
    )
    db.add(event)

    db.commit()
    db.refresh(ticket)
    return ticket

@app.get("/api/v1/tickets", response_model=List[TicketResponse])
def list_tickets(
    status: Optional[TicketStatus] = None,
    ctx: AuthenticatedContext = Depends(get_current_user_and_tenant),
    db: Session = Depends(get_db)
):
    q = db.query(Ticket).filter(Ticket.tenant_id == ctx.tenant.id)
    if status:
        q = q.filter(Ticket.status == status)
    return q.order_by(Ticket.created_at.desc()).all()

@app.get("/api/v1/tickets/{ticket_id}/resolution", response_model=ResolutionDetailResponse)
def get_resolution_detail(
    ticket_id: str,
    ctx: AuthenticatedContext = Depends(get_current_user_and_tenant),
    db: Session = Depends(get_db)
):
    # Strict tenant isolation
    ticket = db.query(Ticket).filter(
        Ticket.id == ticket_id,
        Ticket.tenant_id == ctx.tenant.id
    ).first()

    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found or unauthorized")

    evidence = db.query(EvidenceReference).filter(
        EvidenceReference.ticket_id == ticket.id,
        EvidenceReference.tenant_id == ctx.tenant.id
    ).all()

    proposals = db.query(Proposal).filter(
        Proposal.ticket_id == ticket.id,
        Proposal.tenant_id == ctx.tenant.id
    ).order_by(Proposal.version.desc()).all()

    active_proposal = proposals[0] if proposals else None

    receipts = db.query(ActionReceipt).filter(
        ActionReceipt.tenant_id == ctx.tenant.id,
        ActionReceipt.job_id.in_([j.id for j in ticket.jobs])
    ).all() if ticket.jobs else []

    events = [
        {
            "id": e.id,
            "event_type": e.event_type,
            "actor": e.actor,
            "created_at": e.created_at.isoformat(),
            "details": e.details
        }
        for e in ticket.events
    ]

    return ResolutionDetailResponse(
        ticket=ticket,
        evidence=[
            EvidenceItemResponse(
                id=e.id,
                source_type=e.source_type,
                source_id=e.source_id,
                source_title=e.source_title,
                excerpt=e.excerpt,
                relevance_score=e.relevance_score
            )
            for e in evidence
        ],
        proposals=proposals,
        active_proposal=active_proposal,
        receipts=receipts,
        audit_events=events
    )

# --- PROPOSAL EDIT & APPROVAL ROUTES ---

@app.post("/api/v1/tickets/{ticket_id}/proposals/{proposal_id}/edit", response_model=ProposalResponse)
def edit_proposal(
    ticket_id: str,
    proposal_id: str,
    req: ProposalEditRequest,
    ctx: AuthenticatedContext = Depends(get_current_user_and_tenant),
    db: Session = Depends(get_db)
):
    proposal = db.query(Proposal).filter(
        Proposal.id == proposal_id,
        Proposal.ticket_id == ticket_id,
        Proposal.tenant_id == ctx.tenant.id
    ).first()

    if not proposal:
        raise HTTPException(status_code=404, detail="Proposal not found")

    # Mark old proposal as superseded
    proposal.status = ProposalStatus.SUPERSEDED

    new_hash = compute_args_hash(req.action_arguments)
    new_proposal = Proposal(
        tenant_id=ctx.tenant.id,
        ticket_id=ticket_id,
        version=proposal.version + 1,
        action_type=req.action_type,
        action_arguments=req.action_arguments,
        args_hash=new_hash,
        explanation=req.explanation,
        cited_evidence_ids=proposal.cited_evidence_ids,
        policy_version_snapshot=proposal.policy_version_snapshot,
        status=ProposalStatus.PENDING,
        created_by=ctx.user.id
    )
    db.add(new_proposal)
    db.commit()
    db.refresh(new_proposal)
    return new_proposal

@app.post("/api/v1/tickets/{ticket_id}/proposals/{proposal_id}/decide")
def decide_proposal(
    ticket_id: str,
    proposal_id: str,
    req: ApprovalDecisionRequest,
    ctx: AuthenticatedContext = Depends(get_current_user_and_tenant),
    db: Session = Depends(get_db)
):
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id, Ticket.tenant_id == ctx.tenant.id).first()
    proposal = db.query(Proposal).filter(Proposal.id == proposal_id, Proposal.tenant_id == ctx.tenant.id).first()

    if not ticket or not proposal:
        raise HTTPException(status_code=404, detail="Ticket or Proposal not found")

    approval = Approval(
        tenant_id=ctx.tenant.id,
        proposal_id=proposal.id,
        proposal_version=proposal.version,
        args_hash=proposal.args_hash,
        decided_by_user_id=ctx.user.id,
        is_approved=req.is_approved,
        rejection_reason=req.rejection_reason,
        reviewer_notes=req.reviewer_notes
    )
    db.add(approval)

    if req.is_approved:
        proposal.status = ProposalStatus.APPROVED
        ticket.status = TicketStatus.APPROVED
        
        # Enqueue Execution Job if actionable
        if proposal.action_type != ActionType.ABSTAIN:
            exec_job = Job(
                tenant_id=ctx.tenant.id,
                ticket_id=ticket.id,
                job_type="execute_sandbox_action",
                status=JobStatus.PENDING,
                idempotency_key=f"job_exec_{proposal.id}_{proposal.version}",
                payload={"proposal_id": proposal.id}
            )
            db.add(exec_job)
    else:
        proposal.status = ProposalStatus.REJECTED
        ticket.status = TicketStatus.REJECTED

    db.commit()
    return {"status": "success", "ticket_status": ticket.status.value}

# --- EVALUATION RESULTS ROUTE ---

@app.get("/api/v1/eval/results")
def get_eval_results(ctx: AuthenticatedContext = Depends(get_current_user_and_tenant)):
    # Returns loaded evaluation results if available
    import json
    import os
    eval_file = "/Users/sarthak/.gemini/antigravity/scratch/relay/eval_results.json"
    if os.path.exists(eval_file):
        with open(eval_file, "r") as f:
            return json.load(f)
    return {
        "status": "NOT_RUN",
        "message": "Evaluation benchmarks have not been executed yet."
    }
