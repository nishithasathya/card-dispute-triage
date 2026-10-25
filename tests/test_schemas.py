from datetime import date, timedelta

import pytest
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


@pytest.mark.parametrize(
    "amount",
    ["-100", "0"],
)
def test_non_positive_amount_rejected(amount):
    data = valid_report()
    data["transaction_amount"] = amount

    with pytest.raises(ValidationError):
        DisputeReport(**data)


def test_report_before_transaction_rejected():
    data = valid_report()
    data["report_date"] = date(2026, 9, 30)

    with pytest.raises(ValidationError):
        DisputeReport(**data)


def test_future_transaction_date_rejected():
    data = valid_report()
    data["transaction_date"] = date.today() + timedelta(days=1)
    data["report_date"] = date.today() + timedelta(days=2)

    with pytest.raises(ValidationError):
        DisputeReport(**data)


def test_empty_case_id_rejected():
    data = valid_report()
    data["case_id"] = ""

    with pytest.raises(ValidationError):
        DisputeReport(**data)


def test_whitespace_case_id_rejected():
    data = valid_report()
    data["case_id"] = "   "

    with pytest.raises(ValidationError):
        DisputeReport(**data)


def test_empty_transaction_type_rejected():
    data = valid_report()
    data["transaction_type"] = "   "

    with pytest.raises(ValidationError):
        DisputeReport(**data)


def test_short_complaint_rejected():
    data = valid_report()
    data["complaint_description"] = "Fraud"

    with pytest.raises(ValidationError):
        DisputeReport(**data)


def test_alert_before_transaction_rejected():
    data = valid_report()
    data["alert_sent_date"] = date(2026, 9, 30)

    with pytest.raises(ValidationError):
        DisputeReport(**data)


def test_alert_noticed_before_sent_rejected():
    data = valid_report()
    data["alert_sent_date"] = date(2026, 10, 3)
    data["alert_noticed_date"] = date(2026, 10, 2)

    with pytest.raises(ValidationError):
        DisputeReport(**data)


def test_credentials_shared_after_report_rejected():
    data = valid_report()
    data["credentials_shared"] = True
    data["credentials_shared_date"] = date(2026, 10, 6)

    with pytest.raises(ValidationError):
        DisputeReport(**data)


def test_alert_noticed_after_report_rejected():
    data = valid_report()
    data["alert_sent_date"] = date(2026, 10, 2)
    data["alert_noticed_date"] = date(2026, 10, 6)

    with pytest.raises(ValidationError):
        DisputeReport(**data)