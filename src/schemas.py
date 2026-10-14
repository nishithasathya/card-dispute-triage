from datetime import date
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, Field, model_validator


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

    complaint_description: str = Field(
        min_length=10,
        max_length=5000,
    )

    @model_validator(mode="after")
    def validate_dates(self):
        if self.report_date < self.transaction_date:
            raise ValueError(
                "Report date cannot precede transaction date."
            )

        if self.transaction_date > date.today():
            raise ValueError(
                "Transaction date cannot be in the future."
            )

        return self


class DisputeClassification(BaseModel):
    category: DisputeCategory
    explanation: str


class LiabilityRecommendation(BaseModel):
    case_id: str
    category: DisputeCategory

    recommendation: str
    reasoning: str

    citations: list[str] = Field(default_factory=list)

    requires_human_review: bool
    escalation_reason: str | None = None