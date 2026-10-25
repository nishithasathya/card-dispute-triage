"""Redis-backed job queue for card dispute triage."""

import json
import logging
import os
import time
import uuid
from typing import Any

import redis
from redis.exceptions import RedisError

from opentelemetry import propagate
from prometheus_client import Histogram

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

QUEUE_KEY = "card_dispute:jobs:pending"
PROCESSING_KEY = "card_dispute:jobs:processing"
RESULT_PREFIX = "card_dispute:job:"

JOB_TTL_SECONDS = max(60, int(os.getenv("JOB_TTL_SECONDS", "86400")))
MAX_ATTEMPTS = max(1, int(os.getenv("JOB_MAX_ATTEMPTS", "3")))

POLL_TIMEOUT_SECONDS = max(
    1,
    int(os.getenv("WORKER_POLL_TIMEOUT_SECONDS", "5")),
)

redis_client = redis.Redis.from_url(
    REDIS_URL,
    decode_responses=True,
    socket_connect_timeout=3,
    socket_timeout=POLL_TIMEOUT_SECONDS + 10,
    health_check_interval=30,
)

JOB_QUEUE_WAIT_SECONDS = Histogram(
    "card_dispute_job_queue_wait_seconds",
    "Time from initial job creation until a worker first claims it.",
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 30, 60),
)


def _job_key(job_id: str) -> str:
    return f"{RESULT_PREFIX}{job_id}"


def check_redis() -> bool:
    return bool(redis_client.ping())


def enqueue_job(report: dict[str, Any]) -> dict[str, Any]:
    """Create a job, preserve trace context, and queue its ID."""
    now = time.time()
    job_id = str(uuid.uuid4())

    trace_context: dict[str, str] = {}
    propagate.inject(trace_context)

    job = {
        "job_id": job_id,
        "case_id": report.get("case_id"),
        "status": "queued",
        "attempts": 0,
        "created_at": now,
        "updated_at": now,
        "claimed_at": None,
        "queue_wait_seconds": None,
        "report": report,
        "trace_context": trace_context,
        "result": None,
        "error": None,
    }

    try:
        with redis_client.pipeline(transaction=True) as pipe:
            pipe.set(
                _job_key(job_id),
                json.dumps(job),
                ex=JOB_TTL_SECONDS,
            )
            pipe.rpush(QUEUE_KEY, job_id)
            pipe.execute()
    except RedisError:
        logger.exception("Failed to enqueue job %s", job_id)
        raise

    return {
        "job_id": job_id,
        "case_id": job["case_id"],
        "status": job["status"],
        "created_at": now,
    }


def get_job(job_id: str) -> dict[str, Any] | None:
    """Retrieve a job by ID."""
    try:
        raw_job = redis_client.get(_job_key(job_id))
    except RedisError:
        logger.exception("Failed to retrieve job %s", job_id)
        raise

    if raw_job is None:
        return None

    try:
        return json.loads(raw_job)
    except json.JSONDecodeError:
        logger.error("Invalid JSON stored for job %s", job_id)
        return None


def claim_next_job(timeout_seconds: int = 5) -> dict[str, Any] | None:
    """Atomically claim a job and measure its initial queue wait."""
    wait_seconds = max(0, int(timeout_seconds))

    try:
        job_id = redis_client.blmove(
            QUEUE_KEY,
            PROCESSING_KEY,
            timeout=wait_seconds,
            src="LEFT",
            dest="RIGHT",
        )
    except RedisError:
        logger.exception("Failed to claim a queued job")
        raise

    if job_id is None:
        return None

    job = get_job(job_id)

    if job is None:
        logger.error("Queued job %s has no stored job record", job_id)
        acknowledge_job(job_id)
        return None

    # Record the first claim only. A retry should not overwrite the
    # original queue-wait measurement.
    if job.get("claimed_at") is None:
        claimed_at = time.time()
        created_at = float(job.get("created_at", claimed_at))
        queue_wait = max(0.0, claimed_at - created_at)

        job["claimed_at"] = claimed_at
        job["queue_wait_seconds"] = queue_wait

        try:
            redis_client.set(
                _job_key(job_id),
                json.dumps(job),
                ex=JOB_TTL_SECONDS,
            )
        except RedisError:
            logger.exception(
                "Failed to save queue-wait measurement for job %s",
                job_id,
            )
            # Preserve the existing job-processing behavior even if
            # this optional measurement cannot be saved.
        else:
            JOB_QUEUE_WAIT_SECONDS.observe(queue_wait)

            logger.info(
                "Job queue wait: job_id=%s case_id=%s "
                "queue_wait_seconds=%.4f",
                job_id,
                job.get("case_id"),
                queue_wait,
            )

    return job


def update_job(
    job: dict[str, Any],
    status: str,
    result: Any = None,
    error: str | None = None,
) -> dict[str, Any]:
    """Update a job while preserving its existing result and context."""
    updated_job = dict(job)
    updated_job["status"] = status
    updated_job["updated_at"] = time.time()

    if result is not None:
        updated_job["result"] = result

    if error is not None:
        updated_job["error"] = error
    elif status in {"completed", "queued", "processing"}:
        updated_job["error"] = None

    try:
        redis_client.set(
            _job_key(updated_job["job_id"]),
            json.dumps(updated_job),
            ex=JOB_TTL_SECONDS,
        )
    except RedisError:
        logger.exception(
            "Failed to update job %s",
            updated_job.get("job_id"),
        )
        raise

    job.update(updated_job)
    return updated_job


def acknowledge_job(job_id: str) -> None:
    """Remove a job ID from the processing list."""
    try:
        redis_client.lrem(PROCESSING_KEY, 1, job_id)
    except RedisError:
        logger.exception("Failed to acknowledge job %s", job_id)
        raise


def retry_job(job: dict[str, Any], error: str) -> str:
    """Requeue a failed job or mark it permanently failed."""
    job_id = job["job_id"]
    attempts = int(job.get("attempts", 0))

    if attempts >= MAX_ATTEMPTS:
        update_job(job, status="failed", error=error)
        acknowledge_job(job_id)

        logger.error(
            "Job %s failed after %s attempts",
            job_id,
            attempts,
        )
        return "failed"

    update_job(job, status="queued", error=error)

    try:
        redis_client.lpush(QUEUE_KEY, job_id)
        acknowledge_job(job_id)
    except RedisError:
        logger.exception("Failed to requeue job %s", job_id)
        raise

    logger.warning(
        "Requeued job %s after attempt %s",
        job_id,
        attempts,
    )
    return "queued"


def recover_processing_jobs() -> int:
    """Recover unfinished jobs after a single worker restarts."""
    recovered = 0

    try:
        processing_ids = redis_client.lrange(PROCESSING_KEY, 0, -1)

        for job_id in processing_ids:
            job = get_job(job_id)

            if job is None or job.get("status") in {"completed", "failed"}:
                acknowledge_job(job_id)
                continue

            update_job(
                job,
                status="queued",
                error="Recovered after worker restart.",
            )

            redis_client.lpush(QUEUE_KEY, job_id)
            acknowledge_job(job_id)
            recovered += 1

    except RedisError:
        logger.exception("Failed to recover processing jobs")
        raise

    if recovered:
        logger.warning("Recovered %s interrupted jobs", recovered)

    return recovered