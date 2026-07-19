#!/usr/bin/env python3
"""
Performance benchmark for PIIFilter v2 — measures p50/p95/p99 latency
across document sizes (1KB, 10KB, 100KB) through the FULL pipeline:
  deobfuscation → regex detection → structural validators → context fallback

Outputs a clean ASCII table with columns:
  doc_size | p50(ms) | p95(ms) | p99(ms) | throughput(d/s) | ms/KB | deobfuscator%

Flags FAIL if any size exceeds 50ms/KB target.
"""

from __future__ import annotations

import asyncio
import math
import random
import statistics
import time
import sys
import os

# ── Ensure project modules are importable ──────────────────────────────────
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "plugins", "detector-regex", "src"))

from piifilter.shared.deobfuscator import Deobfuscator
from piifilter_detector_regex.detector import RegexDetector

# ══════════════════════════════════════════════════════════════════════════════
#  Realistic PII generators
# ══════════════════════════════════════════════════════════════════════════════

NAMES = [
    "Alice Johnson", "Bob Smith", "Carol Williams", "David Brown",
    "Eve Davis", "Frank Miller", "Grace Wilson", "Hank Moore",
    "Ivy Taylor", "Jack Anderson", "Karen Thomas", "Leo Jackson",
    "Maria White", "Nathan Harris", "Olivia Martin", "Paul Garcia",
    "Quinn Martinez", "Rachel Robinson", "Sam Clark", "Tina Rodriguez",
    "Uma Lewis", "Victor Lee", "Wendy Walker", "Xavier Hall",
    "Yvonne Allen", "Zachary Young", "Aisha King", "Ben Wright",
    "Chloe Scott", "Diego Green",
]

DOMAINS = ["gmail.com", "yahoo.com", "outlook.com", "hotmail.com",
           "icloud.com", "protonmail.com", "company.com", "acme.org",
           "example.net", "test.io"]

STREETS = ["Oak St", "Elm Ave", "Main St", "Broadway", "Park Ln",
           "Market St", "High St", "Cedar Rd", "Pine Dr", "Lake View Blvd"]

CITIES = ["New York", "Los Angeles", "Chicago", "Houston", "Phoenix",
          "Philadelphia", "San Antonio", "San Diego", "Dallas", "Austin"]

STATES = ["NY", "CA", "IL", "TX", "AZ", "PA", "FL", "OH", "GA", "WA"]

ZIPS = [f"{random.randint(10000, 99999)}" for _ in range(50)]

CCS = [
    "4111-1111-1111-1111", "5500-0000-0000-0004", "3400-0000-0000-009",
    "3000-0000-0000-04", "6011-0000-0000-0004", "3714-496353-98431",
    "4532-0112-3456-7890", "5105-1051-0510-5100",
]

SSNS = [
    "078-05-1120", "123-45-6789", "987-65-4321", "111-22-3333",
    "444-55-6666", "777-88-9999", "001-01-0001", "999-98-7654",
]

IPS = [
    "192.168.1.1", "10.0.0.1", "172.16.0.1", "8.8.8.8",
    "203.0.113.42", "198.51.100.7", "192.0.2.55", "169.254.12.34",
]

PHONES = [
    "+1-555-123-4567", "+1-800-555-0199", "+44-20-7946-0958",
    "+1-212-555-0198", "+1-310-555-0197", "+49-30-1234-5678",
    "+81-3-5555-6789", "+61-2-5555-6789",
]

LIPSUM = (
    "Lorem ipsum dolor sit amet, consectetur adipiscing elit. "
    "Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. "
    "Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris "
    "nisi ut aliquip ex ea commodo consequat. Duis aute irure dolor in "
    "reprehenderit in voluptate velit esse cillum dolore eu fugiat nulla "
    "pariatur. Excepteur sint occaecat cupidatat non proident, sunt in "
    "culpa qui officia deserunt mollit anim id est laborum. "
)

