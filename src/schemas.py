from datetime import date
from decimal import Decimal
from enum import Enum

from pydantic import (
    BaseModel,
    Field,
    field_validator,
    model_validator,
)


class DisputeCategory(str, Enum):
    CARD_NOT_PRESENT = "card_not_present"
    SKIMMING = "skimming"
    UPI_SOCIAL_ENGINEERING = "upi_social_engineering"
    MERCHANT_DISPUTE = "merchant_dispute"
    DUPLICATE_CHARGE = "duplicate_charge"
    UNKNOWN = "unknown"


class DisputeReport(BaseModel):
    case_id: str = Field(min_length=1, max_length=64)

    transaction_date: date
    report_date: date

    transaction_amount: Decimal = Field(
        gt=0,
        max_digits=12,
        decimal_places=2,
    )

    transaction_type: str = Field(
        min_length=1,
        max_length=30,
    )

    customer_noticed_alert: bool
    credentials_shared: bool

    # Optional timeline information.
    # These dates should only be supplied when known.
    alert_sent_date: date | None = None
    alert_noticed_date: date | None = None
    credentials_shared_date: date | None = None

    complaint_description: str = Field(
        min_length=10,
        max_length=5000,
    )

    @field_validator("case_id", "transaction_type")
    @classmethod
    def strip_required_strings(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError(
                "This field cannot be empty or whitespace."
            )

        return value

    @field_validator("complaint_description")
    @classmethod
    def strip_complaint_description(cls, value: str) -> str:
        value = value.strip()

        if len(value) < 10:
            raise ValueError(
                "Complaint description must contain at least 10 characters."
            )

        return value

    @model_validator(mode="after")
    def validate_dates(self):
        if self.report_date < self.transaction_date:
            raise ValueError(
                "Report date cannot be before transaction date."
            )

        if self.transaction_date > date.today():
            raise ValueError(
                "Transaction date cannot be in the future."
            )

        if (
            self.alert_sent_date is not None
            and self.alert_sent_date < self.transaction_date
        ):
            raise ValueError(
                "Alert sent date cannot be before the transaction date."
            )

        if (
            self.alert_noticed_date is not None
            and self.alert_sent_date is not None
            and self.alert_noticed_date < self.alert_sent_date
        ):
            raise ValueError(
                "Alert noticed date cannot be before the alert sent date."
            )

        if (
            self.credentials_shared_date is not None
            and self.credentials_shared_date > self.report_date
        ):
            raise ValueError(
                "Credentials shared date cannot be after the report date."
            )

        if (
            self.alert_noticed_date is not None
            and self.alert_noticed_date > self.report_date
        ):
            raise ValueError(
                "Alert noticed date cannot be after the report date."
            )

        return self


class DisputeClassification(BaseModel):
    category: DisputeCategory
    explanation: str = Field(min_length=1)


class LiabilityRecommendation(BaseModel):
    case_id: str
    category: DisputeCategory
    recommendation: str
    reasoning: str
    citations: list[str] = Field(default_factory=list)
    requires_human_review: bool = True
    escalation_reason: str | None = None