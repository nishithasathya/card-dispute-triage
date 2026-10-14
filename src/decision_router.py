from typing import Any


class DisputeDecisionRouter:
    """
    Routes dispute cases according to classification and evidence quality.

    This component recommends the next workflow action.
    It does not determine customer liability or make a final decision.
    """

    def route(self, triage_result: dict[str, Any]) -> dict[str, Any]:
        case_id = triage_result.get("case_id", "unknown")

        classification = triage_result.get("classification") or {}
        category = classification.get("category", "unknown")

        verification = triage_result.get("evidence_verification") or {}

        evidence = triage_result.get("evidence") or []
        valid_count = verification.get("valid_passages", 0)
        invalid_count = verification.get("invalid_passages", 0)

        reasons = []

        # Rule 1: Missing evidence requires escalation.
        if not evidence or valid_count == 0:
            action = "ESCALATE_FOR_EVIDENCE_REVIEW"
            reasons.append(
                "No structurally valid regulatory evidence is available."
            )

        # Rule 2: Invalid evidence must be reviewed.
        elif invalid_count > 0:
            action = "ESCALATE_FOR_EVIDENCE_REVIEW"
            reasons.append(
                "One or more retrieved passages failed structural validation."
            )

        # Rule 3: Uncertain classification requires further review.
        elif category == "unknown":
            action = "ESCALATE_FOR_CLASSIFICATION_REVIEW"
            reasons.append(
                "The dispute could not be confidently classified."
            )

        # Rule 4: Otherwise, prepare the case for a human reviewer.
        else:
            action = "PREPARE_FOR_HUMAN_REVIEW"
            reasons.append(
                "A preliminary category and structurally valid evidence "
                "are available for reviewer assessment."
            )

        # Every route remains subject to human review.
        return {
            "case_id": case_id,
            "recommended_action": action,
            "reasoning": reasons,
            "requires_human_review": True,
            "automated_liability_decision": False,
        }