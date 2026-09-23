from pydantic import BaseModel, ConfigDict, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from relay.models.entities import UserRole, TicketStatus, ActionType, ProposalStatus, JobStatus

class TokenData(BaseModel):
    user_id: str
    email: str
    tenant_ids: List[str]

class UserLoginRequest(BaseModel):
    email: str
    password: str

class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    email: str
    full_name: str
    memberships: List[Dict[str, Any]]

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
    category: Optional[str] = "general"

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
    action_arguments: Dict[str, Any]
    args_hash: str
    explanation: str
    missing_information: Optional[str] = None
    cited_evidence_ids: List[str]
    status: ProposalStatus
    created_at: datetime
    created_by: str

class ProposalEditRequest(BaseModel):
    action_type: ActionType
    action_arguments: Dict[str, Any]
    explanation: str

class ApprovalDecisionRequest(BaseModel):
    is_approved: bool
    rejection_reason: Optional[str] = None
    reviewer_notes: Optional[str] = None

class ActionReceiptResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    action_type: ActionType
    idempotency_key: str
    provider: str
    provider_transaction_id: Optional[str]
    status: str
    request_payload: Dict[str, Any]
    response_payload: Dict[str, Any]
    verified: bool
    created_at: datetime

class ResolutionDetailResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    ticket: TicketResponse
    evidence: List[EvidenceItemResponse]
    proposals: List[ProposalResponse]
    active_proposal: Optional[ProposalResponse]
    receipts: List[ActionReceiptResponse]
    audit_events: List[Dict[str, Any]]
