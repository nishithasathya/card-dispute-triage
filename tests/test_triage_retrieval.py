from src.triage import RegulatoryRetriever


def test_retriever_returns_source_metadata():
    retriever = RegulatoryRetriever()

    results = retriever.search(
        "Customer liability for unauthorised electronic banking transactions",
        k=3,
    )

    assert len(results) > 0

    for result in results:
        assert result["source"]
        assert result["page"] != "unknown"
        assert result["text"].strip()


def test_retriever_returns_relevant_liability_passages():
    retriever = RegulatoryRetriever()

    results = retriever.search(
        (
            "Customer negligence, sharing OTP credentials, "
            "and liability for unauthorised transactions"
        ),
        k=5,
    )

    combined_text = " ".join(
        result["text"].lower()
        for result in results
    )

    relevant_terms = [
        "liability",
        "unauthorised",
        "unauthorized",
        "negligence",
        "customer",
    ]

    matches = sum(
        term in combined_text
        for term in relevant_terms
    )

    assert matches >= 2, (
        "Retrieved passages did not contain enough "
        "expected liability-related terminology."
    )