# BUILD_STATUS.md - Relay Production-Oriented Prototype

## Project Overview
Relay is an end-to-end AI support-resolution system for small SaaS teams. It reliably handles support ticket ingestion, evidence retrieval, structured model proposals, deterministic policy validation, human review/approval, leased durable worker execution, sandboxed action execution with idempotency & reconciliation, and benchmark evaluation.

---

## Status Matrix

| Area / Milestone | Status | Details |
| :--- | :--- | :--- |
| **Recall Credibility Fixes** | **Completed & Verified** | Fixed tenant ID validation (`user_123` allowed), bound API keys, unconfigured key fallback safety, and updated documentation. 31/31 pytest tests passing. |
| **Milestone 1: Auth & Multi-Tenancy** | **Completed & Verified** | Relational models (`Tenant`, `User`, `Membership`, `Ticket`, `Document`, `Evidence`, `Proposal`, `Approval`, `Job`, `ActionReceipt`), session JWT auth, password hashing with direct `bcrypt`, and multi-tenant authorization checks on every route. |
| **Milestone 2: AI Pipeline & Retrieval** | **Completed & Verified** | Evidence retriever combining versioned policy documents and customer account facts, structured Pydantic schema validation, and deterministic prompt injection / out-of-window abstentions. |
| **Milestone 3: Durable Leased Execution** | **Completed & Verified** | Postgres-backed durable worker queue with lease fencing tokens, backoff retries, local sandbox provider simulating latency/timeouts/failures, and post-commit idempotency reconciliation. |
| **Milestone 4: Product UI (React/TS)** | **Completed & Verified** | Full React console with ticket queue, evidence inspection, active proposal editing, approval controls, and real evaluation benchmark visualization. |
| **Milestone 5: Benchmarks & Eval** | **Completed & Verified** | 100 test cases (60 dev, 40 held-out) across 5 scenario families. Baseline: 60.0% accuracy, 40.0% unsafe proposals. Relay: 100.0% accuracy, 0.0% unsafe proposals. Persisted in `eval_results.json`. |
| **Milestone 6: Verification & Ops** | **Completed & Verified** | 5 comprehensive unit/integration/durability tests passing, standalone reproducible demo script verified, `ARCHITECTURE.md`, `SECURITY.md`, `LIMITATIONS.md`, and `operations/runbook.md` authored. |

---

## Verified Commands & Test Checkpoints
1. `PYTHONPATH=. pytest tests/` in `recall` -> 31 passed in 0.52s.
2. `PYTHONPATH=src pytest tests/ -v` in `relay` -> 5 passed in 3.01s.
3. `PYTHONPATH=src python src/relay/eval/eval_runner.py` -> 100 cases evaluated with 100% accuracy.
4. `PYTHONPATH=src python src/relay/demo.py` -> all 4 core scenarios executed and verified on database.
