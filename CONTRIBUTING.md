# Contributing to Relay

Relay is a deterministic support orchestration and policy boundary validation engine.

## Prerequisites
- Python 3.11+
- SQLite 3.35+ or PostgreSQL 15+

## Local Development Workflow

1. **Environment Setup**:
   ```bash
   git clone https://github.com/vermasarthak/relay.git
   cd relay
   python3 -m venv venv
   source venv/bin/activate
   pip install -e ".[dev]"
   ```

2. **Database Seeding & Server Run**:
   ```bash
   python src/relay/db/seed.py
   uvicorn relay.api.main:app --port 8000 --reload
   ```

3. **Running the Test Suite**:
   ```bash
   pytest tests/ -v
   ```

4. **Running the 100-Case Deterministic Regression Suite**:
   ```bash
   python src/relay/eval/eval_runner.py
   ```

## Contribution Invariants
- **Multi-Tenant Authorization**: All database queries and entity modifications must be scoped to the authenticated tenant.
- **Approval Invalidation**: Any mutation to a proposal must invalidate prior approvals by recomputing the proposal parameter hash.
- **Explicit Evaluation**: Disclose synthetic regression suites honestly; do not claim open-ended model superiority from deterministic rule suites.
