import json
import traceback
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from evaluation.evidence_scoring import score_evaluation_record
from evaluation.metrics import calculate_metrics
from src.graph import DisputeAgentWorkflow
from src.schemas import DisputeReport


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCENARIOS_PATH = PROJECT_ROOT / "evaluation" / "scenarios.json"
RESULTS_DIR = PROJECT_ROOT / "evaluation" / "results"


def load_scenarios() -> list[dict[str, Any]]:
    """Load and validate the evaluation scenario file."""

    with SCENARIOS_PATH.open("r", encoding="utf-8") as file:
        scenarios = json.load(file)

    if not isinstance(scenarios, list):
        raise ValueError("Evaluation scenarios must be a JSON list.")

    for index, scenario in enumerate(scenarios):
        if not isinstance(scenario, dict):
            raise ValueError(
                f"Scenario at index {index} must be a JSON object."
            )

        if not scenario.get("id"):
            raise ValueError(
                f"Scenario at index {index} is missing its id."
            )

    return scenarios


def build_report(scenario: dict[str, Any]) -> DisputeReport:
    """Convert an evaluation scenario into the validated input schema."""

    transaction_date = date(2026, 1, 1)
    delay_days = scenario.get("transaction_delay_days", 1)
    report_date = transaction_date + timedelta(days=delay_days)

    amount = scenario.get("invalid_amount", "2500.00")

    return DisputeReport(
        case_id=scenario["id"],
        transaction_date=transaction_date,
        report_date=report_date,
        transaction_amount=amount,
        transaction_type=scenario["transaction_type"],
        customer_noticed_alert=scenario["customer_noticed_alert"],
        credentials_shared=scenario["credentials_shared"],
        alert_sent_date=(
            date.fromisoformat(scenario["alert_sent_date"])
            if scenario.get("alert_sent_date")
            else None
        ),
        alert_noticed_date=(
            date.fromisoformat(scenario["alert_noticed_date"])
            if scenario.get("alert_noticed_date")
            else None
        ),
        credentials_shared_date=(
            date.fromisoformat(scenario["credentials_shared_date"])
            if scenario.get("credentials_shared_date")
            else None
        ),
        complaint_description=scenario["description"],
    )


def evaluate_scenario(
    scenario: dict[str, Any],
    workflow: DisputeAgentWorkflow,
) -> dict[str, Any]:
    """Evaluate one scenario and retain diagnostic information."""

    record: dict[str, Any] = {
        "scenario_id": scenario["id"],
        "scenario_name": scenario["name"],
        "risk": scenario.get("risk", "unspecified"),
        "expected_category": scenario.get("expected_category"),
        "expected_human_review": scenario.get("expected_human_review"),
        "expected_escalation": scenario.get("expected_escalation"),
        "expected_validation_failure": scenario.get(
            "expected_validation_failure",
            False,
        ),
        "expected_prompt_injection": scenario.get(
            "expected_prompt_injection",
            False,
        ),
        "validation_failed": False,
        "predicted_category": None,
        "classification": {},
        "recommendation": None,
        "requires_human_review": True,
        "evidence": [],
        "evidence_verification": None,
        "routing": {},
        "automated_liability_decision": False,
        "prompt_injection_detected": False,
        "execution_error": None,
    }

    # Step 1: Validate the report.
    try:
        report = build_report(scenario)

    except (ValidationError, ValueError, KeyError, TypeError) as exc:
        record.update(
            {
                "validation_failed": True,
                "validation_error": str(exc),
                "status": "validation_failed",
            }
        )
        return record

    # Step 2: Execute the workflow.
    try:
        result = workflow.run(
            report,
            force_empty_evidence=scenario.get(
                "force_empty_evidence",
                False,
            ),
        )

        classification = result.get("classification") or {}
        routing = result.get("routing") or {}
        evidence = result.get("evidence") or []

        # The graph is expected to expose this flag at the top level.
        # If it is absent, the record defaults to False, so the evaluation
        # will not silently claim that injection was detected.
        injection_detected = (
            result.get("prompt_injection_detected") is True
        )

        record.update(
            {
                "predicted_category": classification.get("category"),
                "classification": classification,
                "recommendation": result.get("recommendation"),
                "requires_human_review": result.get(
                    "requires_human_review",
                    True,
                ),
                "evidence": evidence,
                "evidence_verification": result.get(
                    "evidence_verification"
                ),
                "routing": routing,
                "automated_liability_decision": routing.get(
                    "automated_liability_decision",
                    result.get("automated_liability_decision", False),
                ),
                "prompt_injection_detected": injection_detected,
                "status": result.get("status"),
                "reporting_delay_calendar_days": result.get(
                    "reporting_delay_calendar_days"
                ),
                "escalation_required": result.get(
                    "escalation_required"
                ),
                "escalation_reason": (
                    result.get("escalation_reason")
                    or routing.get("escalation_reason")
                ),
            }
        )

        record = score_evaluation_record(record, scenario)

    except Exception as exc:
        record.update(
            {
                "predicted_category": None,
                "classification": {},
                "recommendation": None,
                "requires_human_review": True,
                "evidence": [],
                "evidence_verification": None,
                "routing": {},
                "automated_liability_decision": False,
                "prompt_injection_detected": False,
                "execution_error": f"{type(exc).__name__}: {exc}",
                "traceback": traceback.format_exc(),
            }
        )

    return record


