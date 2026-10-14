from datetime import date
from decimal import Decimal

from src.classifier import DisputeClassifier
from src.schemas import DisputeReport, DisputeCategory


def make_report(description, transaction_type="card"):
    return DisputeReport(
        case_id="TEST-CLASSIFIER",
        transaction_date=date(2026, 10, 1),
        report_date=date(2026, 10, 5),
        transaction_amount=Decimal("2500.00"),
        transaction_type=transaction_type,
        customer_noticed_alert=True,
        credentials_shared=False,
        complaint_description=description,
    )


def test_classifies_upi_social_engineering():
    report = make_report(
        "A caller impersonating a bank employee tricked me into a payment.",
        transaction_type="UPI",
    )

    result = DisputeClassifier().classify(report)

    assert result.category == DisputeCategory.UPI_SOCIAL_ENGINEERING


def test_classifies_card_not_present():
    report = make_report(
        "I did not make this online purchase using my card.",
        transaction_type="online",
    )

    result = DisputeClassifier().classify(report)

    assert result.category == DisputeCategory.CARD_NOT_PRESENT


def test_classifies_skimming():
    report = make_report(
        "I suspect someone used a cloned card to make this transaction."
    )

    result = DisputeClassifier().classify(report)

    assert result.category == DisputeCategory.SKIMMING


def test_classifies_duplicate_charge():
    report = make_report(
        "The merchant charged me twice for the same purchase."
    )

    result = DisputeClassifier().classify(report)

    assert result.category == DisputeCategory.DUPLICATE_CHARGE


def test_classifies_merchant_dispute():
    report = make_report(
        "I have not received the refund promised by the merchant."
    )

    result = DisputeClassifier().classify(report)

    assert result.category == DisputeCategory.MERCHANT_DISPUTE


def test_unknown_when_description_is_unclear():
    report = make_report(
        "I do not recognise this transaction on my account."
    )

    result = DisputeClassifier().classify(report)

    assert result.category == DisputeCategory.UNKNOWN