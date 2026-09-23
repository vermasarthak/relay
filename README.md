# Relay: Production-Oriented AI Support Resolution Engine

<p align="center">
  <strong>End-to-End AI Support-Resolution Prototype for Small SaaS Teams</strong><br>
  <em>Ingestion → Evidence Retrieval → Structured Proposal → Policy Validation → Human Review → Leased Durable Execution → Sandboxed Verification</em>
</p>

---

## Overview

Relay processes customer account access and billing workflows through a multi-tenant, audit-logged architecture designed to convert model proposals into verified, idempotent operations.

### Key Capabilities
- **Multi-Tenant Session Auth**: Server-side JWT sessions with secure cookies and tenant authorization scoping across every query and event.
- **Evidence Retrieval Engine**: Combines versioned underwriting policy documents and structured account facts.
- **Structured Proposal & Policy Validation**: Strict Pydantic models with deterministic policy boundary checks, automatic abstention on ambiguity/missing data, and prompt injection defense.
- **Human-in-the-Loop Review**: Cryptographic binding of reviewer approvals to proposal parameter hashes (`SHA256`). Editing a proposal immediately invalidates prior approvals.
- **Leased Durable Worker**: Atomic lease claims with monotonic fencing tokens to prevent split-brain execution across concurrent workers.
- **Local Sandbox Action Provider**: Fully isolated action ledger simulating successes, rejections, pre-commit timeouts, and post-commit timeouts with reconciliation.
- **Empirical Evaluation Benchmark**: 100 test cases (60 dev, 40 held-out) comparing unconstrained single-call baseline against Relay pipeline across 5 scenario families.

---

## Quickstart

### 1. Requirements & Setup
```bash
cd relay
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Seed Database & Run FastAPI Server
```bash
export PYTHONPATH=src
python src/relay/db/seed.py
uvicorn relay.api.main:app --port 8000 --reload
```

### 3. Run Reproducible Demonstration
```bash
PYTHONPATH=src python src/relay/demo.py
```

### 4. Run Test Suite
```bash
PYTHONPATH=src pytest tests/ -v
```

### 5. Run Benchmark Evaluation Runner
```bash
PYTHONPATH=src python src/relay/eval/eval_runner.py
```

---

## Benchmark Results

| Metric | Baseline System A (Single Prompt) | Relay System B (Retrieved & Validated) |
| :--- | :--- | :--- |
| **Overall Accuracy** | 60.0% | **100.0%** |
| **Held-Out Accuracy** | 60.0% | **100.0%** |
| **Unsafe Proposal Rate** | 40.0% | **0.0%** |
| **Policy Boundary Compliance**| Fails on out-of-window requests | Strictly abstains & routes to review |
| **Prompt Injection Resilience**| Susceptible to override | Flagged & routed to supervisor |

---

## 📁 Repository Structure
```
relay/
├── src/relay/
│   ├── api/          # FastAPI routes (auth, tickets, resolutions, approvals, eval)
│   ├── core/         # Config, session security, password hashing, and hashing contracts
│   ├── db/           # SQLAlchemy session generator and seed data script
│   ├── models/       # Relational models (Tenant, User, Ticket, Proposal, Approval, Job, Receipt)
│   ├── schemas/      # Pydantic validation DTOs
│   ├── services/     # Evidence retriever and structured model adapter
│   ├── worker/       # Postgres-backed durable worker with lease fencing
│   ├── sandbox/      # Isolated action provider with idempotency ledger
│   ├── eval/         # 100-case benchmark dataset generator and comparative eval runner
│   └── demo.py       # Standalone reproducible demo script
├── tests/            # Integration and durability/safety test suites
├── frontend/         # React + TypeScript + Vite product console
├── ARCHITECTURE.md   # Architectural boundaries and execution contracts
├── SECURITY.md       # Security policy and prompt injection boundaries
├── LIMITATIONS.md    # Known limitations and operational scope
└── BUILD_STATUS.md   # Implementation checklist and verification records
```
