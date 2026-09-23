# Relay Architecture Specification

## 1. System Architecture & Topology

Relay is structured as a modular monolith separating web ingestion, API services, durable leased workers, and isolated sandbox execution.

```
+-------------------------------------------------------+
|                   Product UI (React)                  |
+-------------------------------------------------------+
                           |
                           v (Session Cookie / Bearer Auth)
+-------------------------------------------------------+
|                    FastAPI Web API                    |
|   - Multi-tenant query scoping & CSRF protection      |
|   - Ticket ingestion & Resolution inspection          |
|   - Proposal editing & Reviewer approval binding      |
+-------------------------------------------------------+
                           |
                           v (Durable Database Transaction)
+-------------------------------------------------------+
|            PostgreSQL / SQLite Database               |
|   - Multi-tenant relational schema                    |
|   - Leased Job Queue with Fencing Tokens              |
|   - Audit Ledger & Action Receipts                    |
+-------------------------------------------------------+
                           ^
                           | (Atomic Lease Claims & Backoff)
+-------------------------------------------------------+
|                 Durable Python Worker                 |
|   - Evidence retrieval (Policy Docs + Account Facts)  |
|   - Structured Model Adapter (Deterministic / Live)   |
|   - Re-check policy/account state prior to execution  |
+-------------------------------------------------------+
                           |
                           v (Idempotent execution with reconciliation)
+-------------------------------------------------------+
|             Local Sandbox Action Provider             |
|   - Dedicated persistent action ledger                |
|   - Simulates success, reject, and timeout states     |
+-------------------------------------------------------+
```

---

## 2. Trust Boundaries & Security Model

1. **Untrusted Data Boundary**:
   - Customer tickets and uploaded documentation are treated as untrusted strings.
   - Prompts cannot directly execute actions, escalate roles, or alter database states.
   - LLMs can only emit structured Pydantic schemas allowlisting known action types (`draft_reply`, `cancel_subscription`, `refund`, `abstain`).

2. **Tenant Isolation**:
   - Every database query and worker job is strictly scoped by the authenticated user's `tenant_id`.
   - Tenant headers are cross-checked against the user's cryptographically verified membership token. Cross-tenant reads and mutations return `403 Forbidden` / `404 Not Found`.

3. **Human Approval Contract**:
   - Approvals are cryptographically bound to `SHA256(canonical_action_arguments)` and the `proposal_version`.
   - Modifying a proposal's arguments immediately invalidates prior approvals, requiring renewed review.
   - Re-checking underlying policy versions occurs right before sandbox execution.

4. **Durable Worker & Lease Fencing**:
   - Workers claim jobs atomically with monotonic fencing tokens.
   - If a worker crashes or exceeds its lease timeout, another worker safely claims the job without duplicate side-effects.
   - Sandbox actions utilize persistent idempotency keys. Indeterminate outcomes enter `needs_reconciliation` for status query lookup.
