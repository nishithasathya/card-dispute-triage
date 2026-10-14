from datetime import date

from langchain_community.vectorstores import FAISS
from langchain_huggingface import HuggingFaceEmbeddings

from src.classifier import DisputeClassifier
from src.decision_router import DisputeDecisionRouter
from src.schemas import DisputeReport
from src.verification import EvidenceVerifier


class RegulatoryRetriever:
    """Retrieves relevant passages from the local regulatory document index."""

    def __init__(self, index_path: str = "corpus/processed/faiss_index"):
        embeddings = HuggingFaceEmbeddings(
            model_name="sentence-transformers/all-MiniLM-L6-v2",
            model_kwargs={"device": "cpu"},
            encode_kwargs={"normalize_embeddings": True},
        )

        self.vectorstore = FAISS.load_local(
            index_path,
            embeddings,
            allow_dangerous_deserialization=True,
        )

    def search(self, query: str, k: int = 3) -> list[dict]:
        """Return retrieved passages with their source metadata."""

        results = self.vectorstore.similarity_search_with_score(query, k=k)

        passages = []

        for document, score in results:
            metadata = document.metadata

            passages.append(
                {
                    "source": metadata.get("source", "unknown"),
                    "page": metadata.get("page", "unknown"),
                    "chunk_id": metadata.get("chunk_id", "unknown"),
                    "text": document.page_content,
                    "retrieval_score": float(score),
                }
            )

        return passages


class DisputeTriageEngine:
    """
    Performs preliminary dispute classification, regulatory evidence
    retrieval, structural evidence verification, and workflow routing.

    The engine does not make final liability decisions.
    """

    def __init__(self):
        self.retriever = RegulatoryRetriever()
        self.classifier = DisputeClassifier()
        self.verifier = EvidenceVerifier()
        self.decision_router = DisputeDecisionRouter()

    @staticmethod
    def build_queries(report: DisputeReport) -> list[str]:
        """Build retrieval queries from the dispute facts."""

        reporting_delay = (report.report_date - report.transaction_date).days

        queries = [
            (
                "Customer liability for unauthorised electronic banking "
                "transactions and customer protection"
            ),
            (
                f"{report.transaction_type} transaction dispute: "
                f"{report.complaint_description}"
            ),
            (
                "Reporting delay, customer notification, unauthorised "
                "transactions, and applicable liability"
            ),
            (
                f"Transaction occurred {reporting_delay} calendar days "
                "before the customer reported the dispute"
            ),
            (
                "Customer negligence, sharing OTP credentials, and "
                "liability for unauthorised transactions"
            ),
            (
                "Bank SMS alerts, customer notification, and reporting "
                "unauthorised transactions"
            ),
        ]

        if report.credentials_shared:
            queries.append(
                "Customer shared credentials or OTP with another person "
                "and the circumstances relevant to customer liability"
            )

        if report.customer_noticed_alert:
            queries.append(
                "Customer received or noticed a transaction alert and "
                "subsequently reported an unauthorised transaction"
            )

        return queries

    def collect_evidence(self, report: DisputeReport) -> dict:
        """Classify the dispute, retrieve evidence, verify its structure,
        and recommend the appropriate next workflow action.
        """

        classification = self.classifier.classify(report)
        queries = self.build_queries(report)

        # Deduplicate passages returned by multiple queries.
        evidence_by_id = {}

        for query in queries:
            passages = self.retriever.search(query, k=3)

            for passage in passages:
                chunk_id = passage["chunk_id"]

                if chunk_id not in evidence_by_id:
                    evidence_by_id[chunk_id] = passage

        evidence = list(evidence_by_id.values())

        # Check whether retrieved evidence has the required structure.
        evidence_verification = self.verifier.verify_evidence(evidence)

        reporting_delay = (report.report_date - report.transaction_date).days

        escalation_reasons = [
            "Human review is required before any liability decision.",
            (
                "Retrieved passages must be checked for applicability "
                "to the transaction and relevant regulatory provisions."
            ),
        ]

        if classification.category.value == "unknown":
            escalation_reasons.append(
                "The dispute description does not support a confident "
                "preliminary classification."
            )

        if report.credentials_shared:
            escalation_reasons.append(
                "Credentials were reportedly shared. The circumstances "
                "and applicability of relevant provisions require review."
            )

        if not evidence:
            escalation_reasons.append(
                "No regulatory evidence passages were retrieved."
            )

        if not evidence_verification["all_valid"]:
            escalation_reasons.append(
                "One or more retrieved passages failed structural "
                "evidence validation."
            )

        status = (
            "evidence_collected"
            if evidence and evidence_verification["all_valid"]
            else "review_required"
        )

        # Assemble the preliminary triage result.
        result = {
            "case_id": report.case_id,
            "status": status,
            "transaction_amount": str(report.transaction_amount),
            "transaction_type": report.transaction_type,
            "transaction_date": report.transaction_date.isoformat(),
            "report_date": report.report_date.isoformat(),
            "reporting_delay_calendar_days": reporting_delay,
            "classification": {
                "category": classification.category.value,
                "explanation": classification.explanation,
            },
            "evidence": evidence,
            "evidence_verification": evidence_verification,
            "recommendation": (
                "No liability determination has been made. A reviewer "
                "must assess the case facts and applicable regulatory "
                "provisions before deciding the next action."
            ),
            "requires_human_review": True,
            "escalation_reason": " ".join(escalation_reasons),
        }

        # Recommend the next workflow action without making a liability
        # decision.
        result["routing"] = self.decision_router.route(result)

        return result


if __name__ == "__main__":
    report = DisputeReport(
        case_id="TEST-001",
        transaction_date=date(2026, 10, 1),
        report_date=date(2026, 10, 5),
        transaction_amount="2500.00",
        transaction_type="online",
        customer_noticed_alert=True,
        credentials_shared=False,
        complaint_description=(
            "I did not make this online purchase using my card."
        ),
    )

    engine = DisputeTriageEngine()
    result = engine.collect_evidence(report)

    print("\n=== CARD DISPUTE TRIAGE RESULT ===")
    print(f"Case ID: {result['case_id']}")
    print(f"Status: {result['status']}")

    print("\n--- Classification ---")
    print(f"Category: {result['classification']['category']}")
    print(f"Explanation: {result['classification']['explanation']}")

    print("\n--- Reporting Delay ---")
    print(
        "Calendar days: "
        f"{result['reporting_delay_calendar_days']}"
    )

    print("\n--- Retrieved Evidence ---")
    print(f"Passages retrieved: {len(result['evidence'])}")

    for index, passage in enumerate(result["evidence"], start=1):
        print(f"\nPassage {index}")
        print(f"Source: {passage['source']}")
        print(f"Page: {passage['page']}")
        print(f"Chunk ID: {passage['chunk_id']}")
        print(f"Text: {passage['text'][:300]}")

    print("\n--- Evidence Verification ---")
    verification = result["evidence_verification"]
    print(f"Valid passages: {verification['valid_passages']}")
    print(f"Invalid passages: {verification['invalid_passages']}")
    print(f"All structurally valid: {verification['all_valid']}")

    print("\n--- Workflow Routing ---")
    routing = result["routing"]
    print(f"Recommended action: {routing['recommended_action']}")
    print(f"Reasoning: {' '.join(routing['reasoning'])}")
    print(f"Human review required: {routing['requires_human_review']}")
    print(
        "Automated liability decision: "
        f"{routing['automated_liability_decision']}"
    )

    print("\n--- Recommendation ---")
    print(result["recommendation"])
    print(f"Escalation reason: {result['escalation_reason']}")