from datetime import date

from langchain_community.vectorstores import FAISS
from langchain_huggingface import HuggingFaceEmbeddings

from src.classifier import DisputeClassifier
from src.decision_router import DisputeDecisionRouter
from src.schemas import DisputeReport
from src.verification import EvidenceVerifier


class RegulatoryRetriever:
    """Retrieve and rank relevant passages from regulatory documents."""

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

    @staticmethod
    def _keyword_score(query: str, text: str) -> float:
        """
        Calculate lexical overlap between a query and passage.

        This is a heuristic relevance signal, not a legal entailment check.
        """

        stopwords = {
            "the", "a", "an", "and", "or", "of", "to", "in",
            "for", "on", "is", "are", "was", "were", "with",
            "by", "from", "that", "this", "it", "be", "as",
            "their", "they", "them", "which", "where", "when",
            "what", "who", "how", "after", "before",
        }

        def tokenize(value: str) -> set[str]:
            tokens = set()

            for word in value.lower().split():
                word = word.strip(".,:;!?()[]{}\"'")

                if len(word) > 2 and word not in stopwords:
                    tokens.add(word)

            return tokens

        query_terms = tokenize(query)
        passage_terms = tokenize(text)

        if not query_terms:
            return 0.0

        return len(query_terms & passage_terms) / len(query_terms)

    def search(self, query: str, k: int = 3) -> list[dict]:
        """Retrieve candidate passages and rank them by hybrid score."""

        if k <= 0:
            return []

        total_vectors = self.vectorstore.index.ntotal

        if total_vectors == 0:
            return []

        fetch_k = min(max(k * 4, 12), total_vectors)

        results = self.vectorstore.similarity_search_with_score(
            query,
            k=fetch_k,
        )

        passages = []

        for document, distance in results:
            metadata = document.metadata
            text = document.page_content

            keyword_score = self._keyword_score(query, text)

            # FAISS L2 distance is not a calibrated probability.
            vector_score = 1.0 / (
                1.0 + max(float(distance), 0.0)
            )

            combined_score = (
                0.65 * vector_score
                + 0.35 * keyword_score
            )

            passages.append(
                {
                    "source": metadata.get("source", "unknown"),
                    "page": metadata.get("page", "unknown"),
                    "chunk_id": metadata.get("chunk_id", "unknown"),
                    "text": text,
                    "retrieval_score": float(distance),
                    "keyword_score": float(keyword_score),
                    "combined_score": float(combined_score),
                }
            )

        passages.sort(
            key=lambda passage: passage["combined_score"],
            reverse=True,
        )

        return passages[:k]