LOREM_SENTENCES = (
    "The quick brown fox jumps over the lazy dog near the bank. "
    "Please update your account information as soon as possible. "
    "Your session has expired, please log in again to continue. "
    "We detected unusual activity on your account. "
    "This is an automated message from our support team. "
    "Thank you for your patience while we resolve this issue. "
    "For security purposes, please verify your identity. "
    "Your request has been processed successfully. "
    "We are writing to confirm your recent transaction. "
    "Please do not share this code with anyone. "
    "Access to this resource is restricted. "
    "The server responded with an unexpected error. "
    "Configuration settings have been updated. "
    "Your profile changes have been saved. "
    "A new version of the software is available. "
    "Connection established to the remote host. "
    "Database query executed in 15 milliseconds. "
    "Cache invalidation triggered for key: session_token. "
    "Authentication failed: invalid credentials provided. "
    "Backup completed successfully at 3:00 AM UTC. "
)


def _rand_email() -> str:
    name = random.choice(NAMES).lower().replace(" ", ".")
    return f"{name}.{random.randint(10, 99)}@{random.choice(DOMAINS)}"


def _rand_phone() -> str:
    return random.choice(PHONES)


def _rand_ssn() -> str:
    return random.choice(SSNS)


def _rand_cc() -> str:
    return random.choice(CCS)


def _rand_ip() -> str:
    return random.choice(IPS)


def _rand_name() -> str:
    return random.choice(NAMES)


def _rand_address() -> str:
    num = random.randint(100, 9999)
    street = random.choice(STREETS)
    city = random.choice(CITIES)
    state = random.choice(STATES)
    zipcode = random.choice(ZIPS)
    return f"{num} {street}, {city}, {state} {zipcode}"


def _rand_text_snippet(length: int) -> str:
    """Generate random text of approximately *length* chars."""
    parts = []
    while sum(len(p) for p in parts) < length:
        parts.append(random.choice(LOREM_SENTENCES))
    s = " ".join(parts)
    return s[:length]


