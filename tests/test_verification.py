import pytest

from src.verification import EvidenceVerifier


@pytest.fixture
def valid_passage():
    return {
        "source": "sbi_customer_policy.pdf",
        "page": 31,
        "chunk_id": "sbi_customer_policy.pdf:p31:c1",
        "text": (
            "The customer must report an unauthorised transaction "
            "to the bank within the applicable reporting period."
        ),
    }


def test_valid_passage_passes_verification(valid_passage):
    verifier = EvidenceVerifier()

    result = verifier.verify_passage(valid_passage)

    assert result["valid"] is True
    assert result["issues"] == []


def test_missing_source_fails_verification(valid_passage):
    verifier = EvidenceVerifier()
    valid_passage["source"] = ""

    result = verifier.verify_passage(valid_passage)

    assert result["valid"] is False
    assert any("source" in issue.lower() for issue in result["issues"])


def test_invalid_page_number_fails_verification(valid_passage):
    verifier = EvidenceVerifier()
    valid_passage["page"] = 0

    result = verifier.verify_passage(valid_passage)

    assert result["valid"] is False
    assert any("page" in issue.lower() for issue in result["issues"])


def test_missing_chunk_id_fails_verification(valid_passage):
    verifier = EvidenceVerifier()
    valid_passage["chunk_id"] = ""

    result = verifier.verify_passage(valid_passage)

    assert result["valid"] is False
    assert any("chunk_id" in issue.lower() for issue in result["issues"])


def test_empty_evidence_collection():
    verifier = EvidenceVerifier()

    result = verifier.verify_evidence([])

    assert result["total_passages"] == 0
    assert result["valid_passages"] == 0
    assert result["invalid_passages"] == 0
    assert result["all_valid"] is True


def test_evidence_collection_counts_invalid_passages(valid_passage):
    verifier = EvidenceVerifier()

    invalid_passage = {
        "source": "",
        "page": 0,
        "chunk_id": "",
        "text": "",
    }

    result = verifier.verify_evidence(
        [valid_passage, invalid_passage]
    )

    assert result["total_passages"] == 2
    assert result["valid_passages"] == 1
    assert result["invalid_passages"] == 1
    assert result["all_valid"] is False