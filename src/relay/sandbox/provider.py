import time
import uuid
from typing import Any

from pydantic import BaseModel


class SandboxExecutionResult(BaseModel):
    success: bool
    status: str # succeeded, rejected, timeout_pre_commit, timeout_post_commit
    transaction_id: str | None = None
    error_message: str | None = None
    data: dict[str, Any] = {}

class LocalSandboxActionProvider:
    """
    Isolated sandbox provider service with an in-memory & persistent action ledger.
    Simulates:
    - Normal success
    - Rejection
    - Timeout BEFORE commit (no state change)
    - Timeout AFTER commit (state changed, requires reconciliation via idempotency key)
    """
    def __init__(self):
        # Ledger maps idempotency_key -> {status, tx_id, payload, committed}
        self.ledger: dict[str, dict[str, Any]] = {}

    def execute_action(
        self,
        action_type: str,
        idempotency_key: str,
        payload: dict[str, Any],
        simulation_mode: str | None = None
    ) -> SandboxExecutionResult:
        # 1. Idempotency Check
        if idempotency_key in self.ledger:
            record = self.ledger[idempotency_key]
            return SandboxExecutionResult(
                success=record["status"] == "succeeded",
                status=record["status"],
                transaction_id=record["transaction_id"],
                data=record["payload"]
            )

        # 2. Simulate Failure / Timeout Modes
        if simulation_mode == "timeout_pre_commit":
            # Action NOT committed
            return SandboxExecutionResult(
                success=False,
                status="timeout_pre_commit",
                error_message="Provider network timeout prior to ledger transaction commit."
            )

        if simulation_mode == "timeout_post_commit":
            # Action committed into provider ledger, but caller receives timeout exception
            tx_id = f"tx_sbx_{uuid.uuid4().hex[:12]}"
            self.ledger[idempotency_key] = {
                "status": "succeeded",
                "transaction_id": tx_id,
                "payload": payload,
                "action_type": action_type,
                "timestamp": time.time()
            }
            return SandboxExecutionResult(
                success=False,
                status="timeout_post_commit",
                error_message="Provider downstream connection timed out after ledger commit."
            )

        if simulation_mode == "reject":
            return SandboxExecutionResult(
                success=False,
                status="rejected",
                error_message="Provider rejected transaction (e.g. card issuer refusal or inactive subscription)."
            )

        # 3. Normal Success Path
        tx_id = f"tx_sbx_{uuid.uuid4().hex[:12]}"
        self.ledger[idempotency_key] = {
            "status": "succeeded",
            "transaction_id": tx_id,
            "payload": payload,
            "action_type": action_type,
            "timestamp": time.time()
        }
        return SandboxExecutionResult(
            success=True,
            status="succeeded",
            transaction_id=tx_id,
            data=payload
        )

    def lookup_status(self, idempotency_key: str) -> dict[str, Any] | None:
        """Reconciliation lookup for resolving indeterminate states."""
        return self.ledger.get(idempotency_key)

# Global sandbox instance
sandbox_provider = LocalSandboxActionProvider()
