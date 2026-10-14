import pytest
from datetime import date
from pydantic import ValidationError

from src.schemas import DisputeReport


def valid_report():
    return {
        "case_id": "CASE-001",
        "transaction_date": date(2026, 10, 1),
        "report_date": date(2026, 10, 5),
        "transaction_amount": "2500.00",
        "transaction_type": "card",
        "customer_noticed_alert": True,
        "credentials_shared": False,
        "complaint_description": (
            "I noticed an unauthorised card transaction."
        ),
    }


def test_valid_report():
    report = DisputeReport(**valid_report())

    assert report.case_id == "CASE-001"


def test_negative_amount_rejected():
    data = valid_report()
    data["transaction_amount"] = "-100"

    with pytest.raises(ValidationError):
        DisputeReport(**data)


def test_report_before_transaction_rejected():
    data = valid_report()
    data["report_date"] = date(2026, 9, 30)

    with pytest.raises(ValidationError):
        DisputeReport(**data)


def test_empty_case_id_rejected():
    data = valid_report()
    data["case_id"] = ""

    with pytest.raises(ValidationError):
        DisputeReport(**data)