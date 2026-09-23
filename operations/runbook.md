# Operations Runbook: Relay Support Engine

## 1. Quickstart Commands

### Start Database Seed & App Locally
```bash
# In relay directory
export PYTHONPATH=src
python src/relay/db/seed.py
uvicorn relay.api.main:app --host 0.0.0.0 --port 8000
```

### Run Durable Worker Process
```bash
export PYTHONPATH=src
python -c "
from relay.db.session import SessionLocal
from relay.worker.durable_worker import DurableWorker
import time
db = SessionLocal()
worker = DurableWorker(db)
print('Relay Worker active. Polling jobs...')
while True:
    job = worker.claim_next_job()
    if job:
        print(f'Claimed job {job.id} ({job.job_type})')
        worker.execute_job(job.id)
    time.sleep(1)
"
```

### Run Reproducible Demo
```bash
PYTHONPATH=src python src/relay/demo.py
```

### Run Benchmark Evaluation Harness
```bash
PYTHONPATH=src python src/relay/eval/eval_runner.py
```

---

## 2. Health & Recovery Procedures

- **Worker Lease Expiration**: Leased jobs automatically become eligible for re-claiming by healthy workers after 30 seconds of inactivity.
- **Indeterminate Reconciliation**: Jobs in `needs_reconciliation` state can be re-queried against the sandbox provider ledger using `job_type="reconcile_action"`.
