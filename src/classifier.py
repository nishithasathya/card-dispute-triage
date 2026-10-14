from src.schemas import DisputeReport, DisputeClassification, DisputeCategory


class DisputeClassifier:
    """Rule-based classifier for payment disputes."""

    def classify(self, report: DisputeReport) -> DisputeClassification:
        description = report.complaint_description.lower()
        transaction_type = report.transaction_type.lower()

        # 1. Duplicate charges — check FIRST
        if any(
            phrase in description
            for phrase in [
                "duplicate",
                "charged twice",
                "charged me twice",
                "double charged",
                "same transaction twice",
            ]
        ):
            category = DisputeCategory.DUPLICATE_CHARGE
            explanation = (
                "Possible duplicate charge detected. "
                "Transaction records require verification."
            )

        # 2. UPI and social engineering
        elif (
            "upi" in transaction_type
            or "upi" in description
            or "social engineering" in description
            or "impersonat" in description
            or "pretending to be the bank" in description
            or "pretending to be a bank" in description
            or "tricked me into a payment" in description
        ):
            category = DisputeCategory.UPI_SOCIAL_ENGINEERING
            explanation = (
                "Possible UPI or social-engineering dispute detected. "
                "Human review is required."
            )

        # 3. Suspected card skimming
        elif any(
            phrase in description
            for phrase in [
                "skimming",
                "cloned card",
                "card cloning",
                "card was cloned",
            ]
        ):
            category = DisputeCategory.SKIMMING
            explanation = (
                "Possible card skimming or cloning detected. "
                "The transaction mechanism requires verification."
            )

        # 4. Card-not-present transactions
        elif (
            "online" in transaction_type
            or "e-commerce" in transaction_type
            or "ecommerce" in transaction_type
            or "card-not-present" in description
            or "card not present" in description
            or "online purchase" in description
        ):
            category = DisputeCategory.CARD_NOT_PRESENT
            explanation = (
                "Possible card-not-present transaction. "
                "The transaction channel should be verified."
            )

        # 5. Merchant disputes
        elif any(
            phrase in description
            for phrase in [
                "merchant",
                "refund",
                "goods not received",
                "service not received",
                "product not received",
            ]
        ):
            category = DisputeCategory.MERCHANT_DISPUTE
            explanation = (
                "Possible merchant or refund dispute. "
                "Supporting transaction records should be reviewed."
            )

        # 6. Unknown category
        else:
            category = DisputeCategory.UNKNOWN
            explanation = (
                "Insufficient information for confident classification. "
                "Human review is required."
            )

        return DisputeClassification(
            category=category,
            explanation=explanation,
        )