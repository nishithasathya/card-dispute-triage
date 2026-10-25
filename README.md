# Card Dispute Triage

An AI-powered card dispute triage system that classifies customer complaints, retrieves relevant regulatory evidence, validates evidence citations, and routes cases for human review.

The system is designed to support dispute analysts by organizing complaint information and surfacing potentially relevant evidence. It does not make automated liability decisions.

## Key Features

- **Dispute Classification:** Classifies incoming complaints into dispute categories.
- **Evidence Retrieval:** Retrieves potentially relevant regulatory passages from an indexed corpus.
- **Evidence Verification:** Checks citation metadata and structural validity.
- **Human-in-the-Loop Review:** Routes cases for human review instead of automatically determining liability.
- **Input Validation:** Validates incoming requests and identifies invalid submissions.
- **Quarantine Handling:** Supports safe handling of requests that fail validation.
- **Prompt Injection Detection:** Uses heuristic detection to identify suspicious instructions in complaint text and escalates flagged cases for human review.
- **Evaluation Framework:** Evaluates classification, evidence coverage, citation validity, validation failures, and safety-related behavior.
- **Monitoring and Observability:** Uses Prometheus, Grafana, and Tempo as part of the monitoring stack.
- **Load Testing:** Includes scripts for basic API performance testing.

## Technology Stack

- Python 3.11
- FastAPI
- Retrieval-Augmented Generation (RAG) components
- FAISS for vector search
- Hugging Face models
- Redis
- Docker and Docker Compose
- Prometheus
- Grafana
- Tempo
- Pytest

## Project Structure

```text
card-dispute-triage/
├── corpus/
│   ├── raw/
│   └── processed/
│       └── faiss_index/
├── evaluation/
│   ├── evidence_scoring.py
│   ├── metrics.py
│   ├── run_evaluation.py
│   └── scenarios.json
├── monitoring/
│   ├── prometheus.yml
│   └── tempo.yaml
├── src/
│   ├── agents/
│   ├── static/
│   ├── api.py
│   ├── classifier.py
│   ├── decision_router.py
│   ├── graph.py
│   ├── ingest.py
│   ├── job_queue.py
│   ├── retrieve.py
│   ├── schemas.py
│   ├── triage.py
│   ├── verification.py
│   └── worker.py
├── tests/
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── load_test.py
├── locustfile.py
└── README.md
## System Workflow

1. Receive a customer dispute request through the API.
2. Validate the request against the expected schema.
3. Classify the dispute using the available complaint information.
4. Retrieve potentially relevant regulatory evidence.
5. Verify citation metadata and evidence structure.
6. Generate a triage recommendation based on the available information.
7. Route uncertain, suspicious, or complex cases for human review.
8. Record application metrics for monitoring and evaluation.
## Safety and Human Review

The system is designed to assist human analysts rather than replace them.

- It does not automatically determine liability.
- Cases requiring further assessment are routed for human review.
- Prompt injection detection uses heuristics and may not identify every attack.
- Evidence retrieval and citation validation do not independently establish legal relevance or prove that a passage supports a particular conclusion.
- Reporting-delay and credential-sharing circumstances require appropriate human assessment.

## Installation

### Prerequisites

Ensure the following tools are installed:

- Python 3.11
- Git
- Docker Desktop
- Docker Compose

### Install Dependencies

Navigate to the project root directory and create a virtual environment:

```bash
python3.11 -m venv .venv
```

Activate the virtual environment:

**macOS/Linux:**

```bash
source .venv/bin/activate
```

Install the required Python packages:

```bash
pip install -r requirements.txt
```

## Environment Configuration

The application uses environment variables for configuration.

1. Create a local environment file from the example:

   ```bash
   cp .env.example .env
   ```

2. Open `.env` and configure the required environment variables.
3. Ensure that the required credentials and configuration values are valid before starting the application.

**Security note:** Never commit `.env` to GitHub. It may contain passwords, API keys, and other sensitive information. Only commit `.env.example` with placeholder values.

## Running the Application

### Using Docker Compose

Ensure Docker Desktop is running before proceeding.

Validate the Docker Compose configuration:

```bash
docker compose config --quiet
```

Build the application images and start the services:

```bash
docker compose up --build -d
```

Check the status of the running services:

```bash
docker compose ps
```

View the API logs:

```bash
docker compose logs -f api
```

View the worker logs:

```bash
docker compose logs -f worker
```

Stop the services when finished:

```bash
docker compose down
```

### Accessing the Application

When the services are running, use the following local endpoints:

| Service | URL |
|---|---|
| API | `http://localhost:8000` |
| API Documentation | `http://localhost:8000/docs` |
| Prometheus | `http://localhost:9090` |
| Grafana | `http://localhost:3000` |
| Tempo | `http://localhost:3200` |

These endpoints are available only when the corresponding services are running and configured correctly.

## API Usage

The application exposes an API for processing card dispute complaints.

The API base address is:

```text
http://localhost:8000
```

Interactive API documentation is available at:

```text
http://localhost:8000/docs
```

The API supports dispute triage, including request validation, classification, evidence retrieval, and routing cases for human review.

Refer to `src/api.py` and the API documentation for the supported endpoints, request schemas, and response formats.

### Metrics Endpoint

Application metrics are exposed at:

```text
http://localhost:8000/metrics
```

These metrics can be collected by Prometheus to monitor application activity and performance.

## Evaluation

The project includes an evaluation framework for testing classification, evidence retrieval, citation validation, input validation, and safety-related behavior across predefined scenarios.

### Running the Evaluation

From the project root, execute:

```bash
PYTHONPATH=. python evaluation/run_evaluation.py
```

