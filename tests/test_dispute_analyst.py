from datetime import date

from src.agents.dispute_analyst import DisputeAnalyst
from src.schemas import DisputeReport


def make_report(**overrides):
    data = {
        "case_id": "AGENT-001",
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


def test_agent_returns_case_id():
    agent = DisputeAnalyst()

    result = agent.analyze(make_report())

    assert result["case_id"] == "AGENT-001"


def test_agent_calculates_reporting_delay():
    agent = DisputeAnalyst()

    result = agent.analyze(make_report())

    assert result["reporting_delay_calendar_days"] == 4


def test_agent_includes_classification():
    agent = DisputeAnalyst()

    result = agent.analyze(make_report())

    assert "category" in result["classification"]
    assert "explanation" in result["classification"]


def test_agent_always_requires_human_review():
    agent = DisputeAnalyst()

    result = agent.analyze(make_report())

    assert result["requires_human_review"] is True


def test_agent_preserves_credential_sharing_fact():
    agent = DisputeAnalyst()

    report = make_report(credentials_shared=True)
    result = agent.analyze(report)

    assert result["credentials_shared"] is True