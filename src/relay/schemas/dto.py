from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from relay.models.entities import ActionType, ProposalStatus, TicketStatus


class TokenData(BaseModel):
    user_id: str
    email: str
    tenant_ids: list[str]

class UserLoginRequest(BaseModel):
    email: str
    password: str

class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    email: str
    full_name: str
    memberships: list[dict[str, Any]]

class TenantResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    slug: str
    created_at: datetime

class TicketCreateRequest(BaseModel):
    external_ticket_id: str = Field(..., max_length=128)
    customer_email: str = Field(..., max_length=255)
    customer_name: str = Field(..., max_length=128)
    subject: str = Field(..., max_length=255)
    body: str = Field(..., max_length=20000)
    category: str | None = "general"

class TicketResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    tenant_id: str
    external_ticket_id: str
    customer_email: str
    customer_name: str
    subject: str
    body: str
    category: str
    status: TicketStatus
    created_at: datetime
    updated_at: datetime

class EvidenceItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    source_type: str
    source_id: str
    source_title: str
    excerpt: str
    relevance_score: float

class ProposalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    ticket_id: str
    version: int
    action_type: ActionType
    action_arguments: dict[str, Any]
    args_hash: str
    explanation: str
    missing_information: str | None = None
    cited_evidence_ids: list[str]
    policy_version_snapshot: dict[str, Any] | None = None
    account_state_snapshot: dict[str, Any] | None = None
    status: ProposalStatus
    created_at: datetime
    created_by: str

class ProposalEditRequest(BaseModel):
    action_type: ActionType
    action_arguments: dict[str, Any]
    explanation: str

class ApprovalDecisionRequest(BaseModel):
    is_approved: bool
    rejection_reason: str | None = None
    reviewer_notes: str | None = None

class ActionReceiptResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    action_type: ActionType
    idempotency_key: str
    provider: str
    provider_transaction_id: str | None
    status: str
    request_payload: dict[str, Any]
    response_payload: dict[str, Any]
    verified: bool
    created_at: datetime

class ResolutionDetailResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    ticket: TicketResponse
    evidence: list[EvidenceItemResponse]
    proposals: list[ProposalResponse]
    active_proposal: ProposalResponse | None
    receipts: list[ActionReceiptResponse]
    audit_events: list[dict[str, Any]]
