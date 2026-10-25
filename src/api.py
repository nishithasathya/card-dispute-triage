"""FastAPI application for card dispute triage."""

import asyncio
import json
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)
from pydantic import BaseModel
from redis.exceptions import RedisError

from src.graph import DisputeAgentWorkflow
from src.job_queue import check_redis, enqueue_job, get_job
from src.schemas import DisputeReport

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
    OTLPSpanExporter,
)
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

logger = logging.getLogger(__name__)

# OpenTelemetry distributed tracing configuration.
OTEL_SERVICE_NAME = os.getenv(
    "OTEL_SERVICE_NAME",
    "card-dispute-api",
)

trace_provider = TracerProvider(
    resource=Resource.create(
        {"service.name": OTEL_SERVICE_NAME}
    )
)

trace_exporter = OTLPSpanExporter(
    endpoint=os.getenv(
        "OTEL_EXPORTER_OTLP_ENDPOINT",
        "http://localhost:4317",
    ),
    insecure=True,
)

trace_provider.add_span_processor(
    BatchSpanProcessor(trace_exporter)
)

trace.set_tracer_provider(trace_provider)

tracer = trace.get_tracer(__name__)

MAX_CONCURRENT_RUNS = max(
    1,
    int(os.getenv("MAX_CONCURRENT_RUNS", "4")),
)

TRIAGE_TIMEOUT_SECONDS = max(
    1,
    int(os.getenv("TRIAGE_TIMEOUT_SECONDS", "60")),
)

QUARANTINE_DIR = Path(
    os.getenv("QUARANTINE_DIR", "data/quarantine")
)

triage_semaphore = asyncio.Semaphore(MAX_CONCURRENT_RUNS)


# Prometheus metrics
HTTP_REQUESTS = Counter(
    "card_dispute_http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status"],
)

TRIAGE_REQUESTS = Counter(
    "card_dispute_triage_requests_total",
    "Total triage requests",
)

TRIAGE_SUCCESSES = Counter(
    "card_dispute_triage_success_total",
    "Successful synchronous triage runs",
)

TRIAGE_ERRORS = Counter(
    "card_dispute_triage_errors_total",
    "Failed synchronous triage runs",
    ["error_type"],
)

TRIAGE_TIMEOUTS = Counter(
    "card_dispute_triage_timeouts_total",
    "Triage runs that exceeded their timeout",
)

TRIAGE_DURATION = Histogram(
    "card_dispute_triage_duration_seconds",
    "Duration of synchronous triage runs",
)

ACTIVE_TRIAGE_RUNS = Gauge(
    "card_dispute_active_triage_runs",
    "Number of active synchronous triage runs",
)

QUEUED_JOBS = Counter(
    "card_dispute_jobs_enqueued_total",
    "Total jobs successfully submitted to the queue",
)

JOB_STATUS_REQUESTS = Counter(
    "card_dispute_job_status_requests_total",
    "Total requests to retrieve queued job status",
)

QUARANTINED_REQUESTS = Counter(
    "card_dispute_quarantined_requests_total",
    "Number of invalid requests recorded in quarantine",
)


