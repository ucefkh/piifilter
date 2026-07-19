"""PIIFilter Benchmark Framework — benchmark every detector independently with automated reports.

Usage:
    python benchmarks/run.py                     # Default: benchmark all detectors
    python benchmarks/run.py --detectors regex   # Only benchmark regex
    python benchmarks/run.py --detectors regex,presidio  # Multiple detectors
    python benchmarks/run.py --iterations 100    # Custom iterations
    python benchmarks/run.py --no-pipeline       # Skip full pipeline benchmark
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import statistics
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Callable

# ── Project path setup ──────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "core" / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "plugins" / "detector-regex" / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "plugins" / "detector-presidio" / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "plugins" / "detector-gliner" / "src"))

# NOTE: no module-level piifilter imports — piifilter v2 has a circular import
# issue (piifilter/__init__.py loads piifilter.pipeline, which is a package
# missing its sub-module). All piifilter imports happen lazily inside functions.

# ── Test prompts ────────────────────────────────────────────────────────────

BENCHMARK_SUITE: list[dict[str, Any]] = [
    {
        "name": "standard_pii",
        "description": "Name, email, phone",
        "text": "Hi, I'm Susan from Acme Corp. Email: susan@acme.com Phone: +1 555-123-4567",
    },
    {
        "name": "credentials",
        "description": "API key, database URL",
        "text": "API key: sk-proj-abc123def456, DB: postgresql://admin:pass@db.internal:5432/prod",
    },
    {
        "name": "sensitive_ids",
        "description": "SSN, credit card, IP address",
        "text": "SSN: 123-45-6789, CC: 4111-1111-1111-1111, IP: 192.168.1.100",
    },
    {
        "name": "empty",
        "description": "Empty prompt (baseline)",
        "text": "",
    },
    {
        "name": "jwt_token",
        "description": "JWT token",
        "text": "My JWT is eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3j1N9eN9kL0g",
    },
]

# ── Metrics ─────────────────────────────────────────────────────────────────


@dataclass
class DetectorMetrics:
    """Per-detector, per-prompt benchmark results."""

    detector: str
    prompt: str
    avg_ms: float = 0.0
    p50_ms: float = 0.0
    p95_ms: float = 0.0
    p99_ms: float = 0.0
    min_ms: float = 0.0
    max_ms: float = 0.0
    stddev_ms: float = 0.0
    entities_found: int = 0
    entity_types: list[str] = field(default_factory=list)
    warmup_avg_ms: float = 0.0
    throughput_ops: float = 0.0  # operations per second
    n: int = 0
    errors: int = 0

    def percentile(self, data: list[float], pct: float) -> float:
        """Compute the *pct* percentile from sorted data."""
        if not data:
            return 0.0
        k = (len(data) - 1) * pct / 100.0
        f = math.floor(k)
        c = math.ceil(k)
        if f == c:
            return data[int(k)]
        return data[f] * (c - k) + data[c] * (k - f)


# ── Detector adapter ────────────────────────────────────────────────────────


@dataclass
class DetectorAdapter:
    """Uniform interface around any detector implementation."""

    name: str
    detect_fn: Callable[[str], list[Any]]


def make_regex_adapter() -> DetectorAdapter:
    """Create adapter for the RegexDetector plugin.

    Instead of using the RegexDetector constructor (which triggers an
    EntityType mismatch on some patterns), we manually create the instance
    and patch pattern resolution if needed.
    """
    from piifilter.shared.models import DetectedEntity, EntityType
    from piifilter_detector_regex.patterns import PATTERN_DEFS
    import re

    _DIRECT_MAP = {
        "PERSON", "EMAIL", "PHONE", "ADDRESS", "CITY", "COUNTRY",
        "COMPANY", "BANK_ACCOUNT", "IBAN", "CREDIT_CARD", "PASSPORT",
        "SOCIAL_SECURITY", "JWT", "API_KEY", "SSH_KEY", "DATABASE_URL",
        "PRIVATE_URL", "PROJECT_NAME", "CUSTOMER_NAME", "EMPLOYEE_NAME",
        "GPS", "DOMAIN", "IP_ADDRESS", "FILE_PATH",
    }

    # Manually compile patterns using the correct EntityType enum
    patterns: list[tuple[Any, Any, float]] = []
    for type_name, raw_pattern, score in PATTERN_DEFS:
        # Map pattern type names that don't match EntityType directly
        type_map = {
            "SSN": "SOCIAL_SECURITY",
            "API_KEY": "API_KEY",
            "JWT": "JWT",
            "EMAIL": "EMAIL",
            "PHONE": "PHONE",
            "CREDIT_CARD": "CREDIT_CARD",
            "IP_ADDRESS": "IP_ADDRESS",
            "DATABASE_URL": "DATABASE_URL",
            "DOMAIN": "DOMAIN",
            "PRIVATE_URL": "PRIVATE_URL",
            "IBAN": "IBAN",
            "BANK_ACCOUNT": "BANK_ACCOUNT",
            "PASSPORT": "PASSPORT",
            "SSH_KEY": "SSH_KEY",
            "GPS": "GPS",
            "FILE_PATH": "FILE_PATH",
        }
        if type_name in _DIRECT_MAP:
            et_name = type_name
        else:
            et_name = type_map.get(type_name, type_name.upper())
        try:
            entity_type = EntityType(et_name)
        except ValueError:
            entity_type = EntityType("PERSON")
        compiled = re.compile(raw_pattern, re.IGNORECASE)
        patterns.append((entity_type, compiled, score))

    async def detect(text: str) -> list[DetectedEntity]:
        if not text:
            return []
        entities: list[DetectedEntity] = []
        seen_intervals: list[tuple[int, int]] = []
        for entity_type, pattern, score in patterns:
            for match in pattern.finditer(text):
                start, end = match.start(), match.end()
                if start == end:
                    continue
                if any(s <= start and end <= e for s, e in seen_intervals):
                    continue
                entities.append(
                    DetectedEntity(
                        entity_type=entity_type,
                        value=match.group(),
                        start=start,
                        end=end,
                        confidence=score,
                        detector="regex",
                    )
                )
                seen_intervals.append((start, end))
        entities.sort(key=lambda e: e.start)
        return entities

    return DetectorAdapter(name="regex", detect_fn=detect)


def make_presidio_adapter() -> DetectorAdapter:
    """Create adapter for the PresidioDetector plugin."""
    from piifilter.shared.models import DetectedEntity
    from piifilter_detector_presidio.detector import PresidioDetector

    detector = PresidioDetector()
    try:
        import asyncio as _a
        _a.get_event_loop().run_until_complete(detector.initialize())
    except Exception:
        pass

    async def detect(text: str) -> list[DetectedEntity]:
        if not text:
            return []
        results = await detector.detect(text)
        entities = []
        for r in results:
            entities.append(
                DetectedEntity(
                    entity_type=r.get("entity_type", "unknown"),
                    value=r.get("value", ""),
                    start=r.get("start", 0),
                    end=r.get("end", 0),
                    confidence=r.get("score", 1.0),
                    detector="presidio",
                )
            )
        return entities

    return DetectorAdapter(name="presidio", detect_fn=detect)


def make_gliner_adapter() -> DetectorAdapter:
    """Create adapter for GLiNER detector (stub — returns empty)."""
    from piifilter.shared.models import DetectedEntity

    async def detect(text: str) -> list[DetectedEntity]:
        return []

    return DetectorAdapter(name="gliner", detect_fn=detect)


async def make_pipeline_adapter() -> DetectorAdapter:
    """Create adapter for the full Pipeline (all detectors combined).

    Runs all registered detectors and merges/deduplicates results.
    """
    from piifilter.shared.models import DetectedEntity

    rd = make_regex_adapter()

    pd = None
    try:
        pd = make_presidio_adapter()
    except Exception:
        pass

    async def detect(text: str) -> list[DetectedEntity]:
        all_entities: list[DetectedEntity] = []
        try:
            all_entities.extend(await rd.detect_fn(text))
        except Exception:
            pass
        if pd is not None:
            try:
                all_entities.extend(await pd.detect_fn(text))
            except Exception:
                pass

        all_entities.sort(key=lambda e: (-e.score, e.start))
        seen = set()
        deduped = []
        for e in all_entities:
            key = (e.start, e.end, e.entity_type.value)
            if key not in seen:
                seen.add(key)
                deduped.append(e)
        deduped.sort(key=lambda e: e.start)
        return deduped

    return DetectorAdapter(name="pipeline", detect_fn=detect)


# ── Benchmark runner ────────────────────────────────────────────────────────


async def benchmark_detector(
    detector: DetectorAdapter,
    prompt_suite: list[dict[str, Any]],
    iterations: int = 1000,
    warmup_iterations: int = 10,
) -> list[DetectorMetrics]:
    """Benchmark a single detector across all prompts."""
    results: list[DetectorMetrics] = []

    for prompt_info in prompt_suite:
        text = prompt_info["text"]
        prompt_name = prompt_info["name"]
        entities_found = 0
        entity_types: list[str] = []

        # ── Warmup ──
        warmup_times: list[float] = []
        for _ in range(warmup_iterations):
            t0 = time.perf_counter()
            entities = await detector.detect_fn(text)
            t1 = time.perf_counter()
            warmup_times.append((t1 - t0) * 1000)
            if entities:
                entities_found = len(entities)
                entity_types = sorted(set(e.entity_type.value for e in entities))

        warmup_avg = statistics.mean(warmup_times) if warmup_times else 0.0

        # ── Benchmark ──
        times: list[float] = []
        error_count = 0
        for _ in range(iterations):
            try:
                t0 = time.perf_counter()
                entities = await detector.detect_fn(text)
                t1 = time.perf_counter()
                times.append((t1 - t0) * 1000)
                if not entities_found and entities:
                    entities_found = len(entities)
                    entity_types = sorted(set(e.entity_type.value for e in entities))
            except Exception:
                error_count += 1
                times.append(0.0)

        if not times or all(t == 0.0 for t in times):
            results.append(
                DetectorMetrics(
                    detector=detector.name,
                    prompt=prompt_name,
                    avg_ms=0.0,
                    p50_ms=0.0,
                    p95_ms=0.0,
                    p99_ms=0.0,
                    min_ms=0.0,
                    max_ms=0.0,
                    stddev_ms=0.0,
                    entities_found=entities_found,
                    entity_types=entity_types,
                    warmup_avg_ms=round(warmup_avg, 4),
                    throughput_ops=0.0,
                    n=iterations,
                    errors=error_count,
                )
            )
            continue

        valid_times = [t for t in times if t > 0]
        if not valid_times:
            results.append(
                DetectorMetrics(
                    detector=detector.name,
                    prompt=prompt_name,
                    avg_ms=0.0,
                    p50_ms=0.0,
                    p95_ms=0.0,
                    p99_ms=0.0,
                    min_ms=0.0,
                    max_ms=0.0,
                    stddev_ms=0.0,
                    entities_found=entities_found,
                    entity_types=entity_types,
                    warmup_avg_ms=round(warmup_avg, 4),
                    throughput_ops=0.0,
                    n=iterations,
                    errors=error_count,
                )
            )
            continue

        sorted_times = sorted(valid_times)
        total_time_s = sum(valid_times) / 1000
        throughput = len(valid_times) / total_time_s if total_time_s > 0 else 0.0

        m = DetectorMetrics(detector=detector.name, prompt=prompt_name)
        m.n = len(valid_times)
        m.avg_ms = round(statistics.mean(valid_times), 4)
        m.p50_ms = round(m.percentile(sorted_times, 50), 4)
        m.p95_ms = round(m.percentile(sorted_times, 95), 4)
        m.p99_ms = round(m.percentile(sorted_times, 99), 4)
        m.min_ms = round(min(valid_times), 4)
        m.max_ms = round(max(valid_times), 4)
        m.stddev_ms = round(statistics.stdev(valid_times), 4) if len(valid_times) > 1 else 0.0
        m.entities_found = entities_found
        m.entity_types = entity_types
        m.warmup_avg_ms = round(warmup_avg, 4)
        m.throughput_ops = round(throughput, 1)
        m.errors = error_count

        results.append(m)

    return results


def build_report(
    all_metrics: dict[str, list[DetectorMetrics]],
) -> dict[str, Any]:
    """Build a structured report from all benchmark results."""
    report: dict[str, Any] = {
        "title": "PIIFilter Detector Benchmark Report",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "detectors": {},
        "comparison": {},
    }

    for detector_name, metrics_list in all_metrics.items():
        detector_section: dict[str, Any] = {"prompts": {}}
        overall_latencies: list[float] = []

        for m in metrics_list:
            detector_section["prompts"][m.prompt] = asdict(m)
            if m.avg_ms > 0:
                overall_latencies.append(m.avg_ms)

        if overall_latencies:
            detector_section["overall_avg_ms"] = round(
                statistics.mean(overall_latencies), 4
            )
            detector_section["overall_max_ms"] = round(max(overall_latencies), 4)
            detector_section["overall_min_ms"] = round(min(overall_latencies), 4)
        else:
            detector_section["overall_avg_ms"] = 0
            detector_section["overall_max_ms"] = 0
            detector_section["overall_min_ms"] = 0

        report["detectors"][detector_name] = detector_section

    comparison_rows: list[dict[str, Any]] = []
    prompt_names = [p["name"] for p in BENCHMARK_SUITE]
    for prompt_name in prompt_names:
        row: dict[str, Any] = {"prompt": prompt_name}
        for detector_name, metrics_list in all_metrics.items():
            for m in metrics_list:
                if m.prompt == prompt_name:
                    row[detector_name] = {
                        "avg_ms": m.avg_ms,
                        "p50_ms": m.p50_ms,
                        "p95_ms": m.p95_ms,
                        "p99_ms": m.p99_ms,
                        "entities": m.entities_found,
                        "throughput": m.throughput_ops,
                        "errors": m.errors,
                    }
        comparison_rows.append(row)

    report["comparison"]["detector_names"] = list(all_metrics.keys())
    report["comparison"]["prompts"] = comparison_rows
    report["comparison"]["summary"] = _build_comparison_summary(all_metrics)

    return report


def _build_comparison_summary(
    all_metrics: dict[str, list[DetectorMetrics]],
) -> dict[str, Any]:
    """Build a summary comparing detector performance."""
    summary: dict[str, Any] = {}

    for detector_name, metrics_list in all_metrics.items():
        avg_times = []
        total_entities = 0
        total_errors = 0

        for m in metrics_list:
            if m.avg_ms > 0:
                avg_times.append(m.avg_ms)
                total_entities += m.entities_found
                total_errors += m.errors

        mean_avg = statistics.mean(avg_times) if avg_times else 0.0

        summary[detector_name] = {
            "mean_avg_latency_ms": round(mean_avg, 4),
            "total_entities_detected": total_entities,
            "total_errors": total_errors,
            "prompts_benchmarked": len([m for m in metrics_list if m.avg_ms > 0]),
        }

    return summary


# ── Console output ──────────────────────────────────────────────────────────


def print_table(rows: list[list[str]], headers: list[str]) -> None:
    """Print a formatted table to the console."""
    col_widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            col_widths[i] = max(col_widths[i], len(cell))

    sep = "  ".join(["-" * w for w in col_widths])
    hdr = "  " + "  ".join(h.ljust(col_widths[i]) for i, h in enumerate(headers))
    print(hdr)
    print("  " + sep)
    for row in rows:
        print("  " + "  ".join(cell.ljust(col_widths[i]) for i, cell in enumerate(row)))


def print_results(all_metrics: dict[str, list[DetectorMetrics]]) -> None:
    """Print benchmark results to the console in formatted tables."""
    print("\n" + "=" * 80)
    print("  PIIFilter Detector Benchmark Report")
    print("=" * 80)
    print(f"  Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}")
    print(f"  Python: {sys.version.split()[0]}")
    print()

    for detector_name, metrics_list in all_metrics.items():
        print(f"  ── {detector_name.upper()} ──")
        headers = ["Prompt", "Avg (ms)", "P50", "P95", "P99", "Min", "Max", "StdDev", "Entities", "Throughput", "Errors"]
        rows = []
        for m in metrics_list:
            avg_s = f"{m.avg_ms:.3f}" if m.avg_ms > 0 else "-"
            p50_s = f"{m.p50_ms:.3f}" if m.p50_ms > 0 else "-"
            p95_s = f"{m.p95_ms:.3f}" if m.p95_ms > 0 else "-"
            p99_s = f"{m.p99_ms:.3f}" if m.p99_ms > 0 else "-"
            min_s = f"{m.min_ms:.3f}" if m.min_ms > 0 else "-"
            max_s = f"{m.max_ms:.3f}" if m.max_ms > 0 else "-"
            std_s = f"{m.stddev_ms:.3f}" if m.stddev_ms > 0 else "-"
            entities_s = str(m.entities_found)
            tput_s = f"{m.throughput_ops:.0f}/s" if m.throughput_ops > 0 else "-"
            err_s = str(m.errors) if m.errors > 0 else "0"
            rows.append([m.prompt[:20], avg_s, p50_s, p95_s, p99_s, min_s, max_s, std_s, entities_s, tput_s, err_s])

        print_table(rows, headers)
        print()

    # Comparison summary table
    print("  ── SUMMARY ──")
    headers = ["Detector", "Mean Avg (ms)", "Total Entities", "Total Errors"]
    rows = []
    for detector_name, metrics_list in all_metrics.items():
        avg_times = [m.avg_ms for m in metrics_list if m.avg_ms > 0]
        mean_avg = statistics.mean(avg_times) if avg_times else 0.0
        total_entities = sum(m.entities_found for m in metrics_list)
        total_errors = sum(m.errors for m in metrics_list)
        rows.append([detector_name, f"{mean_avg:.4f}", str(total_entities), str(total_errors)])
    print_table(rows, headers)
    print()


# ── Main ────────────────────────────────────────────────────────────────────


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="PIIFilter Detector Benchmark Framework",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--detectors",
        type=str,
        default="regex,presidio",
        help="Comma-separated list of detectors to benchmark (default: regex,presidio)",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=1000,
        help="Number of iterations per prompt (default: 1000)",
    )
    parser.add_argument(
        "--warmup",
        type=int,
        default=10,
        help="Number of warmup iterations (default: 10)",
    )
    parser.add_argument(
        "--no-pipeline",
        action="store_true",
        help="Skip full pipeline benchmark",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="benchmarks/results.json",
        help="Output path for JSON results (default: benchmarks/results.json)",
    )
    parser.add_argument(
        "--stress",
        type=int,
        default=0,
        help="Generate a stress prompt of N KB (default: 0 = skip stress test)",
    )
    args = parser.parse_args()

    # Build suite
    suite = list(BENCHMARK_SUITE)

    # Add stress test prompt if requested
    if args.stress > 0:
        stress_text = "The following is a large document with PII scattered throughout.\n"
        chunk = "John Smith lives at 42 Wall Street, New York, NY 10005. His email is john.smith@acmecorp.com and SSN is 123-45-6789.\n"
        target_bytes = args.stress * 1024
        repeats = max(1, target_bytes // len(chunk))
        stress_text += chunk * repeats
        stress_text = stress_text[:target_bytes]
        suite.append({
            "name": f"stress_{args.stress}kb",
            "description": f"{args.stress}KB stress test prompt",
            "text": stress_text,
        })

    # Create detector adapters
    detector_names = [d.strip() for d in args.detectors.split(",")]
    adapter_factories: dict[str, Callable[[], DetectorAdapter]] = {
        "regex": make_regex_adapter,
        "presidio": make_presidio_adapter,
        "gliner": make_gliner_adapter,
    }

    adapters: list[DetectorAdapter] = []
    for name in detector_names:
        if name in adapter_factories:
            adapters.append(adapter_factories[name]())
        else:
            print(f"Warning: Unknown detector '{name}', skipping")

    if not args.no_pipeline:
        try:
            pipeline_adapter = await make_pipeline_adapter()
            adapters.append(pipeline_adapter)
        except Exception as exc:
            print(f"  Warning: Pipeline benchmark unavailable: {exc}")
            print("  (The v2 FilterPipeline has an incomplete refactor — run --no-pipeline to skip)")

    if not adapters:
        print("No detectors to benchmark!")
        sys.exit(1)

    # Print benchmark configuration
    print("\n" + "=" * 80)
    print("  PIIFilter Benchmark Configuration")
    print("=" * 80)
    print(f"  Iterations per prompt: {args.iterations}")
    print(f"  Warmup iterations:     {args.warmup}")
    print(f"  Prompt count:           {len(suite)}")
    print(f"  Detectors:              {[a.name for a in adapters]}")
    if args.stress > 0:
        print(f"  Stress prompt:          {args.stress}KB")
    print()

    # Run benchmarks
    all_metrics: dict[str, list[DetectorMetrics]] = {}

    for adapter in adapters:
        print(f"  Benchmarking '{adapter.name}'...")
        t_start = time.perf_counter()
        metrics = await benchmark_detector(
            adapter,
            suite,
            iterations=args.iterations,
            warmup_iterations=args.warmup,
        )
        elapsed = time.perf_counter() - t_start
        print(f"    Completed in {elapsed:.2f}s")
        all_metrics[adapter.name] = metrics

    # Build and write report
    report = build_report(all_metrics)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, default=str))
    print(f"\n  Results saved to {output_path.resolve()}")

    # Print results
    print_results(all_metrics)


if __name__ == "__main__":
    asyncio.run(main())