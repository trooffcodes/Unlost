import os
import statistics
import threading
from time import perf_counter
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("OCR_KEY")
API_URL = "https://api.ocr.space/parse/image"
TEST_FILE = "test.png"
LANGUAGE = "eng"

WARMUP_REQUESTS = 2
SEQUENTIAL_REQUESTS = 10
CONCURRENCY_LEVELS = [1, 2, 3, 5, 10]
REQUESTS_PER_CONCURRENCY = 10
TIMEOUT = 120

results_lock = threading.Lock()


def percentile(values, percentile):
    if not values:
        return 0

    values = sorted(values)
    index = (len(values) - 1) * percentile
    lower = int(index)
    upper = min(lower + 1, len(values) - 1)
    weight = index - lower

    return values[lower] + (values[upper] - values[lower]) * weight


def ocr_space_file(filename, language=LANGUAGE):
    timings = {}

    total_start = perf_counter()

    request_setup_start = perf_counter()

    payload = {
        "apikey": API_KEY,
        "language": language,
        "isOverlayRequired": False
    }

    request_setup_end = perf_counter()

    file_open_start = perf_counter()

    with open(filename, "rb") as f:
        file_data = f.read()

    file_open_end = perf_counter()

    connection_start = perf_counter()

    response = requests.post(
        API_URL,
        files={
            "file": (
                os.path.basename(filename),
                file_data,
                "application/octet-stream"
            )
        },
        data=payload,
        timeout=TIMEOUT
    )

    response_end = perf_counter()

    json_start = perf_counter()
    result = response.json()
    json_end = perf_counter()

    total_end = perf_counter()

    timings["request_setup"] = request_setup_end - request_setup_start
    timings["file_read"] = file_open_end - file_open_start
    timings["network_request"] = response_end - connection_start
    timings["json_parse"] = json_end - json_start
    timings["total"] = total_end - total_start

    if response.status_code != 200:
        raise RuntimeError(
            f"HTTP {response.status_code}: {response.text[:500]}"
        )

    if result.get("IsErroredOnProcessing"):
        error_message = result.get("ErrorMessage", "Unknown OCR error")
        raise RuntimeError(str(error_message))

    parsed_results = result.get("ParsedResults", [])

    if not parsed_results:
        raise RuntimeError("OCR returned no ParsedResults")

    text = parsed_results[0].get("ParsedText", "")

    return text, timings


def run_single_request(request_id):
    start = perf_counter()

    try:
        text, timings = ocr_space_file(TEST_FILE)

        total = perf_counter() - start

        return {
            "id": request_id,
            "success": True,
            "text_length": len(text),
            "timings": timings,
            "total": total,
            "error": None
        }

    except Exception as e:
        total = perf_counter() - start

        return {
            "id": request_id,
            "success": False,
            "text_length": 0,
            "timings": {},
            "total": total,
            "error": str(e)
        }


def run_sequential_test():
    print("\n" + "=" * 70)
    print("SEQUENTIAL TEST")
    print("=" * 70)

    results = []

    for i in range(SEQUENTIAL_REQUESTS):
        result = run_single_request(i)
        results.append(result)

        if result["success"]:
            print(
                f"Request {i + 1}/{SEQUENTIAL_REQUESTS} | "
                f"{result['total']:.3f}s"
            )
        else:
            print(
                f"Request {i + 1}/{SEQUENTIAL_REQUESTS} | "
                f"FAILED | {result['error']}"
            )

    print_results(results, "Sequential")


def run_concurrent_test(concurrency):
    print("\n" + "=" * 70)
    print(f"CONCURRENT TEST: {concurrency} SIMULTANEOUS REQUESTS")
    print("=" * 70)

    results = []

    test_start = perf_counter()

    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = [
            executor.submit(run_single_request, i)
            for i in range(REQUESTS_PER_CONCURRENCY)
        ]

        for future in as_completed(futures):
            result = future.result()
            results.append(result)

            if result["success"]:
                print(
                    f"Request {result['id'] + 1}/{REQUESTS_PER_CONCURRENCY} | "
                    f"{result['total']:.3f}s"
                )
            else:
                print(
                    f"Request {result['id'] + 1}/{REQUESTS_PER_CONCURRENCY} | "
                    f"FAILED | {result['error']}"
                )

    test_total = perf_counter() - test_start

    print_results(
        results,
        f"{concurrency} Concurrent",
        test_total
    )


