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

        dispute_facts = triage_result.get("dispute_analysis") or {}

        reporting_delay = dispute_facts.get(
            "reporting_delay_calendar_days"
        )

        credentials_shared = dispute_facts.get("credentials_shared")
        complaint = str(
            dispute_facts.get("complaint_description", "")
        ).casefold()

        impersonation_indicators = (
            "impersonat",
            "pretending to be",
            "posing as",
            "caller claiming to be",
            "pretend to be",
        )

        impersonation_detected = any(
            indicator in complaint
            for indicator in impersonation_indicators
        )

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

        # Rule 3: Delayed reporting combined with shared credentials and
        # possible impersonation requires explicit human escalation.
        elif (
            reporting_delay is not None
            and reporting_delay >= 14
            and credentials_shared is True
            and impersonation_detected
        ):
            action = "ESCALATE_FOR_HUMAN_REVIEW"
            reasons.append(
                "The report describes delayed reporting, shared credentials, "
                "and possible impersonation. These circumstances require "
                "individual assessment by a human reviewer."
            )
            reasons.append(
                "Do not infer customer negligence or determine liability "
                "from these facts alone. The reviewer must examine the "
                "applicable regulatory and bank-policy provisions."
            )

        # Rule 4: Uncertain classification requires further review.
        elif category == "unknown":
            action = "ESCALATE_FOR_CLASSIFICATION_REVIEW"
            reasons.append(
                "The dispute could not be confidently classified."
            )

        # Rule 5: Otherwise, prepare the case for a human reviewer.
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