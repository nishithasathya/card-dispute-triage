import json
import statistics
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

API_URL = "http://localhost:8000/triage"

TOTAL_REQUESTS = 20
MAX_WORKERS = 2
TIMEOUT_SECONDS = 90


def make_payload(index):
    return {
        "report": {
            "case_id": f"LOAD-TEST-2-{index:03d}",
            "transaction_date": "2026-10-20",
            "report_date": "2026-10-25",
            "transaction_amount": 1500.00,
            "transaction_type": "online",
            "customer_noticed_alert": True,
            "credentials_shared": False,
            "alert_sent_date": "2026-10-20",
            "alert_noticed_date": "2026-10-20",
            "credentials_shared_date": None,
            "complaint_description": (
                f"Synthetic load test case {index}: "
                "I do not recognise this online card transaction "
                "and did not authorise it."
            ),
        }
    }


def send_request(index):
    request = urllib.request.Request(
        API_URL,
        data=json.dumps(make_payload(index)).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    started = time.perf_counter()

    try:
        with urllib.request.urlopen(
            request, timeout=TIMEOUT_SECONDS
        ) as response:
            response.read()
            return {
                "index": index,
                "status": response.status,
                "seconds": time.perf_counter() - started,
                "error": None,
            }

    except urllib.error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")[:300]
        return {
            "index": index,
            "status": exc.code,
            "seconds": time.perf_counter() - started,
            "error": details,
        }

    except Exception as exc:
        return {
            "index": index,
            "status": None,
            "seconds": time.perf_counter() - started,
            "error": str(exc),
        }


def summarize(label, results):
    if not results:
        print(f"\n{label}: no requests")
        return

    durations = [result["seconds"] for result in results]
    successful = sum(
        result["status"] is not None
        and 200 <= result["status"] < 300
        for result in results
    )

    print(f"\n{label}")
    print(f"Requests: {len(results)}")
    print(f"Successful: {successful}")
    print(f"Failed: {len(results) - successful}")
    print(f"Average: {statistics.mean(durations):.3f}s")
    print(f"Median: {statistics.median(durations):.3f}s")
    print(f"Maximum: {max(durations):.3f}s")


def main():
    print(f"Target: {API_URL}")
    print(f"Requests: {TOTAL_REQUESTS}")
    print(f"Concurrency: {MAX_WORKERS}\n")

    results = []
    started = time.perf_counter()

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [
            executor.submit(send_request, index)
            for index in range(1, TOTAL_REQUESTS + 1)
        ]

        for future in as_completed(futures):
            result = future.result()
            results.append(result)

            status = (
                str(result["status"])
                if result["status"] is not None
                else "ERROR"
            )

            print(
                f'Request {result["index"]:02d}: '
                f'HTTP {status}, {result["seconds"]:.3f}s'
            )

            if result["error"]:
                print(f'  Error: {result["error"]}')

    elapsed = time.perf_counter() - started
    results.sort(key=lambda result: result["index"])

    summarize("All requests", results)
    summarize("First 5 requests", results[:5])
    summarize("Remaining 15 requests", results[5:])

    print(f"\nTotal elapsed: {elapsed:.3f}s")
    print(f"Throughput: {len(results) / elapsed:.3f} requests/s")

    report = {
        "total_requests": len(results),
        "concurrency": MAX_WORKERS,
        "elapsed_seconds": round(elapsed, 3),
        "results": results,
    }

    with open("load_test_results_20.json", "w", encoding="utf-8") as file:
        json.dump(report, file, indent=2)

    print("Saved report to load_test_results_20.json")


if __name__ == "__main__":
    main()