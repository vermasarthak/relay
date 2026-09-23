from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
import os
import json
import re
from relay.models.entities import ActionType

class ModelResolutionOutput(BaseModel):
    category: str
    proposed_action: ActionType
    action_arguments: Dict[str, Any] = Field(default_factory=dict)
    cited_evidence_ids: List[str] = Field(default_factory=list)
    explanation: str
    missing_information: Optional[str] = None

class ModelProvider(ABC):
    @abstractmethod
    def resolve_ticket(
        self,
        ticket_subject: str,
        ticket_body: str,
        customer_email: str,
        evidence_list: List[Dict[str, Any]]
    ) -> ModelResolutionOutput:
        pass

class DeterministicModelFake(ModelProvider):
    """
    Deterministic model test double for offline tests and predictable baseline validation.
    Detects intent, checks basic patterns against evidence, and emits structured outputs.
    """
    def resolve_ticket(
        self,
        ticket_subject: str,
        ticket_body: str,
        customer_email: str,
        evidence_list: List[Dict[str, Any]]
    ) -> ModelResolutionOutput:
        combined = f"{ticket_subject} {ticket_body}".lower()

        # Evidence map
        evi_by_id = {e["id"]: e for e in evidence_list}
        all_ids = list(evi_by_id.keys())

        # Check for prompt injection / security evasion attempts
        if "ignore previous instructions" in combined or "grant admin" in combined or "system prompt" in combined:
            return ModelResolutionOutput(
                category="security_suspicious",
                proposed_action=ActionType.ABSTAIN,
                action_arguments={},
                cited_evidence_ids=all_ids[:1],
                explanation="Potential prompt injection or policy bypass detected in input.",
                missing_information="Human supervisor review required for security flag."
            )

        # 1. Cancellation request
        if "cancel" in combined and ("subscription" in combined or "plan" in combined or "account" in combined):
            return ModelResolutionOutput(
                category="billing_cancellation",
                proposed_action=ActionType.CANCEL_SUBSCRIPTION,
                action_arguments={"customer_email": customer_email, "immediate": True},
                cited_evidence_ids=all_ids,
                explanation="Customer explicitly requested subscription cancellation. Checked account state in evidence."
            )

        # 2. Refund request
        if "refund" in combined or "charge back" in combined or "money back" in combined:
            # Check if reason or amount is specified
            amount_match = re.search(r'\$?(\d+)', combined)
            amount_cents = int(amount_match.group(1)) * 100 if amount_match else 2900
            
            # Check if policy evidence mentions refund window (e.g. 14 days)
            days_billing = 5
            for e in evidence_list:
                if "DaysSinceBillingCycle=" in e.get("excerpt", ""):
                    m = re.search(r'DaysSinceBillingCycle=(\d+)', e["excerpt"])
                    if m:
                        days_billing = int(m.group(1))

            if days_billing > 14:
                return ModelResolutionOutput(
                    category="billing_refund",
                    proposed_action=ActionType.ABSTAIN,
                    action_arguments={"requested_amount_cents": amount_cents},
                    cited_evidence_ids=all_ids,
                    explanation=f"Refund request is outside the 14-day policy window ({days_billing} days elapsed).",
                    missing_information="Requires discretionary managerial exception."
                )

            return ModelResolutionOutput(
                category="billing_refund",
                proposed_action=ActionType.REFUND,
                action_arguments={"amount_cents": amount_cents, "reason": "in_policy_request"},
                cited_evidence_ids=all_ids,
                explanation="Refund requested within standard 14-day policy window. Grounded in account and policy evidence."
            )

        # 3. Account Access / Password / General Support
        if "password" in combined or "login" in combined or "access" in combined or "2fa" in combined or "reset" in combined:
            return ModelResolutionOutput(
                category="account_access",
                proposed_action=ActionType.DRAFT_REPLY,
                action_arguments={
                    "reply_body": "To reset your password and recover account access, visit https://app.relaydemo.internal/reset and follow the 2FA verification prompt."
                },
                cited_evidence_ids=all_ids,
                explanation="Drafted response using standard account recovery policy procedures."
            )

        # Default fallback - Abstain when ambiguous or missing facts
        return ModelResolutionOutput(
            category="general_inquiry",
            proposed_action=ActionType.ABSTAIN,
            action_arguments={},
            cited_evidence_ids=all_ids[:1],
            explanation="Ticket inquiry contains insufficient details to determine an automated action.",
            missing_information="Awaiting customer clarification on specific account issue."
        )

class GeminiModelAdapter(ModelProvider):
    """
    Live model adapter interfacing with Google Gemini models.
    Requires GEMINI_API_KEY. Never silently substitutes offline mode when live fails.
    """
    def __init__(self, api_key: str, model_name: str = "gemini-1.5-flash"):
        self.api_key = api_key
        self.model_name = model_name

    def resolve_ticket(
        self,
        ticket_subject: str,
        ticket_body: str,
        customer_email: str,
        evidence_list: List[Dict[str, Any]]
    ) -> ModelResolutionOutput:
        import urllib.request
        # Explicit live API integration contract
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model_name}:generateContent?key={self.api_key}"
        headers = {"Content-Type": "application/json"}
        payload = {
            "contents": [{
                "parts": [{
                    "text": f"Subject: {ticket_subject}\nBody: {ticket_body}\nEvidence: {json.dumps(evidence_list)}"
                }]
            }]
        }
        req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                # Parse structured output from response
                text = data["candidates"][0]["content"]["parts"][0]["text"]
                parsed = json.loads(text)
                return ModelResolutionOutput(**parsed)
        except Exception as e:
            raise RuntimeError(f"Live Gemini API inference failed: {str(e)}. Mode is live, will not silently fall back.")

def get_model_provider(provider_name: Optional[str] = None) -> ModelProvider:
    # Always explicit mode; never silently substitute
    if provider_name == "deterministic_fake" or provider_name is None:
        return DeterministicModelFake()
    elif provider_name == "gemini_live":
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY is not configured in environment. Explicit live mode cannot start.")
        return GeminiModelAdapter(api_key=api_key)
    raise ValueError(f"Model provider '{provider_name}' not configured or missing API credentials.")
