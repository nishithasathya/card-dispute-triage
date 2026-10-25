"""Background worker for Redis-backed card dispute triage."""

import logging
import os
import signal
import time

from opentelemetry import propagate, trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
    OTLPSpanExporter,
)
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from prometheus_client import Counter, Histogram, start_http_server
from redis.exceptions import RedisError

from src.graph import DisputeAgentWorkflow
from src.job_queue import (
    acknowledge_job,
    check_redis,
    claim_next_job,
    recover_processing_jobs,
    retry_job,
    update_job,
)

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

logger = logging.getLogger(__name__)

POLL_TIMEOUT_SECONDS = max(
    1,
    int(os.getenv("WORKER_POLL_TIMEOUT_SECONDS", "5")),
)

SHUTDOWN_REQUESTED = False

# Worker Prometheus metrics.
WORKER_METRICS_PORT = int(
    os.getenv("WORKER_METRICS_PORT", "8001")
)

JOB_PROCESSING_DURATION = Histogram(
    "card_dispute_worker_job_processing_duration_seconds",
    "Time spent processing a claimed triage job inside the worker.",
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 30, 60),
)

JOB_PROCESSING_TOTAL = Counter(
    "card_dispute_worker_jobs_processed_total",
    "Number of jobs finished by the worker, labelled by outcome.",
    ["outcome"],
)

# Configure OpenTelemetry for the worker process.
OTEL_SERVICE_NAME = os.getenv(
    "OTEL_SERVICE_NAME",
    "card-dispute-worker",
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


def request_shutdown(signum, frame):
    """Request a graceful worker shutdown."""
    global SHUTDOWN_REQUESTED
    SHUTDOWN_REQUESTED = True
    logger.info(
        "Shutdown requested; finishing the current operation."
    )


signal.signal(signal.SIGTERM, request_shutdown)
signal.signal(signal.SIGINT, request_shutdown)


def process_job(job: dict, workflow: DisputeAgentWorkflow) -> None:
    """Process one job and record its processing duration."""

    job_id = job["job_id"]
    report_data = job.get("report")

    # Count exactly one attempt each time processing begins.
    job["attempts"] = int(job.get("attempts", 0)) + 1

    # Extract the API request's trace context saved with the queued job.
    parent_context = propagate.extract(
        job.get("trace_context", {})
    )

    # Start timing after the worker has claimed the job.
    processing_start = time.perf_counter()
    outcome = "failed"

    with tracer.start_as_current_span(
        "worker.process_job",
        context=parent_context,
    ) as span:
        span.set_attribute("job.id", str(job_id))
        span.set_attribute(
            "job.attempt",
            int(job["attempts"]),
        )
        span.set_attribute(
            "dispute.case_id",
            str(job.get("case_id", "unknown")),
        )

        try:
            update_job(job, status="processing")

            from src.schemas import DisputeReport

            report = DisputeReport.model_validate(report_data)

            with tracer.start_as_current_span(
                "worker.triage_workflow"
            ):
                result = workflow.run(report)

            # Safety invariant: the service recommends actions but never
            # makes the final liability decision or closes a dispute.
            if not isinstance(result, dict):
                raise ValueError(
                    "The triage workflow returned an invalid result."
                )

            result["requires_human_review"] = True

            routing = result.get("routing")
            if isinstance(routing, dict):
                routing["requires_human_review"] = True
                routing["automated_liability_decision"] = False

            update_job(
                job,
                status="completed",
                result=result,
            )

            acknowledge_job(job_id)

            outcome = "success"
            span.set_attribute("job.status", "completed")

            logger.info(
                "Job completed: job_id=%s case_id=%s attempt=%s",
                job_id,
                job.get("case_id"),
                job["attempts"],
            )

        except Exception as exc:
            span.set_attribute("job.status", "failed")
            span.record_exception(exc)
            span.set_status(
                trace.Status(
                    trace.StatusCode.ERROR,
                    description=str(exc)[:200],
                )
            )

            logger.exception(
                "Job processing failed: job_id=%s attempt=%s",
                job_id,
                job["attempts"],
            )

            try:
                retry_job(
                    job,
                    error=f"{type(exc).__name__}: {str(exc)[:500]}",
                )
            except RedisError:
                # Leave the processing entry in Redis if queue operations fail.
                # Startup recovery can requeue it after the worker restarts.
                logger.exception(
                    "Could not update retry state for job %s",
                    job_id,
                )

        finally:
            duration = time.perf_counter() - processing_start

            JOB_PROCESSING_DURATION.observe(duration)
            JOB_PROCESSING_TOTAL.labels(outcome=outcome).inc()

            span.set_attribute(
                "job.processing_duration_seconds",
                duration,
            )

            logger.info(
                "Job processing measurement: "
                "job_id=%s case_id=%s outcome=%s duration_seconds=%.4f",
                job_id,
                job.get("case_id"),
                outcome,
                duration,
            )


def run_worker() -> None:
    """Run the single-worker polling loop."""

    logger.info("Starting card dispute triage worker.")

    try:
        start_http_server(WORKER_METRICS_PORT)
        logger.info(
            "Worker Prometheus metrics available on port %s.",
            WORKER_METRICS_PORT,
        )
    except OSError:
        logger.exception(
            "Could not start worker metrics server on port %s.",
            WORKER_METRICS_PORT,
        )
        raise

    while not SHUTDOWN_REQUESTED:
        try:
            if not check_redis():
                logger.warning("Redis is not ready.")
                time.sleep(2)
                continue

            # Recover abandoned jobs when the worker starts.
            # This deployment assumes only one worker process.
            recover_processing_jobs()
            break

        except RedisError:
            logger.exception(
                "Redis unavailable during worker startup."
            )
            time.sleep(2)

    if SHUTDOWN_REQUESTED:
        logger.info("Worker shutdown requested during startup.")

    else:
        try:
            # Initialise the workflow once per worker process.
            # The embedding model and FAISS index can now be reused
            # across jobs instead of being reconstructed for every job.
            logger.info("Initialising shared triage workflow.")
            workflow = DisputeAgentWorkflow()
            logger.info("Shared triage workflow initialised.")

            while not SHUTDOWN_REQUESTED:
                try:
                    job = claim_next_job(
                        timeout_seconds=POLL_TIMEOUT_SECONDS,
                    )

                    if job is None:
                        continue

                    process_job(job, workflow)

                except RedisError:
                    logger.exception(
                        "Redis operation failed; retrying shortly."
                    )
                    time.sleep(2)

                except Exception:
                    logger.exception("Unexpected worker error.")
                    time.sleep(1)

        except Exception:
            logger.exception(
                "Worker could not initialise the triage workflow."
            )

    logger.info("Worker shutdown complete.")

    # Flush queued spans before the process exits.
    try:
        trace_provider.force_flush(timeout_millis=5000)
        trace_provider.shutdown()
    except Exception:
        logger.exception("Failed to flush worker traces.")


if __name__ == "__main__":
    run_worker()