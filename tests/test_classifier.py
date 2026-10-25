from datetime import date
from decimal import Decimal

from src.classifier import DisputeClassifier
from src.schemas import DisputeCategory, DisputeReport


def make_report(
    description,
    transaction_type="card",
    credentials_shared=False,
):
    return DisputeReport(
        case_id="TEST-CLASSIFIER",
        transaction_date=date(2026, 10, 1),
        report_date=date(2026, 10, 5),
        transaction_amount=Decimal("2500.00"),
        transaction_type=transaction_type,
        customer_noticed_alert=True,
        credentials_shared=credentials_shared,
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


def test_card_otp_impersonation_is_not_misclassified_as_upi():
    report = make_report(
        (
            "A caller impersonating the bank asked me to share my OTP. "
            "I shared it and later discovered an unauthorised card transaction."
        ),
        transaction_type="CARD",
        credentials_shared=True,
    )

    result = DisputeClassifier().classify(report)

    assert result.category == DisputeCategory.UNKNOWN
    assert "Human review is required" in result.explanation


def test_upi_otp_impersonation_is_classified_as_social_engineering():
    report = make_report(
        (
            "A caller impersonating the bank asked me to share my OTP "
            "for a UPI transaction."
        ),
        transaction_type="UPI",
        credentials_shared=True,
    )

    result = DisputeClassifier().classify(report)

    assert result.category == DisputeCategory.UPI_SOCIAL_ENGINEERING


def test_explicit_upi_indicator_is_recognised():
    report = make_report(
        "Someone tricked me into approving a payment through UPI.",
        transaction_type="payment",
    )

    result = DisputeClassifier().classify(report)

    assert result.category == DisputeCategory.UPI_SOCIAL_ENGINEERING