"""Rule-based dispute classification with conservative fallbacks."""

import re
from typing import Any

from src.schemas import DisputeCategory, DisputeClassification


class DisputeClassifier:
    """Classify disputes using explicit indicators and conservative fallbacks."""

    @staticmethod
    def _normalise(value: Any) -> str:
        if value is None:
            return ""
        return re.sub(r"\s+", " ", str(value).lower()).strip()

    @staticmethod
    def _contains(text: str, patterns: list[str]) -> bool:
        return any(
            re.search(pattern, text, re.IGNORECASE)
            for pattern in patterns
        )

    @staticmethod
    def _result(
        category: DisputeCategory,
        explanation: str,
    ) -> DisputeClassification:
        return DisputeClassification(
            category=category,
            explanation=explanation,
        )

    def classify(self, report: Any) -> DisputeClassification:
        """Classify a validated dispute report."""

        transaction_type = self._normalise(
            getattr(report, "transaction_type", "")
        )
        complaint = self._normalise(
            getattr(report, "complaint_description", "")
        )

        if not complaint:
            return self._result(
                DisputeCategory.UNKNOWN,
                "The complaint is empty or unclear. Human review is required.",
            )

        # 1. Duplicate charges take priority over merchant disputes.
        if self._contains(
            complaint,
            [
                r"\bcharged twice\b",
                r"\bdebited twice\b",
                r"\bduplicate(?:d)? charge\b",
                r"\btransaction appears twice\b",
                r"\bsame transaction.{0,40}\b(twice|two times)\b",
                r"\bdouble[- ]charged\b",
                r"\bcharged me twice\b",
            ],
        ):
            return self._result(
                DisputeCategory.DUPLICATE_CHARGE,
                "The complaint indicates a possible duplicate charge.",
            )

        # 2. Card skimming or cloning.
        if self._contains(
            complaint,
            [
                r"\bskim(?:med|ming)?\b",
                r"\bclon(?:e|ed|ing)\s+(?:my\s+)?card\b",
                r"\bcard cloning\b",
                r"\bcopied my card\b",
                r"\bcopied card details\b",
            ],
        ):
            return self._result(
                DisputeCategory.SKIMMING,
                "The complaint indicates possible card skimming or cloning.",
            )

        # 3. Merchant disputes.
        if self._contains(
            complaint,
            [
                r"\brefund\b",
                r"\bnever delivered\b",
                r"\bnot delivered\b",
                r"\bnever received\b",
                r"\bnot received\b",
                r"\bincorrect amount\b",
                r"\bwrong amount\b",
                r"\bwrong price\b",
                r"\bservice not provided\b",
                r"\bservice not received\b",
                r"\border never arrived\b",
                r"\bmerchant.{0,50}\b(charged|refund|dispute)\b",
                r"\bpaid for.{0,50}\b(not received|never arrived|not delivered)\b",
            ],
        ):
            return self._result(
                DisputeCategory.MERCHANT_DISPUTE,
                "The complaint indicates a possible merchant, delivery, "
                "refund, or transaction-amount dispute.",
            )

        # 4. Detect the payment channel.
        upi_channel = self._contains(
            transaction_type,
            [
                r"\bupi\b",
                r"\bunified payments interface\b",
            ],
        ) or self._contains(
            complaint,
            [
                r"\bupi\b",
                r"\bunified payments interface\b",
            ],
        )

        card_channel = self._contains(
            transaction_type,
            [
                r"\bcard\b",
                r"\bcredit card\b",
                r"\bdebit card\b",
            ],
        ) or self._contains(
            complaint,
            [
                r"\bcard transaction\b",
                r"\bonline card transaction\b",
                r"\bcard purchase\b",
                r"\busing my card\b",
                r"\bwith my card\b",
                r"\bcredit card\b",
                r"\bdebit card\b",
            ],
        )

        # 5. Detect social-engineering indicators.
        social_engineering = self._contains(
            complaint,
            [
                r"\bimpersonat(?:e|ed|ing|or)\b",
                r"\bpretend(?:ing)? to be\b",
                r"\bclaiming to be from my bank\b",
                r"\bcaller.{0,60}\b(bank|bank employee|bank representative)\b",
                r"\bbank employee\b",
                r"\bscammer\b",
                r"\bscam(?:med|ming)?\b",
                r"\btricked me into making a payment\b",
                r"\btricked me into approving a payment\b",
                r"\bconvinced me to reveal my credentials\b",
                r"\bshared my otp\b",
                r"\bshared (?:the )?otp\b",
                r"\brevealed my credentials\b",
                r"\brevealed my otp\b",
                r"\basked for my otp\b",
                r"\bremote access\b",
            ],
        )

        # Do not infer UPI from social engineering alone.
        # Card transactions involving impersonation remain unclassified
        # because the exact fraud mechanism needs human review.
        if social_engineering:
            if upi_channel and not card_channel:
                return self._result(
                    DisputeCategory.UPI_SOCIAL_ENGINEERING,
                    "The complaint indicates possible UPI social engineering. "
                    "Human review is required.",
                )

            if card_channel:
                return self._result(
                    DisputeCategory.UNKNOWN,
                    "The complaint involves possible social engineering and "
                    "a card transaction. Human review is required before "
                    "classification.",
                )

            return self._result(
                DisputeCategory.UNKNOWN,
                "Possible social engineering was reported, but the payment "
                "channel is unclear. Human review is required.",
            )

        # 6. Detect unauthorised transactions.
        unauthorised = self._contains(
            complaint,
            [
                r"\bunauthori[sz]ed\b",
                r"\bdid not authori[sz]e\b",
                r"\bdidn't authori[sz]e\b",
                r"\bdid not make\b",
                r"\bdidn't make\b",
                r"\bdo not recognise\b",
                r"\bdon't recognise\b",
                r"\bdo not recognize\b",
                r"\bdon't recognize\b",
                r"\bunfamiliar transaction\b",
                r"\bnot my purchase\b",
                r"\bi found an online card transaction\b",
            ],
        )

        online_channel = self._contains(
            transaction_type,
            [
                r"\bonline\b",
                r"\be[- ]?commerce\b",
                r"\binternet\b",
                r"\bweb purchase\b",
                r"\bcard_not_present\b",
            ],
        )

        online_purchase = self._contains(
            complaint,
            [
                r"\bonline purchase\b",
                r"\bonline transaction\b",
                r"\bonline card transaction\b",
                r"\bonline payment\b",
                r"\binternet purchase\b",
                r"\be[- ]?commerce\b",
                r"\bweb purchase\b",
            ],
        )

        explicit_card_complaint = self._contains(
            complaint,
            [
                r"\bcard transaction\b",
                r"\bcard purchase\b",
                r"\busing my card\b",
                r"\bwith my card\b",
            ],
        )

        if unauthorised and (
            online_channel
            or online_purchase
            or explicit_card_complaint
        ):
            return self._result(
                DisputeCategory.CARD_NOT_PRESENT,
                "The complaint indicates a possible unauthorised or "
                "unrecognised card-not-present transaction. Human review "
                "is required.",
            )

        return self._result(
            DisputeCategory.UNKNOWN,
            "The complaint does not confidently match a supported dispute "
            "category. Human review is required.",
        )

    def classify_dispute(self, report: Any) -> DisputeClassification:
        """Compatibility method for existing callers."""
        return self.classify(report)


def classify_dispute(report: Any) -> DisputeClassification:
    """Module-level compatibility function."""
    return DisputeClassifier().classify(report)


def classify_transaction(report: Any) -> DisputeClassification:
    """Module-level compatibility function."""
    return DisputeClassifier().classify(report)