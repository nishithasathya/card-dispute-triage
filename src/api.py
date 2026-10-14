from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from datetime import date
from decimal import Decimal

from src.schemas import DisputeReport
from src.triage import DisputeTriageEngine

app = FastAPI(
    title="Card Dispute Triage Service",
    description=(
        "Retrieves relevant regulatory evidence for unauthorised "
        "transaction disputes. Recommendations require human review."
    ),
    version="0.1.0",
)


class TriageRequest(BaseModel):
    report: DisputeReport


@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "service": "card-dispute-triage",
    }


@app.post("/triage")
def triage_dispute(request: TriageRequest):
    try:
        engine = DisputeTriageEngine()
        result = engine.collect_evidence(request.report)

        return result

    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=503,
            detail="Regulatory evidence index is unavailable.",
        ) from exc

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="An unexpected error occurred during triage.",
        ) from exc