def print_classification_mismatches(
    records: list[dict[str, Any]],
) -> None:
    """Print labelled scenarios whose predictions do not match."""

    print("\n--- Classification Mismatches ---")
    mismatches = 0

    for record in records:
        expected = record.get("expected_category")
        predicted = record.get("predicted_category")

        if expected is not None and expected != predicted:
            mismatches += 1
            print(
                f"\n{record['scenario_id']} - "
                f"{record['scenario_name']}"
            )
            print(f"  Expected:  {expected}")
            print(f"  Predicted: {predicted}")

            classification = record.get("classification") or {}
            print(
                "  Classification details: "
                f"{json.dumps(classification, ensure_ascii=False)}"
            )

            print(
                "  Transaction type: "
                f"{record.get('transaction_type', 'see scenario file')}"
            )

    if mismatches == 0:
        print("No classification mismatches among labelled predictions.")

    print(f"Total classification mismatches: {mismatches}")


def print_scenarios_without_evidence(
    records: list[dict[str, Any]],
) -> None:
    """Print valid scenarios for which no evidence was returned."""

    print("\n--- Scenarios Without Evidence ---")
    missing_count = 0

    for record in records:
        if (
            record.get("validation_failed") is not True
            and record.get("execution_error") is None
            and not record.get("evidence")
        ):
            missing_count += 1
            print(
                f"{record['scenario_id']} - "
                f"{record['scenario_name']}"
            )

    if missing_count == 0:
        print("No successfully executed valid scenarios lacked evidence.")

    print(f"Total scenarios without evidence: {missing_count}")


def print_safety_checks(records: list[dict[str, Any]]) -> None:
    """Check human review, liability safety, and escalation routing."""

    print("\n--- Safety Checks ---")
    warnings = 0

    for record in records:
        if (
            record.get("validation_failed") is True
            or record.get("execution_error") is not None
        ):
            continue

        scenario_id = record["scenario_id"]

        if record.get("requires_human_review") is not True:
            warnings += 1
            print(
                f"WARNING: {scenario_id} did not require human review."
            )

        if record.get("automated_liability_decision") is True:
            warnings += 1
            print(
                f"WARNING: {scenario_id} reported an automated "
                "liability decision."
            )

        expected_escalation = record.get("expected_escalation")
        routing = record.get("routing") or {}
        route = routing.get("route", "")

        if (
            expected_escalation == "human_review"
            and route != "ESCALATE_FOR_HUMAN_REVIEW"
        ):
            warnings += 1
            print(
                f"WARNING: {scenario_id} expected human escalation, "
                f"but route was {route!r}."
            )

        if (
            expected_escalation == "evidence_review"
            and route != "ESCALATE_FOR_EVIDENCE_REVIEW"
        ):
            warnings += 1
            print(
                f"WARNING: {scenario_id} expected evidence-review "
                f"escalation, but route was {route!r}."
            )

    if warnings == 0:
        print("No safety-check warnings detected.")

    print(f"Total safety-check warnings: {warnings}")


def print_prompt_injection_checks(
    records: list[dict[str, Any]],
) -> None:
    """Print detection and escalation results for labelled injection cases."""

    print("\n--- Prompt Injection Checks ---")

    cases = [
        record
        for record in records
        if record.get("expected_prompt_injection") is True
    ]

    if not cases:
        print(
            "No scenarios are labelled with expected_prompt_injection=true. "
            "Detection metrics cannot be assessed."
        )
        return

    for record in cases:
        print(
            f"{record['scenario_id']} - {record['scenario_name']}: "
            f"detected={record.get('prompt_injection_detected')}, "
            f"route={(record.get('routing') or {}).get('route')}, "
            f"human_review={record.get('requires_human_review')}"
        )


def print_execution_errors(records: list[dict[str, Any]]) -> None:
    """Print every scenario execution error and its traceback."""

    errors = [
        record
        for record in records
        if record.get("execution_error") is not None
    ]

    print("\n--- Execution Errors ---")

    if not errors:
        print("No execution errors.")
        return

    for record in errors:
        print(
            f"\n{record['scenario_id']} - "
            f"{record['scenario_name']}"
        )
        print(record["execution_error"])
        print(record.get("traceback", "Traceback unavailable"))


def main() -> None:
    """Run the evaluation suite and save a JSON report."""

    scenarios = load_scenarios()
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    workflow = DisputeAgentWorkflow()

    records = [
        evaluate_scenario(scenario, workflow)
        for scenario in scenarios
    ]

    metrics = calculate_metrics(records)

    report = {
        "scenario_count": len(scenarios),
        "metrics": metrics,
        "results": records,
    }

    output_path = RESULTS_DIR / "evaluation_report.json"

    with output_path.open("w", encoding="utf-8") as file:
        json.dump(report, file, indent=2, ensure_ascii=False)

    print("\n=== CARD DISPUTE EVALUATION ===")
    print(f"Scenarios: {len(scenarios)}")
    print(f"Report: {output_path}")

    print("\n--- Metrics ---")

    for name, value in metrics.items():
        if isinstance(value, (int, float)):
            print(f"{name}: {value:.3f}")
        else:
            print(f"{name}: {value}")

    validation_failures = sum(
        record.get("validation_failed") is True
        for record in records
    )

    execution_errors = sum(
        record.get("execution_error") is not None
        for record in records
    )

    expected_validation_failures = sum(
        record.get("expected_validation_failure") is True
        for record in records
    )

    print(f"\nValidation failures: {validation_failures}")
    print(
        "Expected validation failures in scenarios: "
        f"{expected_validation_failures}"
    )
    print(f"Execution errors: {execution_errors}")

    print_classification_mismatches(records)
    print_scenarios_without_evidence(records)
    print_safety_checks(records)
    print_prompt_injection_checks(records)
    print_execution_errors(records)


if __name__ == "__main__":
    main()