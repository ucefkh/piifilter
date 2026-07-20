#!/usr/bin/env python3
"""Held-out adversarial benchmark — run pipeline on ALL 3 new datasets.

Measures overall recall + per-set breakdown to evaluate generalization
to held-out adversarial examples from independent generators.

Usage:
    source .venv/bin/activate
    python benchmarks/benchmark_holdout.py

Output:
    benchmarks/heldout-results.json
    /tmp/adversarial_report.txt
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent

sys.path.insert(0, str(PROJECT_ROOT / "core" / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "plugins" / "detector-regex" / "src"))

from piifilter_detector_regex.patterns import PATTERN_DEFS
from piifilter.shared.models import EntityType
from piifilter.shared.deobfuscator import Deobfuscator

# ── Helpers ──────────────────────────────────────────────────────────────────

_LEGACY_MAP: dict[str, str] = {"SOCIAL_SECURITY": "ssn"}
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


def luhn_valid(digits: str) -> bool:
    nums = [int(d) for d in digits if d.isdigit()]
    if len(nums) < 13:
        return False
    for i in range(len(nums) - 2, -1, -2):
        nums[i] *= 2
        if nums[i] > 9:
            nums[i] -= 9
    return sum(nums) % 10 == 0


def detect_full_pipeline(text: str, patterns: list[tuple[EntityType, re.Pattern[str], float]]) -> list[dict[str, Any]]:
    deob = Deobfuscator()
    text, _log, _ = deob(text)
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


def detect_raw_regex(text: str, patterns: list[tuple[EntityType, re.Pattern[str], float]]) -> list[dict[str, Any]]:
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


def load_dataset(dataset_path: str) -> list[dict[str, Any]]:
    data = json.loads(Path(dataset_path).read_text())
    examples = data.get("examples", data if isinstance(data, list) else [])
    # Tag each example with which dataset version it came from
    version = data.get("version", "unknown")
    for ex in examples:
        ex["_dataset_version"] = version
    return examples


def run_benchmark_on_dataset(
    dataset_path: str,
    dataset_label: str,
    patterns: list[tuple[EntityType, re.Pattern[str], float]],
) -> dict[str, Any]:
    """Run full pipeline + raw regex on a single dataset."""
    all_examples = load_dataset(str(dataset_path))

    if not all_examples:
        return {"label": dataset_label, "total": 0, "full_pipeline": 0, "raw_regex": 0, "entries": []}

    results = []
    for ex in all_examples:
        text = ex.get("text", "")
        if not text:
            continue
        full_detections = detect_full_pipeline(text, patterns)
        full_detected = len(full_detections) > 0
        raw_detections = detect_raw_regex(text, patterns)
        raw_detected = len(raw_detections) > 0

        results.append({
            "text": repr(text)[1:-1] if any(ord(c) > 127 for c in text) else text,
            "entity_type": ex.get("type", "UNKNOWN"),
            "strategy": ex.get("strategy", ""),
            "full_pipeline_detected": full_detected,
            "full_detections": [{"type": d["type"], "value": d["value"]} for d in full_detections],
            "raw_regex_detected": raw_detected,
            "raw_detections": [{"type": d["type"], "value": d["value"]} for d in raw_detections],
        })

    total = len(results)
    full = sum(1 for r in results if r["full_pipeline_detected"])
    raw = sum(1 for r in results if r["raw_regex_detected"])

    return {
        "label": dataset_label,
        "total": total,
        "full_pipeline": full,
        "full_pipeline_rate": round(full / total * 100, 1) if total else 0.0,
        "raw_regex": raw,
        "raw_regex_rate": round(raw / total * 100, 1) if total else 0.0,
        "improvement": round((full - raw) / total * 100, 1) if total else 0.0,
        "entries": results,
    }


def compute_generalization_gap(train_result: dict, holdout_results: list[dict]) -> float:
    """How much performance drops from train to held-out (gap = train_rate - avg_holdout_rate)."""
    train_rate = train_result.get("full_pipeline_rate", 0)
    holdout_rates = [r.get("full_pipeline_rate", 0) for r in holdout_results if r["total"] > 0]
    avg_holdout = sum(holdout_rates) / len(holdout_rates) if holdout_rates else 0
    return round(train_rate - avg_holdout, 1)


def main() -> None:
    DATA_DIR = Path(__file__).resolve().parent / "data"

    # Load existing training benchmark result for comparison
    existing_results_path = PROJECT_ROOT / "benchmarks" / "adversarial-results.json"

    print("╔═══ Held-Out Adversarial Benchmark ═══╗")
    print("║  Testing 3 new independent datasets   ║")
    print("╚════════════════════════════════════════╝\n")

    patterns = compile_patterns()

    # Load existing results for train comparison
    train_full_rate = 0.0
    train_raw_rate = 0.0
    if existing_results_path.exists():
        try:
            existing = json.loads(existing_results_path.read_text())
            s = existing.get("summary", {}).get("overall", {})
            train_full_rate = s.get("full_pipeline_rate", 0)
            train_raw_rate = s.get("raw_regex_rate", 0)
            print(f"  Training benchmark overall: {train_full_rate}% full pipeline, {train_raw_rate}% raw regex")
            train_label = "v1 benchmark (original)"
        except Exception:
            train_full_rate = 0.0
            train_label = "v1 (unavailable)"
    else:
        print("  No existing training benchmark results found.")
        train_label = "v1 (N/A)"

    # Also check v3 results
    v3_results_path = PROJECT_ROOT / "benchmarks" / "adversarial-v3-results.json"
    if v3_results_path.exists():
        try:
            v3 = json.loads(v3_results_path.read_text())
            s3 = v3.get("summary", {}).get("overall", {})
            v3_full = s3.get("full_pipeline_rate", 0)
            v3_raw = s3.get("raw_regex_rate", 0)
            print(f"  v3 benchmark overall:           {v3_full}% full pipeline, {v3_raw}% raw regex")
        except Exception:
            pass

    print()

    # Run on all 3 new datasets
    datasets = [
        (DATA_DIR / "adversarial_v4.json", "v4 (DeepSeek, seed_A, 10 strategies)"),
        (DATA_DIR / "adversarial_v5.json", "v5 (DeepSeek, seed_B, 10 strategies)"),
        (DATA_DIR / "adversarial_v6.json", "v6 (3rd generator, seed_C, 10 strategies)"),
    ]

    all_results = []
    for path, label in datasets:
        if not path.exists():
            print(f"  ⚠ Dataset not found: {path}")
            all_results.append({"label": label, "total": 0, "full_pipeline": 0, "raw_regex": 0,
                                "full_pipeline_rate": 0.0, "raw_regex_rate": 0.0, "entries": []})
            continue

        print(f"  Running on {label} ...")
        result = run_benchmark_on_dataset(str(path), label, patterns)
        all_results.append(result)
        print(f"    Total: {result['total']}, Full: {result['full_pipeline']} ({result['full_pipeline_rate']}%), "
              f"Raw: {result['raw_regex']} ({result['raw_regex_rate']}%), "
              f"Gain: +{result['improvement']}%")
        print()

    # ── Overall held-out summary ──
    combined_total = sum(r["total"] for r in all_results)
    combined_full = sum(r["full_pipeline"] for r in all_results)
    combined_raw = sum(r["raw_regex"] for r in all_results)
    combined_full_rate = round(combined_full / combined_total * 100, 1) if combined_total else 0.0
    combined_raw_rate = round(combined_raw / combined_total * 100, 1) if combined_total else 0.0
    combined_improvement = round((combined_full - combined_raw) / combined_total * 100, 1) if combined_total else 0.0

    generalization_gap = compute_generalization_gap(
        {"full_pipeline_rate": train_full_rate}, all_results
    )

    # ── Build results dict ──
    output = {
        "title": "Held-Out Adversarial Benchmark Report",
        "timestamp": __import__("datetime").datetime.now().isoformat(),
        "train_benchmark": {
            "label": train_label,
            "full_pipeline_rate": train_full_rate,
            "raw_regex_rate": train_raw_rate,
        },
        "holdout_datasets": all_results,
        "combined_held_out": {
            "total_examples": combined_total,
            "full_pipeline_detected": combined_full,
            "full_pipeline_rate": combined_full_rate,
            "raw_regex_detected": combined_raw,
            "raw_regex_rate": combined_raw_rate,
            "deobfuscation_improvement": combined_improvement,
        },
        "generalization_gap": generalization_gap,
    }

    # Save results
    output_path = PROJECT_ROOT / "benchmarks" / "heldout-results.json"
    output_path.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n")
    print(f"  Results saved to {output_path}\n")

    # ── Generate compact report ──
    report_lines = []
    report_lines.append("=" * 80)
    report_lines.append("  HELD-OUT ADVERSARIAL BENCHMARK — Comparison Report")
    report_lines.append("=" * 80)
    report_lines.append("")
    report_lines.append(f"  Training baseline:           {train_full_rate}%  (full pipeline)")
    report_lines.append(f"  Training raw regex baseline: {train_raw_rate}%")
    report_lines.append("")
    report_lines.append(f"  {'Dataset':60s} {'Total':>6s} {'Full':>8s} {'Raw':>6s} {'Gain':>6s}")
    report_lines.append(f"  {'─'*60} {'─'*6} {'─'*8} {'─'*6} {'─'*6}")

    # Training baseline row
    report_lines.append(
        f"  {'Training (v1 benchmark)':60s} {'—':>6s} {train_full_rate:>7.1f}% {train_raw_rate:>5.1f}% {'—':>6s}"
    )

    for r in all_results:
        if r["total"] > 0:
            gain = f"+{r['improvement']:.1f}%"
            report_lines.append(
                f"  {r['label']:60s} {r['total']:6d} {r['full_pipeline_rate']:>7.1f}% "
                f"{r['raw_regex_rate']:>5.1f}% {gain:>6s}"
            )

    report_lines.append(f"  {'─'*60} {'─'*6} {'─'*8} {'─'*6} {'─'*6}")
    report_lines.append(
        f"  {'COMBINED HELD-OUT':60s} {combined_total:6d} {combined_full_rate:>7.1f}% "
        f"{combined_raw_rate:>5.1f}% +{combined_improvement:.1f}%"
    )
    report_lines.append("")
    report_lines.append(f"  Generalization gap (train → held-out): {generalization_gap:+.1f}%")
    if generalization_gap > 0:
        report_lines.append(f"  ⚠ Performance drops by {generalization_gap}% on held-out data — adversarial gap exists.")
    else:
        report_lines.append(f"  ✓ Held-out performance meets or exceeds training — good generalization.")
    report_lines.append("")

    # Per-set breakdown
    report_lines.append("  ── Per-Set Entity-Type Coverage ──")
    report_lines.append("")
    for r in all_results:
        if r["total"] == 0:
            continue
        # Build type breakdown
        type_stats: dict[str, dict[str, int]] = {}
        for entry in r["entries"]:
            etype = entry.get("entity_type", "UNKNOWN")
            if etype not in type_stats:
                type_stats[etype] = {"total": 0, "detected": 0}
            type_stats[etype]["total"] += 1
            if entry["full_pipeline_detected"]:
                type_stats[etype]["detected"] += 1

        report_lines.append(f"  Set: {r['label']}")
        report_lines.append(f"    Overall: {r['full_pipeline']}/{r['total']} ({r['full_pipeline_rate']}%)")
        for etype in sorted(type_stats.keys()):
            ts = type_stats[etype]
            rate = round(ts["detected"] / ts["total"] * 100, 1)
            bar = "█" * int(rate / 10) + "░" * (10 - int(rate / 10))
            report_lines.append(f"    {etype:25s} {ts['detected']:3d}/{ts['total']:<3d} {rate:>5.1f}% {bar}")
        report_lines.append("")

    report_lines.append("=" * 80)

    report_text = "\n".join(report_lines)

    # Write report
    report_path = Path("/tmp/adversarial_report.txt")
    report_path.write_text(report_text)
    print(report_text)
    print(f"\n  Report written to {report_path}")


if __name__ == "__main__":
    main()