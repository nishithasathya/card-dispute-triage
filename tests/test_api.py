from fastapi.testclient import TestClient

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