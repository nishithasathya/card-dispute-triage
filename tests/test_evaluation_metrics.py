from evaluation.metrics import (
    classification_accuracy,
    human_review_rate,
    validation_failure_detection_rate,
    evidence_coverage,
    citation_metadata_validity,
    automated_liability_decision_rate,
    calculate_metrics,
)


def test_classification_accuracy():
    results = [
        {
            "expected_category": "card_not_present",
            "predicted_category": "card_not_present",
        },
        {
            "expected_category": "skimming",
            "predicted_category": "unknown",
        },
    ]

    assert classification_accuracy(results) == 0.5


def test_human_review_rate():
    results = [
        {"requires_human_review": True},
        {"requires_human_review": True},
        {"requires_human_review": False},
    ]

    assert abs(human_review_rate(results) - 2 / 3) < 1e-9


def test_validation_failure_detection_rate():
    results = [
        {
            "expected_validation_failure": True,
            "validation_failed": True,
        },
        {
            "expected_validation_failure": True,
            "validation_failed": False,
        },
    ]

    assert validation_failure_detection_rate(results) == 0.5


def test_evidence_coverage():
    results = [
        {"evidence": [{"source": "rbi.pdf"}]},
        {"evidence": []},
    ]

    assert evidence_coverage(results) == 0.5


def test_citation_metadata_validity():
    results = [
        {
            "evidence_verification": {
                "total_passages": 4,
                "valid_passages": 3,
            }
        }
    ]

    assert citation_metadata_validity(results) == 0.75


def test_automated_liability_decision_rate():
    results = [
        {"automated_liability_decision": False},
        {
            "routing": {
                "automated_liability_decision": True,
            }
        },
    ]

    assert automated_liability_decision_rate(results) == 0.5


def test_calculate_metrics_returns_all_metrics():
    results = [
        {
            "expected_category": "card_not_present",
            "predicted_category": "card_not_present",
            "requires_human_review": True,
            "expected_validation_failure": False,
            "evidence": [{"source": "rbi.pdf"}],
            "evidence_verification": {
                "total_passages": 1,
                "valid_passages": 1,
            },
            "automated_liability_decision": False,
        }
    ]

    metrics = calculate_metrics(results)

    assert metrics["classification_accuracy"] == 1.0
    assert metrics["human_review_rate"] == 1.0
    assert metrics["evidence_coverage"] == 1.0
    assert metrics["citation_metadata_validity"] == 1.0
    assert metrics["automated_liability_decision_rate"] == 0.0