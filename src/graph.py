from typing import TypedDict, Any

from langgraph.graph import StateGraph, START, END

from src.agents.dispute_analyst import DisputeAnalyst
from src.agents.evidence_analyst import EvidenceAnalyst
from src.decision_router import DisputeDecisionRouter
from src.schemas import DisputeReport


class DisputeState(TypedDict, total=False):
    report: DisputeReport
    case_id: str
    force_empty_evidence: bool
    dispute_analysis: dict[str, Any]
    evidence_analysis: dict[str, Any]
    final_result: dict[str, Any]


class DisputeAgentWorkflow:
    """
    Orchestrates dispute analysis and regulatory evidence retrieval.

    The workflow provides preliminary recommendations only.
    All liability decisions require human review.
    """

    def __init__(self):
        self.dispute_analyst = DisputeAnalyst()
        self.evidence_analyst = EvidenceAnalyst()
        self.decision_router = DisputeDecisionRouter()

        builder = StateGraph(DisputeState)

        builder.add_node(
            "dispute_analysis",
            self._analyse_dispute,
        )
        builder.add_node(
            "evidence_analysis",
            self._analyse_evidence,
        )
        builder.add_node(
            "combine_results",
            self._combine_results,
        )

        builder.add_edge(START, "dispute_analysis")
        builder.add_edge("dispute_analysis", "evidence_analysis")
        builder.add_edge("evidence_analysis", "combine_results")
        builder.add_edge("combine_results", END)

        self.graph = builder.compile()

    def _analyse_dispute(
        self,
        state: DisputeState,
    ) -> dict[str, Any]:
        """Classify the reported dispute without deciding liability."""

        report = state["report"]
        analysis = self.dispute_analyst.analyze(report)

        return {
            "case_id": report.case_id,
            "dispute_analysis": analysis,
        }

    def _analyse_evidence(
        self,
        state: DisputeState,
    ) -> dict[str, Any]:
        """Retrieve evidence or use the controlled empty-evidence test."""

        report = state["report"]

        force_empty_evidence = state.get(
            "force_empty_evidence",
            False,
        )

        analysis = self.evidence_analyst.analyze(
            report,
            force_empty_evidence=force_empty_evidence,
        )

        return {
            "evidence_analysis": analysis,
        }

    @staticmethod
    def _requires_impersonation_escalation(
        dispute: dict[str, Any],
    ) -> bool:
        """
        Detect possible credential-sharing incidents involving impersonation.

        This conservative rule triggers human review; it does not determine
        negligence or customer liability.
        """

        if not dispute.get("credentials_shared", False):
            return False

        complaint = str(
            dispute.get("complaint_description", "")
        ).casefold()

        transaction_type = str(
            dispute.get("transaction_type", "")
        ).casefold()

        combined_text = f"{complaint} {transaction_type}"

        indicators = (
            "impersonat",
            "pretending to be the bank",
            "pretended to be the bank",
            "posing as the bank",
            "fake bank",
            "bank representative",
            "bank employee",
            "caller claiming to be from the bank",
            "someone claiming to be from the bank",
            "otp",
            "one-time password",
            "one time password",
            "social engineering",
            "scammer",
            "fraudster",
        )

        return any(
            indicator in combined_text
            for indicator in indicators
        )

    def _combine_results(
        self,
        state: DisputeState,
    ) -> dict[str, Any]:
        """Combine classification and evidence, then select a safe route."""

        dispute = state["dispute_analysis"]
        evidence_result = state["evidence_analysis"]

        classification = dispute.get("classification") or {}
        category = classification.get("category", "unknown")

        evidence = evidence_result.get("evidence") or []
        verification = evidence_result.get("evidence_verification") or {}

        all_evidence_valid = verification.get("all_valid") is True
        evidence_missing = not evidence
        evidence_invalid = not all_evidence_valid

        prompt_injection_detected = (
            evidence_result.get("prompt_injection_detected") is True
        )

        impersonation_escalation = (
            self._requires_impersonation_escalation(dispute)
        )

        escalation_reasons = [
            "Human review is mandatory before any liability decision."
        ]

        if category == "unknown":
            escalation_reasons.append(
                "The dispute classification is uncertain."
            )

        if dispute.get("credentials_shared", False):
            escalation_reasons.append(
                "Reported credential sharing requires assessment of "
                "the circumstances and applicable provisions."
            )

        if impersonation_escalation:
            escalation_reasons.append(
                "Possible OTP sharing with a person impersonating a "
                "bank representative requires explicit human escalation. "
                "The reviewer must assess both the potentially relevant "
                "customer-reporting-delay provisions and the credential-"
                "sharing or customer-negligence provisions. OTP sharing "
                "alone must not determine liability."
            )

        if prompt_injection_detected:
            escalation_reasons.append(
                "Potential prompt-injection wording was detected in the "
                "complaint. The original complaint requires human review."
            )

        if evidence_missing:
            escalation_reasons.append(
                "No regulatory evidence was retrieved."
            )

        if evidence_invalid:
            escalation_reasons.append(
                "Evidence metadata failed structural verification."
            )

        needs_escalation = (
            evidence_missing
            or evidence_invalid
            or category == "unknown"
            or impersonation_escalation
            or prompt_injection_detected
        )

        result = {
            "case_id": state["case_id"],
            "status": (
                "review_required"
                if needs_escalation
                else "evidence_collected"
            ),
            "transaction_amount": dispute.get("transaction_amount"),
            "transaction_type": dispute.get("transaction_type"),
            "transaction_date": dispute.get("transaction_date"),
            "report_date": dispute.get("report_date"),
            "reporting_delay_calendar_days": dispute.get(
                "reporting_delay_calendar_days"
            ),
            "classification": classification,
            "evidence": evidence,
            "evidence_verification": verification,
            "prompt_injection_detected": prompt_injection_detected,
            "recommendation": (
                "No liability determination has been made. A human "
                "reviewer must assess the case facts and applicable "
                "regulatory provisions."
            ),
            "requires_human_review": True,
            "escalation_required": needs_escalation,
            "escalation_reason": " ".join(escalation_reasons),
        }

        # Route in priority order. Missing or structurally invalid
        # evidence must not be treated as a classification-only problem.
        if evidence_missing or evidence_invalid:
            routing = {
                "case_id": state["case_id"],
                "recommended_action": "ESCALATE_FOR_EVIDENCE_REVIEW",
                "reasoning": [
                    (
                        "Regulatory evidence is missing or failed "
                        "structural verification. A reviewer must "
                        "assess the evidence gap."
                    )
                ],
                "requires_human_review": True,
                "automated_liability_decision": False,
                "route": "ESCALATE_FOR_EVIDENCE_REVIEW",
            }

        elif prompt_injection_detected:
            routing = {
                "case_id": state["case_id"],
                "recommended_action": "ESCALATE_FOR_HUMAN_REVIEW",
                "reasoning": [
                    (
                        "Potential prompt-injection wording was detected. "
                        "The complaint must be reviewed by a human, and "
                        "its instructions must not control classification "
                        "or liability decisions."
                    )
                ],
                "requires_human_review": True,
                "automated_liability_decision": False,
                "route": "ESCALATE_FOR_HUMAN_REVIEW",
                "escalation_reason": result["escalation_reason"],
            }

        elif impersonation_escalation:
            routing = {
                "case_id": state["case_id"],
                "recommended_action": "ESCALATE_FOR_HUMAN_REVIEW",
                "reasoning": [
                    (
                        "Possible credential sharing involving "
                        "impersonation requires review of the relevant "
                        "reporting-delay and credential-sharing provisions."
                    )
                ],
                "requires_human_review": True,
                "automated_liability_decision": False,
                "route": "ESCALATE_FOR_HUMAN_REVIEW",
                "escalation_reason": result["escalation_reason"],
            }

        else:
            routing = self.decision_router.route(result)

            if not isinstance(routing, dict):
                routing = {
                    "case_id": state["case_id"],
                    "recommended_action": "ESCALATE_FOR_HUMAN_REVIEW",
                    "reasoning": [
                        "The routing component returned an invalid result."
                    ],
                    "requires_human_review": True,
                    "automated_liability_decision": False,
                    "route": "ESCALATE_FOR_HUMAN_REVIEW",
                }

        # Safety invariants: this workflow must never decide liability.
        routing["requires_human_review"] = True
        routing["automated_liability_decision"] = False

        result["routing"] = routing

        return {
            "final_result": result,
        }

    def run(
        self,
        report: DisputeReport,
        *,
        force_empty_evidence: bool = False,
    ) -> dict[str, Any]:
        """
        Execute the workflow for one dispute.

        force_empty_evidence is intended for controlled tests.
        Leave it False during normal operation.
        """

        output = self.graph.invoke(
            {
                "report": report,
                "case_id": report.case_id,
                "force_empty_evidence": force_empty_evidence,
            }
        )

        return output["final_result"]