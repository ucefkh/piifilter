#!/usr/bin/env python3
"""Performance benchmark for PIIFilter pipeline.

Measures the full pipeline (detect → deobfuscate → patterns → generalize)
at varying document sizes and reports per-stage timing.

Usage:
    uv run python benchmarks/perf_benchmark.py
"""

from __future__ import annotations

import asyncio
import random
import re
import string
import sys
import time
from pathlib import Path
from statistics import median
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent

sys.path.insert(0, str(PROJECT_ROOT / "core" / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "plugins" / "detector-regex" / "src"))

from piifilter.shared.deobfuscator import Deobfuscator
from piifilter.shared.models import EntityType
from piifilter_detector_regex.patterns import PATTERN_DEFS


# ── Pattern compilation (mirrors benchmark_adversarial.py) ────────────────

_LEGACY_MAP: dict[str, str] = {"SOCIAL_SECURITY": "ssn"}
_FALLBACK_MAP: dict[str, str] = {
    "jwt": "token",
    "domain": "url",
    "database_url": "url",
    "private_url": "url",
    "file_path": "url",
    "ssh_key": "api_key",
    "iban": "bank_account",
    "date": "unknown",
    "gps": "unknown",
}
_DIRECT_MAP = {
    "PERSON", "EMAIL", "PHONE", "ADDRESS", "CITY", "COUNTRY",
    "COMPANY", "BANK_ACCOUNT", "IBAN", "CREDIT_CARD", "PASSPORT",
    "SOCIAL_SECURITY", "JWT", "API_KEY", "SSH_KEY", "DATABASE_URL",
    "PRIVATE_URL", "PROJECT_NAME", "CUSTOMER_NAME", "EMPLOYEE_NAME",
    "GPS", "DOMAIN", "IP_ADDRESS", "FILE_PATH",
}


def _resolve_entity_type(name: str) -> EntityType:
    if name in _DIRECT_MAP:
        return EntityType(name)
    lookup = _LEGACY_MAP.get(name, name.lower())
    try:
        return EntityType(lookup)
    except ValueError:
        return EntityType("PERSON")


def compile_patterns() -> list[tuple[EntityType, re.Pattern[str], float]]:
    compiled: list[tuple[EntityType, re.Pattern[str], float]] = []
    for type_name, raw_pattern, score in PATTERN_DEFS:
        entity_type = _resolve_entity_type(type_name)
        pattern = re.compile(raw_pattern, re.UNICODE)
        compiled.append((entity_type, pattern, score))
    return compiled


# ── Luhn check ─────────────────────────────────────────────────────────────

def luhn_valid(digits: str) -> bool:
    nums = [int(d) for d in digits if d.isdigit()]
    if len(nums) < 13:
        return False
    for i in range(len(nums) - 2, -1, -2):
        nums[i] *= 2
        if nums[i] > 9:
            nums[i] -= 9
    return sum(nums) % 10 == 0


# ── PII generators ────────────────────────────────────────────────────────────

PII_TEMPLATES: list[tuple[str, str]] = [
    ("EMAIL", "john.doe{idx}@example.com"),
    ("EMAIL", "alice.smith{idx}@acme.org"),
    ("SOCIAL_SECURITY", "{area:03d}-{group:02d}-{serial:04d}"),
    ("PHONE", "+1-555-{area:03d}-{ext:04d}"),
    ("IP_ADDRESS", "{a}.{b}.{c}.{d}"),
    ("CREDIT_CARD", "{cc:04d} {cc2:04d} {cc3:04d} {cc4:04d}"),
    ("API_KEY", "sk-proj-{key}{key2}{key3}{key4}"),
    ("URL", "https://{host}.example.com/path/{resource}"),
]


def _cc_luhn_digits() -> str:
    prefix = "4"
    rest = [random.randint(0, 9) for _ in range(14)]
    nums = [int(prefix)] + rest
    total = 0
    for i in range(len(nums) - 1, -1, -1):
        d = nums[i]
        if (len(nums) - i) % 2 == 0:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    check = (10 - (total % 10)) % 10
    rest.append(check)
    return "".join(str(n) for n in ([int(prefix)] + rest))


