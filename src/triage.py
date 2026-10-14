from pathlib import Path
from typing import Any

from langchain_community.vectorstores import FAISS
from langchain_huggingface import HuggingFaceEmbeddings

from src.schemas import DisputeReport


# --------------------------------------------------
# PROJECT CONFIGURATION
# --------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent

INDEX_DIR = (
    PROJECT_ROOT
    / "corpus"
    / "processed"
    / "faiss_index"
)

EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


# --------------------------------------------------
# RETRIEVAL ENGINE
# --------------------------------------------------

class RegulatoryRetriever:
    """
    Retrieves potentially relevant passages from the
    locally indexed regulatory corpus.

    Retrieval identifies candidate evidence. It does not
    establish legal liability or prove that a passage
    supports a particular conclusion.
    """

    def __init__(self):
        if not INDEX_DIR.exists():
            raise FileNotFoundError(
                f"FAISS index not found at {INDEX_DIR}. "
                "Run src/retrieve.py first."
            )

        self.embeddings = HuggingFaceEmbeddings(
            model_name=EMBEDDING_MODEL,
            model_kwargs={"device": "cpu"},
            encode_kwargs={"normalize_embeddings": True},
        )

        self.vector_store = FAISS.load_local(
            str(INDEX_DIR),
            self.embeddings,
            allow_dangerous_deserialization=True,
        )

    def search(
        self,
        query: str,
        k: int = 3,
    ) -> list[dict[str, Any]]:
        """
        Search for relevant passages and preserve
        their original source metadata.
        """

        results = self.vector_store.similarity_search(
            query,
            k=k,
        )

        passages = []

        for document in results:
            passages.append(
                {
                    "source": document.metadata.get(
                        "source",
                        "unknown",
                    ),
                    "page": document.metadata.get(
                        "page",
                        "unknown",
                    ),
                    "chunk_id": document.metadata.get(
                        "chunk_id",
                        "unknown",
                    ),
                    "text": document.page_content,
                }
            )

        return passages


# --------------------------------------------------
# DISPUTE TRIAGE ENGINE
# --------------------------------------------------

class DisputeTriageEngine:
    """
    Initial evidence-collection workflow.

    This version validates a dispute, retrieves relevant
    regulatory passages, and routes the case for review.

    It does not make autonomous liability decisions.
    """

    def __init__(self):
        self.retriever = RegulatoryRetriever()

    def build_queries(
        self,
        report: DisputeReport,
    ) -> list[str]:
        """
        Build several retrieval queries from the
        submitted dispute information.
        """

        reporting_delay = (
            report.report_date - report.transaction_date
        ).days

        queries = [
            (
                "Customer liability for unauthorised "
                "electronic banking transactions"
            ),
            (
                f"Transaction type: {report.transaction_type}. "
                f"Complaint: {report.complaint_description}"
            ),
            (
                "Reporting delay, customer notification, "
                "customer negligence, and liability conditions"
            ),
            (
                f"Transaction reporting delay: "
                f"{reporting_delay} calendar days. "
                "Relevant reporting timelines and conditions."
            ),
        ]

        if report.credentials_shared:
            queries.append(
                "Customer sharing credentials, customer "
                "negligence, and unauthorised transactions"
            )

        if report.customer_noticed_alert:
            queries.append(
                "Transaction alerts, customer notification, "
                "and reporting unauthorised transactions"
            )

        return queries

    def collect_evidence(
        self,
        report: DisputeReport,
    ) -> dict[str, Any]:
        """
        Retrieve and deduplicate candidate evidence.

        Every case is marked for human review until a
        properly tested verification and decision process
        has been implemented.
        """

        queries = self.build_queries(report)

        evidence_by_id = {}

        for query in queries:
            passages = self.retriever.search(
                query=query,
                k=3,
            )

            for passage in passages:
                evidence_id = passage["chunk_id"]

                if evidence_id not in evidence_by_id:
                    evidence_by_id[evidence_id] = passage

        evidence = list(evidence_by_id.values())

        reporting_delay = (
            report.report_date - report.transaction_date
        ).days

        return {
            "case_id": report.case_id,
            "status": "evidence_collected",
            "transaction_amount": str(
                report.transaction_amount
            ),
            "transaction_type": report.transaction_type,
            "reporting_delay_calendar_days": reporting_delay,
            "evidence_count": len(evidence),
            "evidence": evidence,
            "recommendation": (
                "No liability determination has been made. "
                "Review the retrieved provisions and case "
                "facts before deciding the next action."
            ),
            "requires_human_review": True,
            "escalation_reason": (
                "Automated evidence verification and "
                "regulatory liability reasoning have not "
                "yet been implemented."
            ),
        }


# --------------------------------------------------
# MANUAL SMOKE TEST
# --------------------------------------------------

if __name__ == "__main__":
    from datetime import date
    from decimal import Decimal

    report = DisputeReport(
        case_id="TEST-001",
        transaction_date=date(2026, 10, 1),
        report_date=date(2026, 10, 5),
        transaction_amount=Decimal("2500.00"),
        transaction_type="card",
        customer_noticed_alert=True,
        credentials_shared=False,
        complaint_description=(
            "I noticed an unauthorised card transaction "
            "that I did not make."
        ),
    )

    engine = DisputeTriageEngine()
    result = engine.collect_evidence(report)

    print("\n" + "=" * 65)
    print("CARD DISPUTE TRIAGE — TEST RESULT")
    print("=" * 65)

    print(f"Case ID: {result['case_id']}")
    print(f"Status: {result['status']}")
    print(f"Evidence collected: {result['evidence_count']}")
    print(
        "Reporting delay: "
        f"{result['reporting_delay_calendar_days']} calendar days"
    )

    print("\nRETRIEVED EVIDENCE")

    for index, passage in enumerate(
        result["evidence"],
        start=1,
    ):
        print(f"\nPassage {index}")
        print(f"Source: {passage['source']}")
        print(f"Page: {passage['page']}")
        print(f"Text: {passage['text'][:400]}")

    print("\nRECOMMENDATION")
    print(result["recommendation"])

    print("\nHUMAN REVIEW REQUIRED")
    print(result["requires_human_review"])