class DisputeTriageEngine:
    """
    Classify disputes, retrieve regulatory evidence, validate evidence
    structure, and recommend the next workflow action.

    The engine never makes a final liability decision.
    """

    def __init__(self):
        self.retriever = RegulatoryRetriever()
        self.classifier = DisputeClassifier()
        self.verifier = EvidenceVerifier()
        self.decision_router = DisputeDecisionRouter()

    @staticmethod
    def build_queries(
        report: DisputeReport,
        category: str | None = None,
    ) -> list[str]:
        """Build general and category-specific regulatory queries."""

        reporting_delay = (
            report.report_date - report.transaction_date
        ).days

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

        if category == "duplicate_charge":
            queries.extend(
                [
                    (
                        "SBI policy Section 4.1(a): unauthorised or "
                        "erroneous debit, reversal, value-dated credit, "
                        "detection, information, and due verification"
                    ),
                    (
                        "SBI policy Section 4.2(c): charges levied in "
                        "violation of an arrangement or inadvertently, "
                        "reversal of charges, agreed terms and conditions"
                    ),
                    (
                        "SBI policy Section 4.1(c): verification timeline "
                        "for unauthorised or erroneous debits and "
                        "third-party involvement"
                    ),
                    (
                        "Duplicate transaction, duplicate debit, "
                        "erroneous account entry, inadvertent charge "
                        "and reversal procedure"
                    ),
                ]
            )

        elif category == "merchant_dispute":
            queries.extend(
                [
                    (
                        "Merchant dispute, goods or services refund, "
                        "and disputed card transaction"
                    ),
                    (
                        "Card network chargeback, disputed merchant "
                        "transaction, and applicable procedure"
                    ),
                ]
            )

        elif category == "card_not_present":
            queries.extend(
                [
                    (
                        "Remote online card-not-present transaction, "
                        "unauthorised electronic banking liability"
                    ),
                    (
                        "Unauthorised online card transaction, "
                        "customer reporting, and liability provisions"
                    ),
                ]
            )

        elif category == "skimming":
            queries.extend(
                [
                    (
                        "Card skimming, copying, theft, and unauthorised "
                        "electronic banking transaction"
                    ),
                    (
                        "Loss, theft, or copying of payment card, "
                        "customer notification, and bank action"
                    ),
                ]
            )

        elif category == "upi_social_engineering":
            queries.extend(
                [
                    (
                        "UPI social engineering, impersonation scam, "
                        "fraud, customer reporting, and liability"
                    ),
                    (
                        "OTP sharing, credential sharing, impersonation, "
                        "customer negligence, and unauthorised transaction"
                    ),
                ]
            )

        elif category == "unknown":
            queries.append(
                "Banking complaint classification, customer protection, "
                "and grievance procedures"
            )

        if report.credentials_shared:
            queries.extend(
                [
                    (
                        "Customer shared credentials or OTP with another "
                        "person and circumstances relevant to liability"
                    ),
                    (
                        "Customer deceived by caller impersonating bank "
                        "and shared OTP or payment credentials"
                    ),
                ]
            )

        if report.customer_noticed_alert:
            queries.append(
                "Customer received or noticed transaction alert and "
                "subsequently reported an unauthorised transaction"
            )

        if report.alert_sent_date:
            queries.append(
                "Date of communication of unauthorised transaction, "
                "SMS alert, and calculation of reporting delay"
            )

        return queries

    def collect_evidence(self, report: DisputeReport) -> dict:
        """
        Classify the dispute, retrieve evidence using multiple queries,
        combine rankings using Reciprocal Rank Fusion (RRF), and route
        the case for human review.

        Evidence selection encourages source diversity without treating
        the presence of a source as proof that its passages are relevant.
        """

        classification = self.classifier.classify(report)

        queries = self.build_queries(
            report,
            category=classification.category.value,
        )

        rrf_scores = {}
        evidence_by_id = {}
        rrf_constant = 60

        # Retrieve candidates for each query and combine their rankings.
        for query in queries:
            passages = self.retriever.search(query, k=5)

            for rank, passage in enumerate(passages, start=1):
                chunk_id = passage["chunk_id"]

                if chunk_id == "unknown":
                    key = (
                        passage["source"],
                        passage["page"],
                        passage["text"],
                    )
                else:
                    key = chunk_id

                rrf_scores[key] = rrf_scores.get(key, 0.0) + (
                    1.0 / (rrf_constant + rank)
                )

                existing = evidence_by_id.get(key)

                if (
                    existing is None
                    or passage["combined_score"]
                    > existing["combined_score"]
                ):
                    evidence_by_id[key] = passage.copy()

        evidence = []

        for key, passage in evidence_by_id.items():
            passage["fusion_score"] = rrf_scores[key]
            evidence.append(passage)

        evidence.sort(
            key=lambda passage: passage["fusion_score"],
            reverse=True,
        )

        # Preserve the best-ranked passage from each available source.
        # Then fill remaining positions using the RRF ranking.
        selected = []
        selected_ids = set()
        selected_sources = set()

        for passage in evidence:
            source = passage["source"]
            chunk_id = passage["chunk_id"]

            if source not in selected_sources:
                selected.append(passage)
                selected_ids.add(chunk_id)
                selected_sources.add(source)

            if len(selected) >= 15:
                break

        for passage in evidence:
            if len(selected) >= 15:
                break

            chunk_id = passage["chunk_id"]

            if chunk_id not in selected_ids:
                selected.append(passage)
                selected_ids.add(chunk_id)

        # Maintain descending RRF order in the final evidence list.
        selected.sort(
            key=lambda passage: passage["fusion_score"],
            reverse=True,
        )

        evidence = selected

        evidence_verification = self.verifier.verify_evidence(evidence)

        reporting_delay = (
            report.report_date - report.transaction_date
        ).days

        escalation_reasons = [
            "Human review is required before any liability decision.",
            (
                "A reviewer must assess whether the retrieved provisions "
                "apply to the specific transaction and complaint."
            ),
        ]

        if classification.category.value == "unknown":
            escalation_reasons.append(
                "The complaint does not support a confident "
                "preliminary classification."
            )

        if report.credentials_shared:
            escalation_reasons.append(
                "Credentials were reportedly shared. The circumstances, "
                "including possible deception or impersonation, require "
                "human assessment."
            )

        if not evidence:
            escalation_reasons.append(
                "No regulatory evidence passages were retrieved."
            )

        if not evidence_verification["all_valid"]:
            escalation_reasons.append(
                "One or more passages failed structural evidence validation."
            )

        status = (
            "evidence_collected"
            if evidence and evidence_verification["all_valid"]
            else "review_required"
        )

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
                "No liability determination has been made. A human "
                "reviewer must assess the case facts and applicable "
                "regulatory provisions before deciding the next action."
            ),
            "requires_human_review": True,
            "escalation_reason": " ".join(escalation_reasons),
        }

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
    print(f"Calendar days: {result['reporting_delay_calendar_days']}")

    print("\n--- Retrieved Evidence ---")
    print(f"Passages retrieved: {len(result['evidence'])}")

    for index, passage in enumerate(result["evidence"], start=1):
        print(f"\nPassage {index}")
        print(f"Source: {passage['source']}")
        print(f"Page: {passage['page']}")
        print(f"Chunk ID: {passage['chunk_id']}")
        print(f"Retrieval distance: {passage['retrieval_score']:.4f}")
        print(f"Keyword score: {passage['keyword_score']:.4f}")
        print(f"Combined score: {passage['combined_score']:.4f}")
        print(f"Fusion score: {passage['fusion_score']:.4f}")
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