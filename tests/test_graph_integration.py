from datetime import date

from src.graph import DisputeAgentWorkflow
from src.schemas import DisputeReport


def test_graph_runs_with_real_components():
    report = DisputeReport(
        case_id="INTEGRATION-001",
        transaction_date=date(2026, 10, 1),
        report_date=date(2026, 10, 5),
        transaction_amount="2500.00",
        transaction_type="online",
        customer_noticed_alert=True,
        credentials_shared=False,
        complaint_description=(
            "I did not make this online purchase using my card."
        ),
    )

    workflow = DisputeAgentWorkflow()
    result = workflow.run(report)

    assert result["case_id"] == "INTEGRATION-001"
    assert result["reporting_delay_calendar_days"] == 4
    assert "classification" in result
    assert "evidence" in result
    assert "evidence_verification" in result
    assert "routing" in result
    assert result["requires_human_review"] is True
    assert result["routing"]["automated_liability_decision"] is False