class TriageRequest(BaseModel):
    """Request body for triage endpoints."""

    report: DisputeReport


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown hooks."""
    QUARANTINE_DIR.mkdir(parents=True, exist_ok=True)
    logger.info("Starting card dispute triage API.")
    yield
    logger.info("Stopping card dispute triage API.")


app = FastAPI(
    title="Card Dispute Triage Service",
    description=(
        "A human-in-the-loop card dispute triage service. "
        "It provides recommendations and evidence, but does not "
        "make final liability decisions or close disputes."
    ),
    version="1.0.0",
    lifespan=lifespan,
)
FastAPIInstrumentor.instrument_app(app)
STATIC_DIR = Path(__file__).parent / "static"


@app.get("/", include_in_schema=False)
async def web_client():
    return FileResponse(STATIC_DIR / "index.html")
def safe_validation_errors(
    errors: list[dict],
) -> list[dict]:
    """
    Preserve validation locations without saving submitted values.

    Pydantic error objects may contain sensitive input values.
    This function deliberately excludes those values.
    """
    sanitized = []

    for error in errors:
        location = [
            str(part)
            for part in error.get("loc", ())
        ]

        error_type = str(
            error.get("type", "validation_error")
        )

        # Missing-field errors do not contain submitted field values.
        # Other messages are generalized to avoid leaking user input.
        if error_type == "missing":
            message = "Required field is missing."
        else:
            message = "Invalid input."

        sanitized.append(
            {
                "location": location,
                "type": error_type,
                "message": message,
            }
        )

    return sanitized


def write_quarantine_record(
    *,
    correlation_id: str,
    method: str,
    path: str,
    errors: list[dict],
) -> str:
    """
    Save validation metadata without the original request body.
    """
    QUARANTINE_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).isoformat()
    record_id = str(uuid.uuid4())

    record = {
        "record_id": record_id,
        "timestamp": timestamp,
        "correlation_id": correlation_id,
        "method": method,
        "path": path,
        "status": "quarantined",
        "reason": "request_validation_failed",
        "validation_errors": safe_validation_errors(errors),
    }

    filename = f"{record_id}.json"
    destination = QUARANTINE_DIR / filename

    # Exclusive creation prevents accidental overwriting.
    with destination.open("x", encoding="utf-8") as file:
        json.dump(record, file, indent=2)
        file.write("\n")

    return record_id


@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    """Log requests and attach a correlation ID."""
    correlation_id = (
        request.headers.get("X-Correlation-ID")
        or str(uuid.uuid4())
    )

    request.state.correlation_id = correlation_id
    start_time = time.perf_counter()
    status_code = 500

    try:
        response = await call_next(request)
        status_code = response.status_code
        response.headers["X-Correlation-ID"] = correlation_id
        return response

    except Exception:
        logger.exception(
            "Unhandled HTTP error",
            extra={
                "correlation_id": correlation_id,
                "path": request.url.path,
            },
        )
        raise

    finally:
        duration = time.perf_counter() - start_time

        if request.url.path != "/metrics":
            HTTP_REQUESTS.labels(
                method=request.method,
                endpoint=request.url.path,
                status=str(status_code),
            ).inc()

        logger.info(
            "HTTP request completed",
            extra={
                "correlation_id": correlation_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": status_code,
                "duration_seconds": round(duration, 4),
            },
        )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
):
    """
    Quarantine invalid requests and return HTTP 422.

    FastAPI validates requests before invoking their endpoint,
    so invalid requests never enter the triage workflow.
    """
    correlation_id = getattr(
        request.state,
        "correlation_id",
        str(uuid.uuid4()),
    )

    errors = safe_validation_errors(exc.errors())

    try:
        record_id = await asyncio.to_thread(
            write_quarantine_record,
            correlation_id=correlation_id,
            method=request.method,
            path=request.url.path,
            errors=errors,
        )

        QUARANTINED_REQUESTS.inc()

        logger.warning(
            "Invalid request quarantined",
            extra={
                "correlation_id": correlation_id,
                "quarantine_record_id": record_id,
                "path": request.url.path,
                "validation_error_count": len(errors),
            },
        )

    except OSError:
        logger.exception(
            "Unable to write quarantine record",
            extra={
                "correlation_id": correlation_id,
                "path": request.url.path,
            },
        )

        return JSONResponse(
            status_code=500,
            content={
                "detail": (
                    "Request validation failed, but the quarantine "
                    "record could not be saved."
                ),
                "correlation_id": correlation_id,
            },
            headers={"X-Correlation-ID": correlation_id},
        )

    return JSONResponse(
        status_code=422,
        content={
            "detail": errors,
            "quarantine_record_id": record_id,
            "correlation_id": correlation_id,
        },
        headers={"X-Correlation-ID": correlation_id},
    )


@app.get("/health")
async def health():
    """Basic API health check."""
    return {
        "status": "healthy",
        "service": "card-dispute-triage",
    }


@app.get("/health/ready")
async def readiness():
    """Check whether the API can reach Redis."""
    try:
        check_redis()
    except RedisError:
        raise HTTPException(
            status_code=503,
            detail="Redis is unavailable.",
        )

    return {
        "status": "ready",
        "service": "card-dispute-triage",
        "queue": "available",
    }


@app.get("/metrics")
async def metrics():
    """Expose Prometheus metrics."""
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )


def run_triage(report: DisputeReport) -> dict:
    """Execute the triage workflow."""
    return DisputeAgentWorkflow().run(report)


@app.post("/triage")
async def triage(request: TriageRequest):
    """Run triage synchronously."""
    TRIAGE_REQUESTS.inc()
    start_time = time.perf_counter()

    try:
        async with triage_semaphore:
            ACTIVE_TRIAGE_RUNS.inc()

            try:
                result = await asyncio.wait_for(
                    asyncio.to_thread(
                        run_triage,
                        request.report,
                    ),
                    timeout=TRIAGE_TIMEOUT_SECONDS,
                )
            finally:
                ACTIVE_TRIAGE_RUNS.dec()

        TRIAGE_SUCCESSES.inc()

        return {
            "case_id": request.report.case_id,
            "status": "review_required",
            "requires_human_review": True,
            "automated_liability_decision": False,
            "result": result,
        }

    except asyncio.TimeoutError:
        TRIAGE_TIMEOUTS.inc()
        TRIAGE_ERRORS.labels(error_type="timeout").inc()

        raise HTTPException(
            status_code=504,
            detail="Triage exceeded the configured time limit.",
        )

    except FileNotFoundError:
        TRIAGE_ERRORS.labels(error_type="missing_file").inc()
        logger.exception("Required triage resource is missing.")

        raise HTTPException(
            status_code=503,
            detail="A required triage resource is unavailable.",
        )

    except Exception:
        TRIAGE_ERRORS.labels(error_type="internal").inc()
        logger.exception(
            "Synchronous triage failed",
            extra={"case_id": request.report.case_id},
        )

        raise HTTPException(
            status_code=500,
            detail="Triage could not be completed.",
        )

    finally:
        TRIAGE_DURATION.observe(time.perf_counter() - start_time)


@app.post("/triage/queue", status_code=202)
async def submit_triage_job(request: TriageRequest):
    """Submit a dispute for background processing."""
    try:
        report_data = request.report.model_dump(mode="json")
        job = enqueue_job(report_data)

        QUEUED_JOBS.inc()

        logger.info(
            "Triage job queued",
            extra={
                "job_id": job["job_id"],
                "case_id": job["case_id"],
            },
        )

        return {
            **job,
            "status_url": f"/triage/jobs/{job['job_id']}",
            "result_url": f"/triage/jobs/{job['job_id']}/result",
        }

    except RedisError:
        logger.exception("Unable to enqueue triage job.")

        raise HTTPException(
            status_code=503,
            detail="The triage queue is temporarily unavailable.",
        )


@app.get("/triage/jobs/{job_id}")
async def get_triage_job_status(job_id: str):
    """Retrieve the status of a queued job."""
    JOB_STATUS_REQUESTS.inc()

    try:
        job = get_job(job_id)
    except RedisError:
        logger.exception("Unable to retrieve job status.")

        raise HTTPException(
            status_code=503,
            detail="The job queue is temporarily unavailable.",
        )

    if job is None:
        raise HTTPException(
            status_code=404,
            detail="Job not found or its record has expired.",
        )

    return {
        "job_id": job["job_id"],
        "case_id": job.get("case_id"),
        "status": job["status"],
        "attempts": job.get("attempts", 0),
        "created_at": job.get("created_at"),
        "updated_at": job.get("updated_at"),
        "error": job.get("error"),
    }


@app.get("/triage/jobs/{job_id}/result")
async def get_triage_job_result(job_id: str):
    """Retrieve the result of a queued job."""
    try:
        job = get_job(job_id)
    except RedisError:
        logger.exception("Unable to retrieve job result.")

        raise HTTPException(
            status_code=503,
            detail="The job queue is temporarily unavailable.",
        )

    if job is None:
        raise HTTPException(
            status_code=404,
            detail="Job not found or its record has expired.",
        )

    if job["status"] in {"queued", "processing"}:
        return JSONResponse(
            status_code=202,
            content={
                "job_id": job["job_id"],
                "case_id": job.get("case_id"),
                "status": job["status"],
                "message": "The job has not finished yet.",
            },
        )

    if job["status"] == "failed":
        return JSONResponse(
            status_code=500,
            content={
                "job_id": job["job_id"],
                "case_id": job.get("case_id"),
                "status": "failed",
                "error": job.get("error"),
            },
        )

    return {
        "job_id": job["job_id"],
        "case_id": job["case_id"],
        "status": job["status"],
        "requires_human_review": True,
        "automated_liability_decision": False,
        "result": job.get("result"),
    }