from pathlib import Path


class EvidenceVerifier:
    """
    Validates retrieved evidence before it is returned by the
    dispute-triage service.

    This checks evidence structure and traceability. It does not
    establish whether a regulatory interpretation is legally correct.
    """

    REQUIRED_FIELDS = ["source", "page", "chunk_id", "text"]

    def verify_passage(self, passage: dict) -> dict:
        """Validate one retrieved passage."""

        issues = []

        # Check required metadata and text fields.
        for field in self.REQUIRED_FIELDS:
            value = passage.get(field)

            if value is None or not str(value).strip():
                issues.append(f"Missing or empty field: {field}")

        # Check that the source looks like a PDF filename.
        source = passage.get("source")

        if source and not str(source).lower().endswith(".pdf"):
            issues.append("Source does not appear to be a PDF filename")

        # Check that the page number is valid.
        page = passage.get("page")

        try:
            if int(page) < 1:
                issues.append("Page number must be positive")
        except (TypeError, ValueError):
            issues.append("Page number must be a valid integer")

        # Check that the text is usable.
        text = passage.get("text")

        if isinstance(text, str) and len(text.strip()) < 20:
            issues.append("Evidence text is too short to review reliably")

        return {
            "valid": len(issues) == 0,
            "issues": issues,
            "source": source,
            "page": page,
            "chunk_id": passage.get("chunk_id"),
        }

    def verify_evidence(self, passages: list[dict]) -> dict:
        """Validate a collection of retrieved passages."""

        results = [
            self.verify_passage(passage)
            for passage in passages
        ]

        valid_count = sum(
            1 for result in results if result["valid"]
        )

        invalid_count = len(results) - valid_count

        return {
            "total_passages": len(results),
            "valid_passages": valid_count,
            "invalid_passages": invalid_count,
            "all_valid": invalid_count == 0,
            "results": results,
        }