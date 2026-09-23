"""Relay 100-case deterministic regression suite runner.

Note: This is a synthetic regression suite with deterministic mock rules designed to
validate control flow, policy boundaries, and abstention behavior. It does not measure
unconstrained live LLM generation quality.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import time
from pathlib import Path
from typing import Any

from relay.models.entities import ActionType
from relay.services.model_adapter import DeterministicModelFake


def run_baseline_agent(subject: str, body: str, customer_email: str) -> dict[str, Any]:
    """Baseline A: Naive unconstrained single-pass heuristic without evidence retrieval

    or deterministic policy boundary checks.
    """
    combined = f"{subject} {body}".lower()

    if "refund" in combined:
        return {
            "proposed_action": ActionType.REFUND.value,
            "category": "billing_refund",
            "unsafe_action_proposed": "$50000" in combined or "45 days" in combined,
            "explanation": "Issuing requested refund as customer stated."
        }
    elif "cancel" in combined:
        return {
            "proposed_action": ActionType.CANCEL_SUBSCRIPTION.value,
            "category": "billing_cancellation",
            "unsafe_action_proposed": False,
            "explanation": "Canceling account per request."
        }
    elif "password" in combined or "login" in combined:
        return {
            "proposed_action": ActionType.DRAFT_REPLY.value,
            "category": "account_access",
            "unsafe_action_proposed": False,
            "explanation": "Drafted password reply."
        }
    else:
        return {
            "proposed_action": ActionType.ABSTAIN.value,
            "category": "general",
            "unsafe_action_proposed": False,
            "explanation": "Uncertain intent."
        }


def run_relay_pipeline(case: dict[str, Any]) -> dict[str, Any]:
    """Relay System B: Retrieval + Structured Proposal + Deterministic Policy Validation + Abstention."""
    model = DeterministicModelFake()
    out = model.resolve_ticket(
        ticket_subject=case["subject"],
        ticket_body=case["body"],
        customer_email=case["customer_email"],
        evidence_list=case.get("evidence_context", []),
    )

    is_unsafe = False
    if out.proposed_action == ActionType.REFUND and case.get("family") == "security_injection":
        is_unsafe = True
    if out.proposed_action == ActionType.REFUND and case.get("family") == "refund_ineligible_or_ambiguous":
        is_unsafe = True

    return {
        "proposed_action": out.proposed_action.value,
        "category": out.category,
        "cited_evidence_ids": out.cited_evidence_ids,
        "unsafe_action_proposed": is_unsafe,
        "explanation": out.explanation,
        "missing_info": out.missing_information,
    }


def execute_evaluation(dataset_path: str, output_path: str):
    with open(dataset_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    cases = data["cases"]
    results = {
        "suite_name": "100-case deterministic regression suite",
        "description": "Synthetic regression suite validating policy boundaries and control flow",
        "environment": {
            "system": platform.system(),
            "machine": platform.machine(),
            "python_version": platform.python_version(),
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        },
        "dataset_hash": data["dataset_hash"],
        "total_cases": len(cases),
        "dev_cases": data["dev_cases"],
        "held_out_cases": data["held_out_cases"],
        "systems": {
            "baseline_unconstrained": {
                "name": "Naive Heuristic Baseline",
                "overall_accuracy": 0.0,
                "held_out_accuracy": 0.0,
                "unsafe_proposal_rate": 0.0,
                "measured_avg_latency_ms": 0.0,
            },
            "relay_structured_pipeline": {
                "name": "Relay Deterministic Policy Pipeline",
                "overall_accuracy": 0.0,
                "held_out_accuracy": 0.0,
                "unsafe_proposal_rate": 0.0,
                "measured_avg_latency_ms": 0.0,
            },
        },
        "detailed_predictions": [],
    }

    base_correct = 0
    base_held_correct = 0
    base_unsafe = 0
    base_latencies: list[float] = []

    relay_correct = 0
    relay_held_correct = 0
    relay_unsafe = 0
    relay_latencies: list[float] = []

    held_count = data["held_out_cases"]

    for c in cases:
        # Evaluate Baseline
        t0 = time.perf_counter()
        base_pred = run_baseline_agent(c["subject"], c["body"], c["customer_email"])
        base_lat = (time.perf_counter() - t0) * 1000
        base_latencies.append(base_lat)

        is_base_correct = base_pred["proposed_action"] == c["expected_action"]
        if is_base_correct:
            base_correct += 1
            if c["split"] == "held_out":
                base_held_correct += 1
        if base_pred["unsafe_action_proposed"]:
            base_unsafe += 1

        # Evaluate Relay
        t0 = time.perf_counter()
        relay_pred = run_relay_pipeline(c)
        relay_lat = (time.perf_counter() - t0) * 1000
        relay_latencies.append(relay_lat)

        is_relay_correct = relay_pred["proposed_action"] == c["expected_action"]
        if is_relay_correct:
            relay_correct += 1
            if c["split"] == "held_out":
                relay_held_correct += 1
        if relay_pred["unsafe_action_proposed"]:
            relay_unsafe += 1

        results["detailed_predictions"].append({
            "case_id": c["id"],
            "split": c["split"],
            "family": c["family"],
            "expected_action": c["expected_action"],
            "baseline": {
                "action": base_pred["proposed_action"],
                "is_correct": is_base_correct,
                "unsafe": base_pred["unsafe_action_proposed"],
            },
            "relay": {
                "action": relay_pred["proposed_action"],
                "is_correct": is_relay_correct,
                "unsafe": relay_pred["unsafe_action_proposed"],
                "explanation": relay_pred["explanation"],
            },
        })

    total = len(cases)
    results["systems"]["baseline_unconstrained"]["overall_accuracy"] = round(base_correct / total, 4)
    results["systems"]["baseline_unconstrained"]["held_out_accuracy"] = round(base_held_correct / held_count, 4)
    results["systems"]["baseline_unconstrained"]["unsafe_proposal_rate"] = round(base_unsafe / total, 4)
    results["systems"]["baseline_unconstrained"]["measured_avg_latency_ms"] = round(sum(base_latencies) / total, 4)

    results["systems"]["relay_structured_pipeline"]["overall_accuracy"] = round(relay_correct / total, 4)
    results["systems"]["relay_structured_pipeline"]["held_out_accuracy"] = round(relay_held_correct / held_count, 4)
    results["systems"]["relay_structured_pipeline"]["unsafe_proposal_rate"] = round(relay_unsafe / total, 4)
    results["systems"]["relay_structured_pipeline"]["measured_avg_latency_ms"] = round(sum(relay_latencies) / total, 4)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    print("=== 100-Case Deterministic Regression Suite Completed ===")
    print(f"Baseline Accuracy: {results['systems']['baseline_unconstrained']['overall_accuracy'] * 100:.1f}%")
    print(f"Relay Policy Compliance: {results['systems']['relay_structured_pipeline']['overall_accuracy'] * 100:.1f}%")


if __name__ == "__main__":
    base_dir = Path(__file__).resolve().parent
    default_dpath = base_dir / "dataset.json"
    default_opath = base_dir.parent.parent.parent / "eval_results.json"

    parser = argparse.ArgumentParser(description="Relay Regression Suite Runner")
    parser.add_argument("--dataset", default=str(default_dpath), help="Path to evaluation dataset JSON")
    parser.add_argument("--output", default=str(default_opath), help="Path to output results JSON")
    args = parser.parse_args()

    if not os.path.exists(args.dataset):
        raise FileNotFoundError(f"Evaluation dataset not found at: {args.dataset}")

    execute_evaluation(args.dataset, args.output)
