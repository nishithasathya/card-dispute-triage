from datetime import date
from unittest.mock import MagicMock

from src.graph import DisputeAgentWorkflow
from src.schemas import DisputeReport


def make_report(**overrides):
    data = {
        "case_id": "GRAPH-001",
        "transaction_date": date(2026, 10, 1),
        "report_date": date(2026, 10, 5),
        "transaction_amount": "2500.00",
        "transaction_type": "online",
        "customer_noticed_alert": True,
        "credentials_shared": False,
        "complaint_description": (
            "I did not make this online purchase using my card."
        ),
    }

    data.update(overrides)

    return DisputeReport(**data)


def make_workflow():
    workflow = DisputeAgentWorkflow.__new__(
        DisputeAgentWorkflow
    )

    workflow.dispute_analyst = MagicMock()
    workflow.evidence_analyst = MagicMock()

    workflow.dispute_analyst.analyze.return_value = {
        "case_id": "GRAPH-001",
        "transaction_amount": "2500.00",
        "transaction_type": "online",
        "transaction_date": "2026-10-01",
        "report_date": "2026-10-05",
        "reporting_delay_calendar_days": 4,
        "credentials_shared": False,
        "classification": {
            "category": "card_not_present",
            "explanation": "Possible online card dispute.",
        },
    }

    workflow.evidence_analyst.analyze.return_value = {
        "evidence": [
            {
                "source": "rbi_customer_protection_2017.pdf",
                "page": 3,
                "chunk_id": "rbi_customer_protection_2017.pdf:p3:c1",
                "text": (
                    "Illustrative evidence passage for testing."
                ),
            }
        ],
        "evidence_verification": {
            "total_passages": 1,
            "valid_passages": 1,
            "invalid_passages": 0,
            "all_valid": True,
            "results": [],
        },
    }

    workflow.decision_router = MagicMock()

    workflow.decision_router.route.return_value = {
        "case_id": "GRAPH-001",
        "recommended_action": "PREPARE_FOR_HUMAN_REVIEW",
        "reasoning": ["Evidence is available for review."],
        "requires_human_review": True,
        "automated_liability_decision": False,
    }

    return workflow


def test_graph_can_be_constructed():
    workflow = DisputeAgentWorkflow()

    assert workflow.graph is not None


def test_dispute_node_returns_analysis():
    workflow = make_workflow()

    result = workflow._analyse_dispute(
        {"report": make_report()}
    )

    assert result["case_id"] == "GRAPH-001"
    assert result["dispute_analysis"]["classification"]["category"] == (
        "card_not_present"
    )


def test_evidence_node_returns_evidence():
    workflow = make_workflow()

    result = workflow._analyse_evidence(
        {"report": make_report()}
    )

    assert "evidence_analysis" in result
    assert len(result["evidence_analysis"]["evidence"]) == 1


def test_combined_result_requires_human_review():
    workflow = make_workflow()

    result = workflow._combine_results(
        {
            "case_id": "GRAPH-001",
            "dispute_analysis": (
                workflow.dispute_analyst.analyze.return_value
            ),
            "evidence_analysis": (
                workflow.evidence_analyst.analyze.return_value
            ),
        }
    )["final_result"]

    assert result["requires_human_review"] is True
    assert result["routing"]["automated_liability_decision"] is False


def test_combined_result_includes_reporting_delay():
    workflow = make_workflow()

    result = workflow._combine_results(
        {
            "case_id": "GRAPH-001",
            "dispute_analysis": (
                workflow.dispute_analyst.analyze.return_value
            ),
            "evidence_analysis": (
                workflow.evidence_analyst.analyze.return_value
            ),
        }
    )["final_result"]

    assert result["reporting_delay_calendar_days"] == 4