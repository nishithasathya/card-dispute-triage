"""
Locust load test for the Card Dispute Triage API.

Measures:
1. HTTP submission latency.
2. HTTP status-polling latency.
3. End-to-end time from job submission to completion.
4. Successful and failed background jobs.
5. Jobs that fail to finish within the polling timeout.

Uses synthetic test data only.
"""

import time
import uuid

from locust import HttpUser, between, task


class CardDisputeTriageUser(HttpUser):
    wait_time = between(1, 3)

    def on_start(self):
        self.case_prefix = f"LOAD-{uuid.uuid4().hex[:8]}"

    @task(3)
    def submit_triage_job(self):
        case_id = f"{self.case_prefix}-{uuid.uuid4().hex[:6]}"

        payload = {
            "report": {
                "case_id": case_id,
                "transaction_date": "2026-10-01",
                "report_date": "2026-10-22",
                "transaction_amount": 2500,
                "transaction_type": "card_not_present",
                "customer_noticed_alert": False,
                "credentials_shared": True,
                "alert_sent_date": "2026-10-01",
                "alert_noticed_date": None,
                "credentials_shared_date": "2026-10-01",
                "complaint_description": (
                    "A caller impersonating my bank requested my OTP. "
                    "I shared it and later discovered an unauthorised "
                    "card transaction. Please review the dispute."
                ),
            }
        }

        # Start measuring the complete workflow before submission.
        workflow_start = time.monotonic()

        with self.client.post(
            "/triage/queue",
            json=payload,
            name="POST /triage/queue",
            catch_response=True,
        ) as response:
            if response.status_code != 202:
                response.failure(
                    f"Expected HTTP 202; received {response.status_code}"
                )
                self.environment.events.request.fire(
                    request_type="WORKFLOW",
                    name="End-to-end triage completion",
                    response_time=(time.monotonic() - workflow_start) * 1000,
                    response_length=0,
                    exception=RuntimeError(
                        f"Submission failed with HTTP {response.status_code}"
                    ),
                    context={},
                )
                return

            try:
                result = response.json()
                job_id = result.get("job_id")
            except (ValueError, AttributeError):
                job_id = None

            if not job_id:
                response.failure("Response did not contain a valid job_id")
                self.environment.events.request.fire(
                    request_type="WORKFLOW",
                    name="End-to-end triage completion",
                    response_time=(time.monotonic() - workflow_start) * 1000,
                    response_length=0,
                    exception=RuntimeError("Missing job_id"),
                    context={},
                )
                return

            response.success()

        # Poll for up to 60 seconds for the background job to finish.
        deadline = time.monotonic() + 60

        while time.monotonic() < deadline:
            with self.client.get(
                f"/triage/jobs/{job_id}",
                name="GET /triage/jobs/[job_id]",
                catch_response=True,
            ) as status_response:
                if status_response.status_code != 200:
                    status_response.failure(
                        f"Unexpected HTTP {status_response.status_code}"
                    )
                    self.environment.events.request.fire(
                        request_type="WORKFLOW",
                        name="End-to-end triage completion",
                        response_time=(time.monotonic() - workflow_start) * 1000,
                        response_length=0,
                        exception=RuntimeError("Status polling failed"),
                        context={},
                    )
                    return

                try:
                    status_data = status_response.json()
                except ValueError:
                    status_response.failure("Invalid status JSON")
                    return

                status = status_data.get("status")

                if status == "completed":
                    status_response.success()
                    self.environment.events.request.fire(
                        request_type="WORKFLOW",
                        name="End-to-end triage completion",
                        response_time=(time.monotonic() - workflow_start) * 1000,
                        response_length=0,
                        exception=None,
                        context={},
                    )
                    return

                if status == "failed":
                    status_response.success()
                    self.environment.events.request.fire(
                        request_type="WORKFLOW",
                        name="End-to-end triage completion",
                        response_time=(time.monotonic() - workflow_start) * 1000,
                        response_length=0,
                        exception=RuntimeError(
                            f"Background job failed: {job_id}"
                        ),
                        context={},
                    )
                    return

                if status not in ("queued", "processing"):
                    status_response.failure(
                        f"Unexpected job status: {status!r}"
                    )
                    return

            # Avoid hammering the status endpoint.
            self.wait()

        # The job did not reach a terminal state within 60 seconds.
        self.environment.events.request.fire(
            request_type="WORKFLOW",
            name="End-to-end triage completion",
            response_time=(time.monotonic() - workflow_start) * 1000,
            response_length=0,
            exception=TimeoutError(
                f"Job {job_id} did not finish within 60 seconds"
            ),
            context={},
        )