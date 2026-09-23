import logging
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from relay.core.clock import Clock, get_clock
from relay.core.config import settings
from relay.core.security import compute_args_hash
from relay.models.entities import (
    ActionReceipt,
    ActionType,
    Approval,
    AuditEvent,
    CustomerAccount,
    Document,
    Job,
    JobAttempt,
    JobStatus,
    Proposal,
    ProposalStatus,
    Ticket,
    TicketStatus,
)
from relay.sandbox.provider import sandbox_provider
from relay.services.model_adapter import get_model_provider
from relay.services.retriever import EvidenceRetriever

logger = logging.getLogger("relay.worker")

class DurableWorker:
    def __init__(self, db: Session, worker_id: str | None = None, lease_duration_seconds: int = 30, clock: Clock | None = None):
        self.db = db
        self.worker_id = worker_id or f"wrk_{uuid.uuid4().hex[:8]}"
        self.lease_duration_seconds = lease_duration_seconds
        self.clock = clock or get_clock()

    def utc_now(self) -> datetime:
        return self.clock.now()

    def claim_next_job(self) -> Job | None:
        """
        Atomically leases the next available job using lease fencing tokens.
        Ensures concurrent workers cannot double-claim or execute stale leases.
        """
        now = self.utc_now()
        job = self.db.query(Job).filter(
            Job.next_attempt_at <= now,
            or_(
                Job.status == JobStatus.PENDING,
                Job.status == JobStatus.RETRY_SCHEDULED,
                and_(Job.status == JobStatus.LEASED, Job.leased_until < now) # Stale lease recovery
            )
        ).with_for_update(skip_locked=True).first()

        if not job:
            return None

        # Increment fencing token and assign lease
        job.fencing_token += 1
        job.worker_id = self.worker_id
        job.status = JobStatus.LEASED
        job.leased_until = now + timedelta(seconds=self.lease_duration_seconds)
        job.attempt_count += 1
        
        # Log attempt
        attempt = JobAttempt(
            job_id=job.id,
            attempt_number=job.attempt_count,
            worker_id=self.worker_id,
            fencing_token=job.fencing_token,
            status="running",
            started_at=now
        )
        self.db.add(attempt)
        self.db.commit()
        self.db.refresh(job)
        return job

    def execute_job(self, job_id: str, expected_fencing_token: int | None = None) -> bool:
        job = self.db.query(Job).filter(Job.id == job_id).first()
        now = self.utc_now()
        if not job or job.worker_id != self.worker_id:
            return False

        if expected_fencing_token is not None and job.fencing_token != expected_fencing_token:
            logger.warning(f"Fencing token mismatch for job {job_id}: expected {expected_fencing_token}, found {job.fencing_token}")
            return False

        if job.leased_until:
            leased_until = job.leased_until if job.leased_until.tzinfo else job.leased_until.replace(tzinfo=UTC)
            current_now = now if now.tzinfo else now.replace(tzinfo=UTC)
            if leased_until < current_now:
                logger.warning(f"Worker {self.worker_id} attempting to execute expired lease on job {job_id}")
                return False

        current_token = job.fencing_token

        try:
            if job.job_type == "analyze_ticket":
                self._handle_analyze_ticket(job)
            elif job.job_type == "execute_sandbox_action":
                self._handle_execute_sandbox_action(job)
            elif job.job_type == "reconcile_action":
                self._handle_reconcile_action(job)
            else:
                raise ValueError(f"Unknown job_type: {job.job_type}")

            # Commit success
            job.status = JobStatus.COMPLETED
            job.updated_at = self.utc_now()
            
            # Update attempt record
            attempt = self.db.query(JobAttempt).filter(
                JobAttempt.job_id == job.id,
                JobAttempt.fencing_token == current_token
            ).first()
            if attempt:
                attempt.status = "success"
                attempt.completed_at = self.utc_now()

            self.db.commit()
            return True

        except Exception as exc:
            logger.error(f"Worker {self.worker_id} error executing job {job.id}: {exc}")
            self.db.rollback()

            # Re-fetch and record failure / reset state if validation error
            job = self.db.query(Job).filter(Job.id == job_id).first()
            if job:
                ticket = self.db.query(Ticket).filter(Ticket.id == job.ticket_id).first()
                exc_str = str(exc).lower()
                if "invalidat" in exc_str or "policy change" in exc_str or "account state" in exc_str:
                    if ticket:
                        ticket.status = TicketStatus.AWAITING_REVIEW
                    proposal_id = job.payload.get("proposal_id")
                    if proposal_id:
                        p = self.db.query(Proposal).filter(Proposal.id == proposal_id).first()
                        if p:
                            p.status = ProposalStatus.PENDING
                    job.status = JobStatus.FAILED
                else:
                    if job.attempt_count >= job.max_attempts:
                        job.status = JobStatus.FAILED
                    else:
                        job.status = JobStatus.RETRY_SCHEDULED
                        backoff = min(300, 2 ** job.attempt_count)
                        job.next_attempt_at = self.utc_now() + timedelta(seconds=backoff)

                # Clear lease on failure/retry so other workers can claim cleanly
                job.worker_id = None
                job.leased_until = None
                job.updated_at = self.utc_now()

                attempt = self.db.query(JobAttempt).filter(
                    JobAttempt.job_id == job.id,
                    JobAttempt.fencing_token == current_token
                ).first()
                if attempt:
                    attempt.status = "failed"
                    attempt.error_message = str(exc)
                    attempt.completed_at = self.utc_now()

                self.db.commit()
            return False

    def _handle_analyze_ticket(self, job: Job):
        ticket = self.db.query(Ticket).filter(Ticket.id == job.ticket_id).first()
        if not ticket:
            return

        ticket.status = TicketStatus.ANALYZING

        # 1. Retrieve evidence
        retriever = EvidenceRetriever(self.db, ticket.tenant_id)
        evidence_items = retriever.retrieve_for_ticket(ticket.id, ticket.customer_email, f"{ticket.subject} {ticket.body}")

        evidence_payload = [
            {"id": e.id, "title": e.source_title, "excerpt": e.excerpt, "source_type": e.source_type}
            for e in evidence_items
        ]

        # 2. Run model pipeline
        model = get_model_provider(settings.model_provider)
        model_out = model.resolve_ticket(
            ticket_subject=ticket.subject,
            ticket_body=ticket.body,
            customer_email=ticket.customer_email,
            evidence_list=evidence_payload
        )

        # 3. Policy & Customer Account Snapshot
        doc_snapshot = {}
        for d in self.db.query(Document).filter(Document.tenant_id == ticket.tenant_id).all():
            doc_snapshot[d.id] = d.current_version

        acc_snapshot = {}
        cust_acc = self.db.query(CustomerAccount).filter(
            CustomerAccount.tenant_id == ticket.tenant_id,
            CustomerAccount.customer_email == ticket.customer_email
        ).first()
        if cust_acc:
            acc_snapshot[cust_acc.id] = {
                "subscription_status": cust_acc.subscription_status,
                "plan_tier": cust_acc.plan_tier,
                "monthly_rate_cents": cust_acc.monthly_rate_cents,
                "days_since_billing": cust_acc.days_since_billing
            }

        # Validate cited evidence IDs (must exist in retrieved set and belong to tenant)
        retrieved_ids = {e["id"] for e in evidence_payload}
        valid_cited_ids = [cid for cid in model_out.cited_evidence_ids if cid in retrieved_ids]

        # 4. Create Proposal
        args_hash = compute_args_hash(model_out.action_arguments)
        proposal = Proposal(
            tenant_id=ticket.tenant_id,
            ticket_id=ticket.id,
            version=1,
            action_type=model_out.proposed_action,
            action_arguments=model_out.action_arguments,
            args_hash=args_hash,
            explanation=model_out.explanation,
            missing_information=model_out.missing_information,
            cited_evidence_ids=valid_cited_ids,
            policy_version_snapshot=doc_snapshot,
            account_state_snapshot=acc_snapshot,
            status=ProposalStatus.PENDING
        )
        self.db.add(proposal)

        if model_out.proposed_action == ActionType.ABSTAIN:
            ticket.status = TicketStatus.ABSTAINED
        else:
            ticket.status = TicketStatus.AWAITING_REVIEW

        ticket.category = model_out.category
        
        # Audit Log
        event = AuditEvent(
            tenant_id=ticket.tenant_id,
            ticket_id=ticket.id,
            event_type="proposal_generated",
            actor=self.worker_id,
            correlation_id=job.idempotency_key,
            details={"action": model_out.proposed_action.value, "category": model_out.category}
        )
        self.db.add(event)

    def _handle_execute_sandbox_action(self, job: Job):
        ticket = self.db.query(Ticket).filter(Ticket.id == job.ticket_id).first()
        if not ticket:
            return

        proposal_id = job.payload.get("proposal_id")
        proposal = self.db.query(Proposal).filter(Proposal.id == proposal_id).first()
        if not proposal:
            raise ValueError("Proposal not found for execution job")

        # 1. Verify Approval Integrity
        approval = self.db.query(Approval).filter(Approval.proposal_id == proposal.id).first()
        if not approval or not approval.is_approved:
            raise ValueError("Execution rejected: Proposal is not approved")

        current_hash = compute_args_hash(proposal.action_arguments)
        if current_hash != approval.args_hash or proposal.version != approval.proposal_version:
            ticket.status = TicketStatus.AWAITING_REVIEW
            proposal.status = ProposalStatus.PENDING
            raise ValueError("Approval invalidation: Proposal arguments or version were modified")

        # 2. Recheck underlying Policy and Customer Account State
        for doc_id, snap_ver in (proposal.policy_version_snapshot or {}).items():
            doc = self.db.query(Document).filter(Document.id == doc_id).first()
            if doc and doc.current_version != snap_ver:
                ticket.status = TicketStatus.AWAITING_REVIEW
                proposal.status = ProposalStatus.PENDING
                raise ValueError("Policy change detected: Underwriting policy was updated after approval")

        for acc_id, snap_data in (proposal.account_state_snapshot or {}).items():
            acc = self.db.query(CustomerAccount).filter(CustomerAccount.id == acc_id).first()
            if acc and (
                acc.subscription_status != snap_data.get("subscription_status")
                or acc.plan_tier != snap_data.get("plan_tier")
            ):
                ticket.status = TicketStatus.AWAITING_REVIEW
                proposal.status = ProposalStatus.PENDING
                raise ValueError("Account state changed: Customer subscription or plan was altered after approval")

        ticket.status = TicketStatus.EXECUTING
        self.db.flush()

        # 3. Call Sandbox Action Provider outside DB transaction locks
        sim_mode = job.payload.get("simulation_mode")
        provider_res = sandbox_provider.execute_action(
            action_type=proposal.action_type.value,
            idempotency_key=job.idempotency_key,
            payload=proposal.action_arguments,
            simulation_mode=sim_mode
        )

        # 4. Handle Result & Indeterminate Statuses
        if provider_res.status == "timeout_post_commit":
            # Indeterminate state -> Trigger Reconciliation
            ticket.status = TicketStatus.NEEDS_RECONCILIATION
            receipt = ActionReceipt(
                tenant_id=ticket.tenant_id,
                job_id=job.id,
                action_type=proposal.action_type,
                idempotency_key=job.idempotency_key,
                provider="relay_local_sandbox",
                status="needs_reconciliation",
                request_payload=proposal.action_arguments,
                response_payload={"error": provider_res.error_message},
                verified=False
            )
            self.db.add(receipt)
            return

        if not provider_res.success:
            ticket.status = TicketStatus.FAILED
            receipt = ActionReceipt(
                tenant_id=ticket.tenant_id,
                job_id=job.id,
                action_type=proposal.action_type,
                idempotency_key=job.idempotency_key,
                provider="relay_local_sandbox",
                status="failed",
                request_payload=proposal.action_arguments,
                response_payload={"error": provider_res.error_message},
                verified=False
            )
            self.db.add(receipt)
            return

        # Success - Apply state changes
        if proposal.action_type == ActionType.CANCEL_SUBSCRIPTION:
            acc = self.db.query(CustomerAccount).filter(
                CustomerAccount.tenant_id == ticket.tenant_id,
                CustomerAccount.customer_email == ticket.customer_email
            ).first()
            if acc:
                acc.subscription_status = "canceled"

        ticket.status = TicketStatus.SUCCEEDED
        receipt = ActionReceipt(
            tenant_id=ticket.tenant_id,
            job_id=job.id,
            action_type=proposal.action_type,
            idempotency_key=job.idempotency_key,
            provider="relay_local_sandbox",
            provider_transaction_id=provider_res.transaction_id,
            status="succeeded",
            request_payload=proposal.action_arguments,
            response_payload=provider_res.data,
            verified=True
        )
        self.db.add(receipt)

        event = AuditEvent(
            tenant_id=ticket.tenant_id,
            ticket_id=ticket.id,
            event_type="action_executed",
            actor=self.worker_id,
            correlation_id=job.idempotency_key,
            details={"action": proposal.action_type.value, "tx_id": provider_res.transaction_id}
        )
        self.db.add(event)

    def _handle_reconcile_action(self, job: Job):
        ticket = self.db.query(Ticket).filter(Ticket.id == job.ticket_id).first()
        target_key = job.payload.get("target_idempotency_key")
        
        status_record = sandbox_provider.lookup_status(target_key)
        if status_record and status_record.get("status") == "succeeded":
            if ticket:
                ticket.status = TicketStatus.SUCCEEDED
                action_type = status_record.get("action_type")
                if action_type == ActionType.CANCEL_SUBSCRIPTION.value:
                    acc = self.db.query(CustomerAccount).filter(
                        CustomerAccount.tenant_id == ticket.tenant_id,
                        CustomerAccount.customer_email == ticket.customer_email
                    ).first()
                    if acc:
                        acc.subscription_status = "canceled"

            receipt = self.db.query(ActionReceipt).filter(ActionReceipt.idempotency_key == target_key).first()
            if receipt:
                receipt.status = "succeeded"
                receipt.provider_transaction_id = status_record.get("transaction_id")
                receipt.verified = True

            if ticket:
                event = AuditEvent(
                    tenant_id=ticket.tenant_id,
                    ticket_id=ticket.id,
                    event_type="action_reconciled",
                    actor=self.worker_id,
                    correlation_id=job.idempotency_key,
                    details={"action": status_record.get("action_type"), "tx_id": status_record.get("transaction_id")}
                )
                self.db.add(event)
        else:
            if ticket:
                ticket.status = TicketStatus.FAILED
                event = AuditEvent(
                    tenant_id=ticket.tenant_id,
                    ticket_id=ticket.id,
                    event_type="action_reconciliation_failed",
                    actor=self.worker_id,
                    correlation_id=job.idempotency_key,
                    details={"target_idempotency_key": target_key}
                )
                self.db.add(event)