def print_results(results, test_name, wall_time=None):
    successful = [
        result for result in results
        if result["success"]
    ]

    failed = [
        result for result in results
        if not result["success"]
    ]

    if not results:
        return

    total_times = [
        result["total"]
        for result in successful
    ]

    network_times = [
        result["timings"]["network_request"]
        for result in successful
        if "network_request" in result["timings"]
    ]

    file_times = [
        result["timings"]["file_read"]
        for result in successful
        if "file_read" in result["timings"]
    ]

    json_times = [
        result["timings"]["json_parse"]
        for result in successful
        if "json_parse" in result["timings"]
    ]

    request_setup_times = [
        result["timings"]["request_setup"]
        for result in successful
        if "request_setup" in result["timings"]
    ]

    print("\n" + "-" * 70)
    print(f"{test_name} RESULTS")
    print("-" * 70)

    print(f"Total requests:       {len(results)}")
    print(f"Successful:            {len(successful)}")
    print(f"Failed:                {len(failed)}")

    if results:
        print(
            f"Success rate:          "
            f"{len(successful) / len(results) * 100:.2f}%"
        )

    if not successful:
        return

    print("\nTotal latency")
    print(f"Average:               {statistics.mean(total_times):.3f}s")
    print(f"Median / P50:          {percentile(total_times, 0.50):.3f}s")
    print(f"P95:                   {percentile(total_times, 0.95):.3f}s")
    print(f"P99:                   {percentile(total_times, 0.99):.3f}s")
    print(f"Minimum:               {min(total_times):.3f}s")
    print(f"Maximum:               {max(total_times):.3f}s")

    print("\nInternal timing")

    if file_times:
        print(
            f"File read average:     "
            f"{statistics.mean(file_times):.4f}s"
        )

    if request_setup_times:
        print(
            f"Request setup avg:     "
            f"{statistics.mean(request_setup_times):.4f}s"
        )

    if network_times:
        print(
            f"Network/API average:   "
            f"{statistics.mean(network_times):.3f}s"
        )

    if json_times:
        print(
            f"JSON parsing average:  "
            f"{statistics.mean(json_times):.4f}s"
        )

    if wall_time:
        print("\nThroughput")
        print(f"Wall-clock time:       {wall_time:.3f}s")
        print(
            f"Requests/second:       "
            f"{len(results) / wall_time:.2f}"
        )

    if failed:
        print("\nErrors")

        for result in failed:
            print(
                f"Request {result['id'] + 1}: "
                f"{result['error']}"
            )


def warmup():
    print("\n" + "=" * 70)
    print("WARMUP")
    print("=" * 70)

    for i in range(WARMUP_REQUESTS):
        start = perf_counter()

        try:
            ocr_space_file(TEST_FILE)
            elapsed = perf_counter() - start
            print(f"Warmup {i + 1}/{WARMUP_REQUESTS}: {elapsed:.3f}s")
        except Exception as e:
            print(f"Warmup {i + 1}/{WARMUP_REQUESTS}: FAILED | {e}")


def save_summary():
    pass


def main():
    if not API_KEY:
        raise RuntimeError("OCR_KEY is not set")

    if not os.path.exists(TEST_FILE):
        raise FileNotFoundError(TEST_FILE)

    print("=" * 70)
    print("OCR API PERFORMANCE BENCHMARK")
    print("=" * 70)
    print(f"API:                  {API_URL}")
    print(f"Test file:            {TEST_FILE}")
    print(f"Sequential requests:  {SEQUENTIAL_REQUESTS}")
    print(f"Concurrent levels:    {CONCURRENCY_LEVELS}")
    print(f"Requests per level:   {REQUESTS_PER_CONCURRENCY}")

    warmup()

    run_sequential_test()

    for concurrency in CONCURRENCY_LEVELS:
        run_concurrent_test(concurrency)


if __name__ == "__main__":
    main()