"""Benchmark 5 test queries against the streaming endpoint."""

import time
import json
import httpx

QUERIES = [
    "Where is the main entry point of this program?",
    "What functions modify the CUSTOMER-RECORD?",
    "Find all file I/O operations",
    "What are the dependencies of the codegen module?",
    "Show me error handling patterns in this codebase",
]

BASE = "http://127.0.0.1:8090"


def measure_query(query: str) -> dict:
    t0 = time.time()
    sources_t = first_t = done_t = None
    sources_data = None

    with httpx.Client() as client:
        with client.stream(
            "POST",
            f"{BASE}/api/query/stream",
            json={"query": query},
            timeout=30,
        ) as response:
            for line in response.iter_lines():
                now = time.time() - t0
                if line.startswith("data:") and sources_t is None:
                    data = line[5:].strip()
                    if data.startswith("["):
                        sources_t = now
                        sources_data = json.loads(data)
                elif line.startswith("data:") and first_t is None:
                    data = line[5:].strip()
                    if data.startswith('"'):
                        first_t = now
                elif line.startswith("data:") and "latency_ms" in line:
                    done_t = now
                    break

    return {
        "query": query[:50],
        "sources_s": sources_t or 0,
        "first_token_s": first_t or 0,
        "done_s": done_t or 0,
        "num_sources": len(sources_data) if sources_data else 0,
    }


def main():
    results = []
    for i, q in enumerate(QUERIES):
        if i > 0:
            time.sleep(3)  # avoid Groq rate limit
        r = measure_query(q)
        results.append(r)
        print(
            f"Q{i+1}: sources={r['sources_s']:.2f}s  "
            f"first_token={r['first_token_s']:.2f}s  "
            f"done={r['done_s']:.2f}s  "
            f"({r['num_sources']} chunks)"
        )

    print("\n--- SUMMARY ---")
    avg_done = sum(r["done_s"] for r in results) / len(results)
    avg_first = sum(r["first_token_s"] for r in results) / len(results)
    max_done = max(r["done_s"] for r in results)
    print(f"Avg total latency:      {avg_done:.2f}s")
    print(f"Avg first-token:        {avg_first:.2f}s")
    print(f"Max total latency:      {max_done:.2f}s")
    print(f"All under 3s:           {'YES' if max_done < 3.0 else 'NO'}")


if __name__ == "__main__":
    main()
