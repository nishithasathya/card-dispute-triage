from src.decision_router import DisputeDecisionRouter


def make_triage_result(
    category="card_not_present",
    evidence=None,
    valid_passages=1,
    invalid_passages=0,
):
    if evidence is None:
        evidence = [
            {
                "source": "sbi_customer_policy.pdf",
                "page": 31,
                "chunk_id": "sbi_customer_policy.pdf:p31:c1",
                "text": (
                    "The bank's policy describes customer liability "
                    "for unauthorised transactions."
                ),
            }
        ]

    return {
        "case_id": "TEST-ROUTER-001",
        "classification": {
            "category": category,
            "explanation": "Preliminary rule-based classification.",
        },
        "evidence": evidence,
        "evidence_verification": {
            "total_passages": len(evidence),
            "valid_passages": valid_passages,
            "invalid_passages": invalid_passages,
            "all_valid": invalid_passages == 0,
        },
    }


def test_valid_case_routes_to_human_review():
    router = DisputeDecisionRouter()

    result = router.route(make_triage_result())

    assert result["recommended_action"] == "PREPARE_FOR_HUMAN_REVIEW"
    assert result["requires_human_review"] is True
    assert result["automated_liability_decision"] is False


def test_unknown_category_escalates():
    router = DisputeDecisionRouter()

    result = router.route(
        make_triage_result(category="unknown")
    )

    assert (
        result["recommended_action"]
        == "ESCALATE_FOR_CLASSIFICATION_REVIEW"
    )


def test_missing_evidence_escalates():
    router = DisputeDecisionRouter()

    result = router.route(
        make_triage_result(
            evidence=[],
            valid_passages=0,
            invalid_passages=0,
        )
    )

    assert result["recommended_action"] == "ESCALATE_FOR_EVIDENCE_REVIEW"


def test_invalid_evidence_escalates():
    router = DisputeDecisionRouter()

    result = router.route(
        make_triage_result(
            valid_passages=1,
            invalid_passages=1,
        )
    )

    assert result["recommended_action"] == "ESCALATE_FOR_EVIDENCE_REVIEW"


def test_every_route_requires_human_review():
    router = DisputeDecisionRouter()

    scenarios = [
        make_triage_result(),
        make_triage_result(category="unknown"),
        make_triage_result(evidence=[], valid_passages=0),
    ]

    for scenario in scenarios:
        result = router.route(scenario)

        assert result["requires_human_review"] is True
        assert result["automated_liability_decision"] is False