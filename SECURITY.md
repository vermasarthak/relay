# Relay Security Policy

## Multi-Tenancy & Authorization
- Every API endpoint validates the caller's server-side session and ensures their membership permits access to the requested `tenant_id`.
- Tenant IDs supplied in request headers or payloads cannot grant cross-tenant access.

## Prompt Injection & LLM Boundaries
- The LLM output is parsed strictly into Pydantic models.
- Prompt injection attempts (e.g., instructions to refund $50,000 or grant admin privileges) are flagged and automatically routed to human supervisor abstention.
- Self-reported model confidence is never treated as authorization to execute privileged actions.

## Action Idempotency & Reconciliation
- All sandbox actions require unique deterministic idempotency keys.
- Financial mutations (refunds, cancellations) are never executed twice in the event of timeouts or worker reboots.