def generate_document(target_bytes: int) -> str:
    """Generate a realistic document with PII injected at ~5% density.

    Produces a mix of random text + PII instances (email, phone, SSN,
    CC, IP, name, address) so the full pipeline processes it realistically.
    Returns a string of approximately *target_bytes* chars.
    """
    # PII injectors: each returns (label, pii_string)
    pii_generators = [
        ("EMAIL", _rand_email),
        ("PHONE", _rand_phone),
        ("SSN", _rand_ssn),
        ("CC", _rand_cc),
        ("IP", _rand_ip),
        ("NAME", _rand_name),
        ("ADDRESS", _rand_address),
    ]

    segments: list[str] = []
    current_len = 0

    # PII density: inject every ~500 chars on average (~20 PII instances per 10KB)
    pii_interval = max(300, target_bytes // 20)

    while current_len < target_bytes:
        remaining = target_bytes - current_len

        # Should we inject PII?
        if remaining > 50 and random.random() < (pii_interval / max(remaining + pii_interval, 1)):
            _, pii_func = random.choice(pii_generators)
            pii = pii_func()
            if len(pii) <= remaining:
                # Wrap PII in natural context
                prefix = random.choice(["", " ", ". ", ", ", "; "])
                suffix = random.choice(["", ".", ",", " ", ".\n", "\n"])
                chunk = prefix + pii + suffix
                segments.append(chunk)
                current_len += len(chunk)
            else:
                # Fall through — add filler
                pass

        # Add random filler text
        filler_len = min(random.randint(40, 200), remaining - 10)
        if filler_len < 10:
            filler_len = remaining
        filler = _rand_text_snippet(filler_len)
        segments.append(filler)
        current_len += len(filler)

    return "".join(segments)


# ══════════════════════════════════════════════════════════════════════════════
#  Benchmark harness
# ══════════════════════════════════════════════════════════════════════════════

def percentile(data: list[float], p: float) -> float:
    """Compute the p-th percentile of *data* using linear interpolation."""
    if not data:
        return 0.0
    sorted_data = sorted(data)
    n = len(sorted_data)
    k = (p / 100.0) * (n - 1)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return sorted_data[int(k)]
    d0 = sorted_data[f] * (c - k)
    d1 = sorted_data[c] * (k - f)
    return d0 + d1


async def run_benchmark() -> None:
    # Document sizes to test
    DOC_SIZES = [1024, 10_240, 102_400]  # 1KB, 10KB, 100KB
    ITERATIONS = 20  # per size for statistical significance
    MS_PER_KB_TARGET = 50.0

    print("=" * 90)
    print("  PIIFilter v2 — Performance Benchmark")
    print(f"  Sizes: {', '.join(f'{s//1024}KB' if s < 50_000 else '100KB' for s in DOC_SIZES)}")
    print(f"  Iterations per size: {ITERATIONS}")
    print(f"  Target: ≤{MS_PER_KB_TARGET} ms/KB")
    print("=" * 90)

    # Pre-generate documents for reproducibility
    print("\n[Generating test documents...]")
    documents: dict[str, str] = {}
    rng_state = random.getstate()
    for size in DOC_SIZES:
        random.seed(42 + size)
        label = f"{size//1024}KB" if size < 50_000 else "100KB"
        documents[label] = generate_document(size)
        print(f"  {label}: {len(documents[label]):>6} chars generated")
    random.setstate(rng_state)

    # Initialize the pipeline components once
    print("\n[Initializing pipeline...]")
    deobfuscator = Deobfuscator()
    detector = RegexDetector()
    print("  Deobfuscator & RegexDetector ready.")

    # Per-transform timing for the deobfuscator — we need to instrument the __call__
    # to capture per-transform timings. We'll wrap the Deobfuscator.
    _orig_call = Deobfuscator.__call__

    transform_timings: dict[str, list[float]] = {}  # transform_name -> [timings]

    def instrumented_deobfuscate(text: str) -> tuple[str, list[dict]]:
        """Run deobfuscation with per-transform timing."""
        log: list[dict] = []
        t_all_start = time.perf_counter()
        # Manually step through each transform (same order as Deobfuscator.__call__)
        # so we can time each one independently.
        d = deobfuscator
        transforms = [
            ("NFKC", lambda t: d._nfkc_normalize(t, log)),
            ("html_comments", lambda t: d._strip_html_comments(t, log)),
            ("at_dot", lambda t: d._unwrap_at_dot(t, log)),
            ("obfuscated_email_046", lambda t: d._fix_obfuscated_email_entities(t, log)),
            ("xml_escape", lambda t: d._decode_xml_escape(t, log)),
            ("html_entities", lambda t: d._unwrap_html_entities(t, log)),
            ("zero_width", lambda t: d._unwrap_zero_width(t, log)),
            ("dashes", lambda t: d._normalize_dashes(t, log)),
            ("soft_hyphen", lambda t: d._remove_soft_hyphen(t, log)),
            ("fullwidth", lambda t: d._flatten_fullwidth(t, log)),
            ("unicode_escapes", lambda t: d._unwrap_unicode_escapes(t, log)),
            ("hex_escapes", lambda t: d._decode_hex_escapes(t, log)),
            ("url_percent", lambda t: d._decode_url_percent(t, log)),
            ("binary_strings", lambda t: d._decode_binary_strings(t, log)),
            ("unicode_fractions", lambda t: d._normalize_unicode_fractions(t, log)),
            ("spoken_numbers", lambda t: d._unwrap_spoken_numbers(t, log)),
            ("spoken_separators", lambda t: d._map_spoken_separators(t, log)),
            ("ip_octet_spaces", lambda t: d._normalize_ip_octet_spaces(t, log)),
            ("ip_octet_dots", lambda t: d._normalize_ip_octet_dots(t, log)),
            ("ssn_segments", lambda t: d._normalize_ssn_segments(t, log)),
            ("cc_segments", lambda t: d._normalize_cc_segments(t, log)),
            ("dash_spaces", lambda t: d._cleanup_dash_spaces(t, log)),
            ("ip_collapse", lambda t: d._collapse_ip_spaces(t, log)),
            ("digit_collapse", lambda t: d._collapse_digit_spaces(t, log)),
            ("hex_decode", lambda t: d._decode_hex(t, log)),
            ("base64_decode", lambda t: d._decode_base64(t, log)),
            ("area_serial", lambda t: d._extract_area_serial(t, log)),
            ("split_tokens", lambda t: d._reconstruct_split_tokens(t, log)),
            ("l33t_decode", lambda t: d._decode_l33t(t, log)),
            ("morse_decode", lambda t: d._decode_morse(t, log)),
            ("punct_stuffing", lambda t: d._remove_punctuation_stuffing(t, log)),
            ("pig_latin", lambda t: d._decode_pig_latin(t, log)),
        ]

        for name, func in transforms:
            t_start = time.perf_counter()
            text = func(text)
            elapsed = time.perf_counter() - t_start
            if name not in transform_timings:
                transform_timings[name] = []
            transform_timings[name].append(elapsed)

        t_all = time.perf_counter() - t_all_start
        return text, log

    # ── Run benchmarks ──────────────────────────────────────────────────

    results: dict[str, dict] = {}

    for label, doc in documents.items():
        print(f"\n{'─' * 90}")
        print(f"  Benchmarking {label} ({len(doc)} chars) ...")
        print(f"{'─' * 90}")

        total_times: list[float] = []     # total pipeline time in seconds
        detect_times: list[float] = []    # detection-only time
        deobf_times: list[float] = []     # deobfuscation time
        entity_counts: list[int] = []     # entities found per run

        for i in range(ITERATIONS):
            # Warm-up iteration (not counted)
            if i == 0:
                _text, _ = instrumented_deobfuscate(doc)
                await detector.detect(_text)
                # Reset transform timings for warmup
                transform_timings.clear()
                # Also run a simple detection warmup
                await detector.detect(doc)
                continue

            # ── Full pipeline: deobfuscate → detect ──────────────────
            t_total_start = time.perf_counter()

            # Deobfuscation
            t_deobf_start = time.perf_counter()
            cleaned, deobf_log = instrumented_deobfuscate(doc)
            t_deobf = time.perf_counter() - t_deobf_start

            # Detection
            t_detect_start = time.perf_counter()
            entities = await detector.detect(cleaned)
            t_detect = time.perf_counter() - t_detect_start

            t_total = time.perf_counter() - t_total_start

            total_times.append(t_total)
            deobf_times.append(t_deobf)
            detect_times.append(t_detect)
            entity_counts.append(len(entities))

        # ── Compute statistics ────────────────────────────────────────
        doc_size_kb = len(doc) / 1024

        p50_total = percentile(total_times, 50) * 1000  # ms
        p95_total = percentile(total_times, 95) * 1000
        p99_total = percentile(total_times, 99) * 1000
        mean_total = statistics.mean(total_times) * 1000

        ms_per_kb = mean_total / doc_size_kb
        throughput = 1.0 / statistics.mean(total_times) if statistics.mean(total_times) > 0 else float("inf")

        deobf_pct = (statistics.mean(deobf_times) / statistics.mean(total_times)) * 100 if total_times else 0

        avg_entities = statistics.mean(entity_counts)

        print(f"    Iterations: {ITERATIONS - 1} (1 warm-up)")
        print(f"    Avg entities found: {avg_entities:.1f}")
        print(f"    Total time:")
        print(f"      p50:  {p50_total:>8.2f} ms")
        print(f"      p95:  {p95_total:>8.2f} ms")
        print(f"      p99:  {p99_total:>8.2f} ms")
        print(f"      mean: {mean_total:>8.2f} ms")
        print(f"    Throughput: {throughput:.1f} docs/sec")
        print(f"    ms/KB:      {ms_per_kb:.2f}")
        print(f"    Deobf % of total: {deobf_pct:.1f}%")

        results[label] = {
            "doc_size": len(doc),
            "p50_ms": p50_total,
            "p95_ms": p95_total,
            "p99_ms": p99_total,
            "mean_ms": mean_total,
            "throughput": throughput,
            "ms_per_kb": ms_per_kb,
            "deobf_pct": deobf_pct,
            "deobf_times": deobf_times,
            "detect_times": detect_times,
            "entity_counts": entity_counts,
        }

    # ══════════════════════════════════════════════════════════════════
    #  Output: main summary table
    # ══════════════════════════════════════════════════════════════════

    print("\n" + "=" * 90)
    print("  RESULTS SUMMARY")
    print("=" * 90)

    header = f"{'Doc Size':<12} {'p50(ms)':<10} {'p95(ms)':<10} {'p99(ms)':<10} {'Throughput':<14} {'ms/KB':<10} {'Deobf%':<8} {'Status':<8}"
    sep = "-" * 90
    print(sep)
    print(header)
    print(sep)

    all_pass = True
    for label, r in sorted(results.items()):
        passed = r["ms_per_kb"] <= MS_PER_KB_TARGET
        status = "PASS" if passed else "FAIL"
        if not passed:
            all_pass = False
        print(
            f"{label:<12} {r['p50_ms']:<10.2f} {r['p95_ms']:<10.2f} {r['p99_ms']:<10.2f} "
            f"{r['throughput']:<14.1f} {r['ms_per_kb']:<10.2f} {r['deobf_pct']:<8.1f} {status:<8}"
        )
    print(sep)

    # ══════════════════════════════════════════════════════════════════
    #  Per-transform deobfuscator timing
    # ══════════════════════════════════════════════════════════════════

    print("\n" + "=" * 90)
    print("  DEOBFUSCATOR — Per-Transform Timing (mean μs across all runs)")
    print("=" * 90)

    # Aggregate transform timings by transform name
    trans_agg: dict[str, float] = {}
    for tname, timings in transform_timings.items():
        trans_agg[tname] = statistics.mean(timings) * 1_000_000  # μs

    # Sort by descending cost
    sorted_trans = sorted(trans_agg.items(), key=lambda x: -x[1])
    total_trans = sum(v for _, v in sorted_trans)

    hdr = f"{'Transform':<30} {'Mean (μs)':<12} {'% of Deobf':<12}"
    print(hdr)
    print("-" * 90)
    for tname, mean_us in sorted_trans:
        pct = (mean_us / total_trans) * 100
        print(f"{tname:<30} {mean_us:<12.2f} {pct:<12.1f}")
    print("-" * 90)
    print(f"{'TOTAL':<30} {total_trans:<12.2f} {'100.0%':<12}")

    # ══════════════════════════════════════════════════════════════════
    #  Bottleneck identification
    # ══════════════════════════════════════════════════════════════════

    print("\n" + "=" * 90)
    print("  BOTTLENECK ANALYSIS")
    print("=" * 90)

    if sorted_trans:
        top3 = sorted_trans[:3]
        top3_total = sum(v for _, v in top3)
        top3_pct = (top3_total / total_trans) * 100 if total_trans > 0 else 0
        print(f"  Top 3 transforms consume {top3_pct:.1f}% of deobfuscation time:")
        for i, (tname, mean_us) in enumerate(top3, 1):
            pct = (mean_us / total_trans) * 100
            print(f"    {i}. {tname:<28} {mean_us:>8.2f} μs  ({pct:.1f}%)")

        # Biggest single bottleneck
        bottleneck_name, bottleneck_us = sorted_trans[0]
        bneck_pct = (bottleneck_us / total_trans) * 100
        bneck_us_per_kb = bottleneck_us / (doc_size_kb if "doc_size_kb" in dir() else 100)
        print(f"\n  ⚡ Primary bottleneck: {bottleneck_name} ({bneck_pct:.1f}% of deobfuscation)")

    # 🌟 Flag if any size exceeds 50ms/KB
    print(f"\n  Target: ≤{MS_PER_KB_TARGET} ms/KB")
    if all_pass:
        print(f"  ✅ ALL SIZES PASS — no size exceeds {MS_PER_KB_TARGET} ms/KB")
    else:
        for label, r in sorted(results.items()):
            if r["ms_per_kb"] > MS_PER_KB_TARGET:
                print(f"  ❌ {label}: {r['ms_per_kb']:.2f} ms/KB exceeds {MS_PER_KB_TARGET} ms/KB target")
        print(f"  ❌ FAIL — at least one size exceeds the {MS_PER_KB_TARGET} ms/KB target")

    print("\n" + "=" * 90)

    # ── Detailed entity counts per size ────────────────────────────
    print("\n  ENTITY COUNTS (avg per run)")
    print("-" * 40)
    for label, r in sorted(results.items()):
        avg = statistics.mean(r["entity_counts"])
        mx = max(r["entity_counts"])
        mn = min(r["entity_counts"])
        print(f"  {label:<10}: avg={avg:>5.1f}  min={mn:>3}  max={mx:>3}")

    print()


if __name__ == "__main__":
    asyncio.run(run_benchmark())