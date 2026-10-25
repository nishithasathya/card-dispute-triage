import re
from typing import Any


STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "been",
    "by", "for", "from", "has", "have", "in", "is", "it",
    "of", "on", "or", "that", "the", "this", "to", "was",
    "were", "will", "with", "my", "i", "me", "we", "our",
    "they", "their", "you", "your", "about", "after", "before",
    "not", "no", "but", "if", "then", "can", "could", "would",
}


def tokenize(text: str) -> set[str]:
    """Convert text into normalized, meaningful terms."""

    words = re.findall(r"\b[a-zA-Z0-9]+\b", text.lower())

    return {
        word
        for word in words
        if word not in STOPWORDS and len(word) > 2
    }


def score_context_relevance(
    complaint: str,
    evidence: list[dict[str, Any]],
) -> float | None:
    """
    Estimate lexical relevance between a complaint and retrieved evidence.

    This is a heuristic, not a semantic or legal relevance assessment.
    Returns None when there is insufficient input to assess.
    """

    complaint_terms = tokenize(complaint)

    evidence_text = " ".join(
        str(item.get("text", ""))
        for item in evidence
    )

    evidence_terms = tokenize(evidence_text)

    if not complaint_terms or not evidence_terms:
        return None

    overlap = complaint_terms.intersection(evidence_terms)

    return len(overlap) / len(complaint_terms)


def score_groundedness(
    claim: str,
    evidence: list[dict[str, Any]],
) -> float | None:
    """
    Estimate claim-term support in retrieved passages.

    This checks word overlap only. It cannot establish that a legal
    interpretation is correct or that the evidence entails the claim.
    """

    claim_terms = tokenize(claim)

    evidence_text = " ".join(
        str(item.get("text", ""))
        for item in evidence
    )

    evidence_terms = tokenize(evidence_text)

    if not claim_terms or not evidence_terms:
        return None

    supported_terms = claim_terms.intersection(evidence_terms)

    return len(supported_terms) / len(claim_terms)


def score_faithfulness(
    classification: dict[str, Any] | None,
    recommendation: str | None,
    evidence: list[dict[str, Any]],
) -> float | None:
    """
    Estimate textual support for output fields.

    Classification labels are not treated as natural-language claims.
    The score assesses only the explanation and recommendation text.
    """

    claims = []

    if classification:
        explanation = classification.get("explanation")

        if isinstance(explanation, str) and explanation.strip():
            claims.append(explanation)

    if isinstance(recommendation, str) and recommendation.strip():
        claims.append(recommendation)

    if not claims:
        return None

    scores = [
        score_groundedness(claim, evidence)
        for claim in claims
    ]

    valid_scores = [
        score for score in scores
        if score is not None
    ]

    if not valid_scores:
        return None

    return sum(valid_scores) / len(valid_scores)


def score_hallucination(
    classification: dict[str, Any] | None,
    recommendation: str | None,
    evidence: list[dict[str, Any]],
) -> float | None:
    """
    Estimate unsupported wording as one minus the lexical support score.

    This is NOT a true hallucination detector. A correct paraphrase may
    have low word overlap, while an incorrect statement may reuse source
    vocabulary. Interpret this score only as a lexical diagnostic.
    """

    faithfulness_score = score_faithfulness(
        classification=classification,
        recommendation=recommendation,
        evidence=evidence,
    )

    if faithfulness_score is None:
        return None

    return 1.0 - faithfulness_score


def score_evaluation_record(
    result: dict[str, Any],
    scenario: dict[str, Any],
) -> dict[str, Any]:
    """
    Add heuristic evidence scores to a successful evaluation record.

    Invalid inputs and failed workflow executions are left unscored.
    """

    if (
        result.get("validation_failed") is True
        or result.get("execution_error") is not None
    ):
        return result

    evidence = result.get("evidence") or []

    complaint = str(scenario.get("description", ""))

    classification = result.get("classification") or {}

    recommendation = result.get("recommendation")

    context_score = score_context_relevance(
        complaint=complaint,
        evidence=evidence,
    )

    groundedness_score = score_groundedness(
        claim=(
            classification.get("explanation", "")
            if classification
            else str(recommendation or "")
        ),
        evidence=evidence,
    )

    faithfulness_score = score_faithfulness(
        classification=classification,
        recommendation=recommendation,
        evidence=evidence,
    )

    hallucination_score = score_hallucination(
        classification=classification,
        recommendation=recommendation,
        evidence=evidence,
    )

    result.update(
        {
            "groundedness_score": groundedness_score,
            "context_relevance_score": context_score,
            "faithfulness_score": faithfulness_score,
            "hallucination_score": hallucination_score,
            "evaluation_method": "lexical_overlap_heuristic",
        }
    )

    return result