def make_pii(idx: int) -> str:
    template_name, template = random.choice(PII_TEMPLATES)
    rng = random.Random(idx * 7919 + 65537)
    a, b, c, d = rng.randint(1, 254), rng.randint(1, 254), rng.randint(1, 254), rng.randint(1, 254)
    cc = _cc_luhn_digits()
    return template.format(
        idx=idx,
        area=(idx * 7 + 100) % 1000,
        group=(idx * 3 + 10) % 100,
        serial=(idx * 13 + 1000) % 10000,
        ext=(idx * 17 + 5000) % 10000,
        a=a, b=b, c=c, d=d,
        cc=int(cc[:4]), cc2=int(cc[4:8]), cc3=int(cc[8:12]), cc4=int(cc[12:]),
        key=string.ascii_lowercase[(idx // 3) % 26],
        key2=string.ascii_lowercase[(idx * 7) % 26],
        key3=string.ascii_lowercase[(idx + 11) % 26],
        key4=string.ascii_lowercase[(idx * 5 + 3) % 26],
        host=string.ascii_lowercase[(idx % 20) + 1],
        resource=string.ascii_lowercase[(idx * 3) % 26],
    )


OBFUSCATION_TEMPLATES = [
    lambda s: s.replace("o", "\u043E").replace("a", "\u0430").replace("e", "\u0435"),
    lambda s: "\u200B".join(list(s)),
    lambda s: s.replace("@", "[at]").replace(".", "[dot]") if "@" in s else s,
    lambda s: s.replace("1", "one").replace("2", "two").replace("3", "three").replace("4", "four").replace("5", "five"),
    lambda s: "".join(f"&#{ord(c)};" if c in "@.-_" else c for c in s),
    lambda s: s.replace("@", "%40").replace(".", "%2E") if "@" in s else s,
    lambda s: "+".join(f'"{c}"' for c in s) if len(s) > 3 and "@" in s else s,
    lambda s: s.replace("-", "\u2013") if "-" in s else s,
    lambda s: "".join(chr(ord(c) + 0xFEE0) if 0x21 <= ord(c) <= 0x7E else c for c in s),
    lambda s: " | ".join(list(s)) if len(s) < 30 else s,
]


def generate_document(target_size: int) -> str:
    parts: list[str] = []
    current_size = 0
    pii_count = 0

    lorem = (
        "Lorem ipsum dolor sit amet, consectetur adipiscing elit. "
        "Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. "
        "Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris "
        "nisi ut aliquip ex ea commodo consequat. Duis aute irure dolor in "
        "reprehenderit in voluptate velit esse cillum dolore eu fugiat nulla pariatur. "
    )

    while current_size < target_size:
        filler = f"{lorem[:random.randint(50, 300)]}\n"
        parts.append(filler)
        current_size += len(filler)

        if random.random() < 0.5:
            pii_count += 1
            pii = make_pii(pii_count)
            if random.random() < 0.3:
                obfuscator = random.choice(OBFUSCATION_TEMPLATES)
                try:
                    pii = obfuscator(pii)
                except (ValueError, IndexError):
                    pass
            pii_line = f"  contact: {pii}\n"
            parts.append(pii_line)
            current_size += len(pii_line)

    text = "".join(parts)
    return text[:target_size]


# ── Detection runner ──────────────────────────────────────────────────────────

def detect_full_pipeline(text: str, patterns: list[tuple[EntityType, re.Pattern[str], float]]) -> list[dict[str, Any]]:
    deob = Deobfuscator()
    text, _log = deob(text)

    entities: list[dict[str, Any]] = []
    seen_intervals: list[tuple[int, int]] = []

    for entity_type, pattern, score in patterns:
        for match in pattern.finditer(text):
            start, end = match.start(), match.end()
            if start == end:
                continue
            if any(s <= start and end <= e for s, e in seen_intervals):
                continue
            if entity_type == EntityType.CREDIT_CARD:
                digits = "".join(c for c in match.group() if c.isdigit())
                if len(digits) >= 13 and not luhn_valid(digits):
                    continue
            entities.append({
                "type": entity_type.value,
                "value": match.group(),
                "start": start,
                "end": end,
                "score": score,
            })
            seen_intervals.append((start, end))

    entities.sort(key=lambda e: e["start"])
    return entities


# ── Benchmark runner ──────────────────────────────────────────────────────────


def _per_transform_timing(text: str) -> dict[str, float]:
    deob = Deobfuscator()
    timings: dict[str, float] = {}

    methods = [
        ("NFKC", lambda t: deob._nfkc_normalize(t, [])),
        ("strip_html_comments", lambda t: Deobfuscator._strip_html_comments(t, [])),
        ("fix_obfuscated_email_046", lambda t: Deobfuscator._fix_obfuscated_email_entities(t, [])),
        ("unwrap_at_dot", lambda t: Deobfuscator._unwrap_at_dot(t, [])),
        ("unwrap_html_entities", lambda t: Deobfuscator._unwrap_html_entities(t, [])),
        ("unwrap_zero_width", lambda t: Deobfuscator._unwrap_zero_width(t, [])),
        ("normalize_dashes", lambda t: Deobfuscator._normalize_dashes(t, [])),
        ("remove_soft_hyphen", lambda t: Deobfuscator._remove_soft_hyphen(t, [])),
        ("flatten_fullwidth", lambda t: deob._flatten_fullwidth(t, [])),
        ("unwrap_unicode_escapes", lambda t: Deobfuscator._unwrap_unicode_escapes(t, [])),
        ("decode_url_percent", lambda t: Deobfuscator._decode_url_percent(t, [])),
        ("unwrap_spoken_numbers", lambda t: Deobfuscator._unwrap_spoken_numbers(t, [])),
        ("map_spoken_separators", lambda t: Deobfuscator._map_spoken_separators(t, [])),
        ("normalize_ip_octet_spaces", lambda t: Deobfuscator._normalize_ip_octet_spaces(t, [])),
        ("normalize_ip_octet_dots", lambda t: Deobfuscator._normalize_ip_octet_dots(t, [])),
        ("normalize_ssn_segments", lambda t: Deobfuscator._normalize_ssn_segments(t, [])),
        ("normalize_cc_segments", lambda t: Deobfuscator._normalize_cc_segments(t, [])),
        ("cleanup_dash_spaces", lambda t: Deobfuscator._cleanup_dash_spaces(t, [])),
        ("collapse_ip_spaces", lambda t: Deobfuscator._collapse_ip_spaces(t, [])),
        ("collapse_digit_spaces", lambda t: Deobfuscator._collapse_digit_spaces(t, [])),
        ("decode_hex", lambda t: Deobfuscator._decode_hex(t, [])),
        ("decode_base64", lambda t: Deobfuscator._decode_base64(t, [])),
        ("extract_area_serial", lambda t: Deobfuscator._extract_area_serial(t, [])),
        ("reconstruct_split_tokens", lambda t: Deobfuscator._reconstruct_split_tokens(t, [])),
    ]

    for name, method in methods:
        t0 = time.perf_counter_ns()
        _ = method(text)
        dt = (time.perf_counter_ns() - t0) / 1_000_000
        timings[name] = dt
        text = method(text)

    return timings


def run_benchmark() -> None:
    sizes = [1024, 10 * 1024, 100 * 1024]
    num_iterations = 20

    print("=" * 90)
    print("  PIIFilter Performance Benchmark — Full Pipeline")
    print("=" * 90)
    print()

    patterns = compile_patterns()
    results: list[dict[str, Any]] = []

    for size in sizes:
        size_label = f"{size // 1024}KB" if size >= 1024 else f"{size}B"
        print(f"  Generating {num_iterations} documents of {size_label}...")

        docs = []
        for i in range(num_iterations):
            doc = generate_document(size)
            docs.append(doc)

        print(f"  Running pipeline ({num_iterations}x iterations)...")

        full_latencies: list[float] = []
        deob_latencies: list[float] = []
        pattern_latencies: list[float] = []
        per_transform_timings_list: list[dict[str, float]] = []

        for i, doc in enumerate(docs):
            # Stage 1: Deobfuscation
            deob = Deobfuscator()
            t0 = time.perf_counter_ns()
            cleaned, log = deob(doc)
            t1 = time.perf_counter_ns()
            deob_ms = (t1 - t0) / 1_000_000
            deob_latencies.append(deob_ms)

            # Stage 2: Pattern matching
            t0 = time.perf_counter_ns()
            entities = detect_full_pipeline(doc, patterns)
            t1 = time.perf_counter_ns()
            pattern_ms = (t1 - t0) / 1_000_000
            pattern_latencies.append(pattern_ms)

            full_ms = deob_ms + pattern_ms
            full_latencies.append(full_ms)

            if i == 0:
                per_transform_timings_list.append(_per_transform_timing(doc))

        def _p50(vals: list[float]) -> float:
            return round(median(vals), 2)

        def _p95(vals: list[float]) -> float:
            if len(vals) < 2:
                return round(vals[0], 2) if vals else 0.0
            sorted_vals = sorted(vals)
            idx = int(len(sorted_vals) * 0.95)
            return round(sorted_vals[min(idx, len(sorted_vals) - 1)], 2)

        def _p99(vals: list[float]) -> float:
            if len(vals) < 2:
                return round(vals[0], 2) if vals else 0.0
            sorted_vals = sorted(vals)
            idx = int(len(sorted_vals) * 0.99)
            return round(sorted_vals[min(idx, len(sorted_vals) - 1)], 2)

        total_ms = sum(full_latencies)
        throughput = round(num_iterations / (total_ms / 1000), 1) if total_ms > 0 else 0.0

        if per_transform_timings_list:
            pt = per_transform_timings_list[0]
            bottleneck = max(pt, key=pt.get) if pt else "N/A"
            bottleneck_time = pt.get(bottleneck, 0)
            total_deob_ms = sum(pt.values())
            bottleneck_pct = round(bottleneck_time / total_deob_ms * 100, 1) if total_deob_ms > 0 else 0.0
            bottleneck_str = f"{bottleneck} ({bottleneck_time:.2f}ms, {bottleneck_pct}%)"
        else:
            bottleneck_str = "N/A"

        results.append({
            "doc_size": size_label,
            "p50_ms": _p50(full_latencies),
            "p95_ms": _p95(full_latencies),
            "p99_ms": _p99(full_latencies),
            "throughput": f"{throughput} docs/s",
            "deob_mean_ms": round(sum(deob_latencies) / len(deob_latencies), 2),
            "pattern_mean_ms": round(sum(pattern_latencies) / len(pattern_latencies), 2),
            "full_mean_ms": round(sum(full_latencies) / len(full_latencies), 2),
            "per_kb_ms": round((sum(full_latencies) / len(full_latencies)) / (size / 1024), 2) if size > 0 else 0,
            "bottleneck": bottleneck_str,
            "deob_pct": round(sum(deob_latencies) / sum(full_latencies) * 100, 1) if sum(full_latencies) > 0 else 0,
            "total_deob_ms": total_deob_ms,
        })

    # ── Output table ──────────────────────────────────────────────────────

    print()
    print("  ── Per-Document-Size Performance ──")
    print()
    header = f"  {'Doc Size':>10s} {'p50(ms)':>10s} {'p95(ms)':>10s} {'p99(ms)':>10s} {'Throughput':>15s} {'ms/KB':>8s} {'Deob%':>7s} {'Bottleneck':>50s}"
    sep = "  " + "─" * 10 + " " + "─" * 10 + " " + "─" * 10 + " " + "─" * 10 + " " + "─" * 15 + " " + "─" * 8 + " " + "─" * 7 + " " + "─" * 50
    print(header)
    print(sep)
    for r in results:
        print(f"  {r['doc_size']:>10s} {r['p50_ms']:>9.2f}ms {r['p95_ms']:>9.2f}ms {r['p99_ms']:>9.2f}ms {r['throughput']:>15s} {r['per_kb_ms']:>7.2f}ms {r['deob_pct']:>6.1f}%  {r['bottleneck'][:50]:50s}")

    print()
    # Average ms/KB across all sizes
    avg_ms_per_kb = sum(r["per_kb_ms"] for r in results) / len(results)
    target_ms_per_kb = 50.0
    status = "✓ PASS" if avg_ms_per_kb <= target_ms_per_kb else "✗ FAIL"
    print(f"  Target: <{target_ms_per_kb}ms/KB  →  Actual: {avg_ms_per_kb:.2f}ms/KB (avg across sizes)  {status}")
    print(f"  Note: ms/KB decreases with size due to fixed overhead amortization.")

    # ── Per-transform deobfuscator timing ─────────────────────────────────
    print()
    print("  ── Per-Transform Deobfuscator Timing (on 1KB document) ──")
    print()
    if per_transform_timings_list:
        pt = per_transform_timings_list[0]
        sorted_pt = sorted(pt.items(), key=lambda x: -x[1])
        total = sum(pt.values())
        print(f"  {'Transform':>30s} {'Time(ms)':>12s} {'% of Total':>12s}")
        print(f"  {'─'*30} {'─'*12} {'─'*12}")
        for name, t_ms in sorted_pt:
            pct = t_ms / total * 100 if total > 0 else 0
            print(f"  {name:>30s} {t_ms:>10.4f}ms {pct:>10.1f}%")
        print(f"  {'─'*30} {'─'*12} {'─'*12}")
        print(f"  {'TOTAL':>30s} {total:>10.4f}ms {100.0:>10.1f}%")

        # Check if deobfuscator is >50% of total pipeline
        high_deob = [r for r in results if r["deob_pct"] > 50]
        if high_deob:
            worst = max(high_deob, key=lambda r: r["deob_pct"])
            print()
            print(f"  ⚠  Deobfuscator is {worst['deob_pct']:.1f}% of total at {worst['doc_size']}!")
            print(f"     Slowest transform: {worst['bottleneck']}")

    print()
    print("=" * 90)


def main() -> None:
    run_benchmark()


if __name__ == "__main__":
    main()