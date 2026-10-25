import json
from pathlib import Path

from fastapi.testclient import TestClient

import src.api as api
from src.api import app

client = TestClient(app)


def test_health_endpoint():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_triage_rejects_invalid_request():
    response = client.post(
        "/triage",
        json={"report": {}},
    )

    assert response.status_code == 422


def test_triage_rejects_report_date_before_transaction():
    response = client.post(
        "/triage",
        json={
            "report": {
                "case_id": "TEST-INVALID",
                "transaction_date": "2026-10-10",
                "report_date": "2026-10-05",
                "transaction_amount": "2500.00",
                "transaction_type": "card",
                "customer_noticed_alert": True,
                "credentials_shared": False,
                "complaint_description": (
                    "I want to report an unauthorised card transaction."
                ),
            }
        },
    )

    assert response.status_code == 422


def test_invalid_request_is_quarantined(tmp_path, monkeypatch):
    monkeypatch.setattr(api, "QUARANTINE_DIR", tmp_path)

    response = client.post(
        "/triage",
        headers={"X-Correlation-ID": "test-correlation-001"},
        json={"report": {}},
    )

    assert response.status_code == 422

    response_data = response.json()
    assert response_data["correlation_id"] == "test-correlation-001"
    assert "quarantine_record_id" in response_data

    records = list(tmp_path.glob("*.json"))
    assert len(records) == 1

    record = json.loads(records[0].read_text(encoding="utf-8"))

    assert record["status"] == "quarantined"
    assert record["reason"] == "request_validation_failed"
    assert record["correlation_id"] == "test-correlation-001"
    assert record["path"] == "/triage"
    assert len(record["validation_errors"]) > 0


def test_quarantine_does_not_store_original_request_body(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(api, "QUARANTINE_DIR", tmp_path)

    sensitive_description = (
        "My private complaint details should not be stored in quarantine."
    )

    response = client.post(
        "/triage",
        json={
            "report": {
                "case_id": "CASE-QUARANTINE",
                "transaction_date": "2026-10-01",
                "report_date": "2026-10-05",
                "transaction_amount": "-2500.00",
                "transaction_type": "card",
                "customer_noticed_alert": True,
                "credentials_shared": False,
                "complaint_description": sensitive_description,
            }
        },
    )

    assert response.status_code == 422

    records = list(tmp_path.glob("*.json"))
    assert len(records) == 1

    saved_content = records[0].read_text(encoding="utf-8")

    assert sensitive_description not in saved_content
    assert "CASE-QUARANTINE" not in saved_content


def test_invalid_request_does_not_start_triage(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(api, "QUARANTINE_DIR", tmp_path)

    def unexpected_triage(*args, **kwargs):
        raise AssertionError(
            "Triage must not run for an invalid request."
        )

    monkeypatch.setattr(api, "run_triage", unexpected_triage)

    response = client.post(
        "/triage",
        json={"report": {}},
    )

    assert response.status_code == 422
    assert len(list(tmp_path.glob("*.json"))) == 1


def test_quarantine_response_contains_correlation_header():
    response = client.post(
        "/triage",
        headers={"X-Correlation-ID": "test-correlation-002"},
        json={"report": {}},
    )

    assert response.status_code == 422
    assert (
        response.headers["X-Correlation-ID"]
        == "test-correlation-002"
    )