The evaluation report is generated at:

```text
evaluation/results/evaluation_report.json
```

### Recorded Evaluation Results

The latest recorded evaluation contained 22 scenarios and produced the following results:

| Metric | Result |
|---|---:|
| Classification Accuracy on Labelled Scenarios | 100% |
| Human Review Rate | 100% |
| Validation Failure Detection Rate | 100% |
| Evidence Coverage | 81.8% |
| Citation Metadata Validity | 100% |
| Automated Liability Decision Rate | 0% |
| Prompt Injection Detection Rate | 100% |
| Prompt Injection Escalation Rate | 100% |
| Execution Errors | 0 |

### Evaluation Interpretation

The results indicate that the system performed as expected on the current predefined evaluation scenarios.

- **Classification accuracy:** Measures correct classification on labelled scenarios.
- **Human review rate:** Measures the proportion of evaluated cases routed for human review.
- **Validation failure detection rate:** Measures the detection of deliberately invalid requests.
- **Evidence coverage:** Measures the proportion of evaluated cases with retrieved evidence according to the evaluation framework.
- **Citation metadata validity:** Measures whether retrieved evidence satisfies the configured structural and metadata checks.
- **Automated liability decision rate:** Measures how often the system makes an automated liability decision. The target is zero.
- **Prompt injection detection rate:** Measures detection on the evaluation scenarios containing prompt injection.
- **Prompt injection escalation rate:** Measures escalation of detected prompt injection cases for human review.

These results are specific to the current evaluation dataset. They do not guarantee equivalent performance on unseen or real-world complaints.

Some additional evidence-quality metrics use lexical-overlap heuristics. These metrics are approximate indicators and do not independently establish semantic correctness, legal relevance, or whether evidence fully supports a claim.

## Automated Testing

The project includes unit and integration tests for its core components.

### Running the Test Suite

From the project root, activate the virtual environment and run:

```bash
PYTHONPATH=. python -m pytest -q
```

A previously recorded test run completed with 67 passing tests.

Run the test suite again after making changes to verify the current state of the application.

### Test Coverage Areas

The test suite includes tests for:

- API request handling
- Request schema validation
- Dispute classification
- Decision routing
- Evidence analysis
- Retrieval behavior
- Triage workflow
- Graph integration
- Citation verification
- Evaluation metrics

## Monitoring and Observability

The project includes a monitoring stack consisting of Prometheus, Grafana, and Tempo.

### Prometheus

Prometheus collects application and worker metrics.

Open the Prometheus interface:

```text
http://localhost:9090
```

The configured targets include the API and worker services.

The `up` metric can be used to check whether a configured target is reachable.

Example query:

```promql
up
```

### Grafana

Grafana provides dashboards for monitoring application behavior.

Open Grafana:

```text
http://localhost:3000
```

The dashboard includes panels for:

- Total triage requests
- Successful triage runs
- Triage errors
- Average triage duration
- Active triage runs
- Total queued jobs

Grafana credentials depend on the local environment configuration.

### Tempo

Tempo provides tracing infrastructure for investigating application execution and service interactions.

The local Tempo endpoint is:

```text
http://localhost:3200
```

### Application Metrics

The API metrics endpoint is:

```text
http://localhost:8000/metrics
```

The exposed metrics include request counts, successful triage runs, execution errors, triage duration, active runs, and job queue activity.

Monitoring results depend on the services being configured and running correctly.

## Load Testing

The project includes `load_test.py` and `locustfile.py` for basic performance testing.

### Recorded Results

The following results were recorded during local smoke/load tests:

| Metric | Initial Test | Follow-up Test |
|---|---:|---:|
| Number of Requests | 10 | 20 |
| Successful HTTP Responses | 10 | 20 |
| Total Elapsed Time | 7.44 seconds | 4.504 seconds |
| Throughput | 1.34 requests/second | 4.44 requests/second |
| Average Latency | 1.49 seconds | 0.450 seconds |

All 30 requests across the two recorded tests received successful HTTP responses.

### Interpretation

The results provide an initial indication of API responsiveness under a small local workload.

They should not be interpreted as a production capacity benchmark. Performance may vary depending on hardware, model initialization, request complexity, concurrency, and available system resources.

### Running the Load Test

From the project root, run:

```bash
python load_test.py
```

Refer to `load_test.py` and `locustfile.py` for the implemented test configuration and request behavior.

## Limitations

The project has several limitations:

- Prompt injection detection relies on heuristics and may not identify every attack.
- Evidence retrieval may return incomplete or irrelevant passages.
- Citation metadata validation does not prove that evidence semantically supports a claim.
- Evaluation results are based on a limited set of predefined scenarios.
- Lexical-overlap metrics are approximations rather than definitive semantic assessments.
- Local load-test results do not establish production scalability.
- Ambiguous disputes and cases involving credential sharing or reporting delays require human assessment.

## Future Improvements

Potential improvements include:

- Expanding the evaluation dataset with more diverse and realistic dispute scenarios.
- Improving semantic evidence retrieval and relevance ranking.
- Introducing stronger claim-level evidence verification.
- Expanding adversarial testing for prompt injection and malicious inputs.
- Evaluating performance under larger and more realistic workloads.
- Improving monitoring, alerting, and failure recovery.
- Enhancing observability for asynchronous job processing.
- Improving the handling of ambiguous cases and conflicting evidence.

## Disclaimer

Card Dispute Triage is an academic decision-support prototype intended to assist dispute analysts.

It does not replace qualified human review, legal advice, or regulatory interpretation. Retrieved evidence and generated recommendations must be independently assessed before being used to make decisions about an actual financial dispute.