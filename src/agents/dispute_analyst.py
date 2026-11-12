from src.classifier import DisputeClassifier
from src.schemas import DisputeReport


class DisputeAnalyst:
    """
    Agent 1: Analyses a dispute and produces a preliminary classification.

    This agent does not determine liability or make a final decision.
    """

    def __init__(self):
        self.classifier = DisputeClassifier()

    def analyze(self, report: DisputeReport) -> dict:
        """
        Classify the dispute and summarise the relevant case facts.
        """

        classification = self.classifier.classify(report)

        reporting_delay = (
            report.report_date - report.transaction_date
        ).days

        return {
            "case_id": report.case_id,
            "agent": "dispute_analyst",
            "transaction_type": report.transaction_type,
            "transaction_amount": str(report.transaction_amount),
            "transaction_date": report.transaction_date.isoformat(),
            "report_date": report.report_date.isoformat(),
            "reporting_delay_calendar_days": reporting_delay,
            "customer_noticed_alert": report.customer_noticed_alert,
            "credentials_shared": report.credentials_shared,
            "complaint_description": report.complaint_description,
            "classification": {
                "category": classification.category.value,
                "explanation": classification.explanation,
            },
            "requires_human_review": True,
        }