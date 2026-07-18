"""Benchmark scripts for PIIFilter."""

import asyncio
import json
import time
from pathlib import Path

from piifilter import FilterPipeline, FilterConfig
from piifilter.shared.models import FilterRequest

BENCHMARK_PROMPTS = [
    "Hi, I'm Susan from Acme Corp. My email is susan@acme.com and my phone is +1 555-123-4567.",
    "Our API key is sk-proj-abc123def456 and the database is at postgresql://admin:pass@db.internal:5432/prod.",
    "The contract for John Smith at 42 Wall Street, New York, NY 10005 needs review.",
    "My IP is 192.168.1.100 and my credit card is 4111-1111-1111-1111.",
    "The JWT token is eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3j1N9eN9kL0g. The SSH key is at ~/.ssh/id_rsa.",
    "Passport number AB123456 and social security 123-45-6789 are attached.",
    "Our office at 42 Broadway Avenue, San Francisco, CA needs security audit.",
]


async def run_benchmark(iterations: int = 100):
    """Run a benchmark across multiple prompts."""
    cfg = FilterConfig()
    pipeline = FilterPipeline(cfg)
    results = []

    print(f"Running benchmark with {iterations} iterations on {len(BENCHMARK_PROMPTS)} prompts...")
    print("-" * 60)

    for prompt in BENCHMARK_PROMPTS:
        req = FilterRequest(prompt=prompt)
        times = []

        for _ in range(iterations):
            start = time.perf_counter()
            result = await pipeline.filter(req)
            elapsed = (time.perf_counter() - start) * 1000
            times.append(elapsed)

        avg = sum(times) / len(times)
        max_t = max(times)
        min_t = min(times)
        p99 = sorted(times)[int(len(times) * 0.99)]
        entities = len(result.entities)

        results.append({
            "prompt_preview": prompt[:50],
            "entities": entities,
            "risk_score": result.risk.score,
            "risk_level": result.risk.level.value,
            "avg_ms": round(avg, 2),
            "min_ms": round(min_t, 2),
            "max_ms": round(max_t, 2),
            "p99_ms": round(p99, 2),
        })

        print(f"  {prompt[:50]:50s} → {entities:2d} entities | avg {avg:6.2f}ms | p99 {p99:6.2f}ms")

    print("-" * 60)
    all_avg = sum(r["avg_ms"] for r in results) / len(results)
    print(f"Overall average latency: {all_avg:.2f}ms")
    print(f"Target: <50ms — {'✅ PASS' if all_avg < 50 else '❌ FAIL'}")

    return results


if __name__ == "__main__":
    results = asyncio.run(run_benchmark())
    output_path = Path("benchmarks/results.json")
    output_path.write_text(json.dumps(results, indent=2))
    print(f"\nResults saved to {output_path}")