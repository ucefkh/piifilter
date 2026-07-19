#!/usr/bin/env python3
"""Run the adversarial benchmark against the fresh v3 dataset.

Usage:
    uv run python benchmarks/benchmark_adversarial.py --dataset benchmarks/data/adversarial_v3.json

Compares full pipeline (deobfuscator + regex + Luhn) vs raw regex (no deobfuscation)
on the fresh adversarial dataset.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# ── Imports — full pipeline via RegexDetector ──────────────────────────
sys.path.insert(0, str(PROJECT_ROOT / "core" / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "plugins" / "detector-regex" / "src"))

from piifilter_detector_regex.detector import RegexDetector
from piifilter_detector_regex.patterns import PATTERN_DEFS
from piifilter.shared.models import EntityType, DetectedEntity
from piifilter.shared.deobfuscator import Deobfuscator

# ── Helpers matching the exact benchmark logic ──────────────────────────────

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


def luhn_valid(digits: str) -> bool:
    nums = [int(d) for d in digits if d.isdigit()]
    if len(nums) < 13:
        return False
    for i in range(len(nums) - 2, -1, -2):
        nums[i] *= 2
        if nums[i] > 9:
            nums[i] -= 9
    return sum(nums) % 10 == 0


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


# ── Categorization ──────────────────────────────────────────────────────────

# Maps every strategy string found in the v3 dataset to its display category.
# The categorize() function does prefix matching, so order matters:
# more specific prefixes must come before more general ones.
STRATEGY_CATEGORIES: list[tuple[str, str]] = [
    # Punctuation-related
    ("punctuation-stuffed", "Punctuation-stuffed"),
    ("punct-stuffed", "Punctuation-stuffed"),
    ("punct-stuff", "Punctuation-stuffed"),
    # Emoji
    ("emoji-substitution", "Emoji substitution"),
    ("emoji substitution", "Emoji substitution"),
    # Leet / hex / binary
    ("leet-speak extended", "Leet-speak extended"),
    ("l33tspeak", "L33tspeak"),
    ("hex-escape", "Hexadecimal encoding"),
    ("hexadecimal encoding", "Hexadecimal encoding"),
    ("hex-encoding", "Hexadecimal encoding"),
    ("binary-8bit", "Binary encoding"),
    ("binary encoding", "Binary encoding"),
    # Words / text transforms
    ("reversed-words", "Reversed words"),
    ("reversed words", "Reversed words"),
    ("camelCase_split", "CamelCase split"),
    ("camelCase split", "CamelCase split"),
    ("case-shifted", "Case-shifted"),
    ("pig-latin-ip", "Pig-latin style"),
    ("pig-latin style", "Pig-latin style"),
    ("pig-latin", "Pig-latin style"),
    # Encoding / escaping
    ("unicode-superscript-subscript", "Unicode fractions"),
    ("unicode-fractions", "Unicode fractions"),
    ("unicode fractions", "Unicode fractions"),
    ("fractional characters", "Fractional characters"),
    ("xml-escape", "XML escaping"),
    ("xml-escaping", "XML escaping"),
    ("XML escaping", "XML escaping"),
    ("double-encoding", "Double encoding"),
    ("double encoding", "Double encoding"),
    # Structural
    ("zwj-interleaving", "ZWJ interleaving"),
    ("zero-width joiner interleaving", "ZWJ interleaving"),
    ("syllabic-split", "Syllabic split"),
    ("syllabic split", "Syllabic split"),
    ("morse-code", "Morse code"),
    ("morse code", "Morse code"),
    ("circ-shift-in-segment", "Circular-shifted"),
    ("circular-shifted", "Circular-shifted"),
    # Catch-all fallback
    ("custom", "Other"),
]


def categorize(ex: dict[str, Any]) -> str:
    strat = ex.get("strategy", "")
    for prefix, cat in STRATEGY_CATEGORIES:
        if strat.startswith(prefix):
            return cat
    # Fallback: by entity type
    return f"{ex.get('type', 'UNKNOWN')}"


def load_dataset(path: str) -> list[dict[str, Any]]:
    data = json.loads(Path(path).read_text())
    return data.get("examples", data if isinstance(data, list) else [])


def run_benchmark(dataset_path: str) -> dict[str, Any]:
    patterns = compile_patterns()
    all_examples = load_dataset(dataset_path)

    if not all_examples:
        print(f"  [ERROR] No examples found in {dataset_path}")
        return {"summary": {}, "entries": []}

    # Group by category (strategy)
    categories: dict[str, list[dict[str, Any]]] = {}
    for ex in all_examples:
        cat = categorize(ex)
        categories.setdefault(cat, []).append(ex)

    results: list[dict[str, Any]] = []
    category_summary: dict[str, dict[str, Any]] = {}

    for ex in all_examples:
        text = ex.get("text", "")
        cat = categorize(ex)
        entity_type = ex.get("type", "UNKNOWN")

        # Full pipeline
        full_detections = detect_full_pipeline(text, patterns)
        full_detected = len(full_detections) > 0

        # Raw regex only
        raw_detections = detect_raw_regex(text, patterns)
        raw_detected = len(raw_detections) > 0

        results.append({
            "category": cat,
            "entity_type": entity_type,
            "strategy": ex.get("strategy", ""),
            "label": f"{entity_type}:{ex.get('strategy', '')}",
            "text": repr(text)[1:-1] if any(ord(c) > 127 for c in text) else text,
            "ground_truth": ex.get("ground_truth", ""),
            "pii_value": ex.get("pii_value", ""),
            "full_pipeline_detected": full_detected,
            "full_detections": [
                {"type": d["type"], "value": d["value"], "score": d["score"]}
                for d in full_detections
            ],
            "raw_regex_detected": raw_detected,
            "raw_detections": [
                {"type": d["type"], "value": d["value"], "score": d["score"]}
                for d in raw_detections
            ],
        })

    # Build category summary
    for cat_name in categories:
        cat_examples = categories[cat_name]
        cat_results = [r for r in results if r["category"] == cat_name]
        total = len(cat_results)
        full_detected_count = sum(1 for r in cat_results if r["full_pipeline_detected"])
        raw_detected_count = sum(1 for r in cat_results if r["raw_regex_detected"])
        category_summary[cat_name] = {
            "total": total,
            "full_pipeline_detected": full_detected_count,
            "full_pipeline_rate": round(full_detected_count / total * 100, 1) if total > 0 else 0.0,
            "raw_regex_detected": raw_detected_count,
            "raw_regex_rate": round(raw_detected_count / total * 100, 1) if total > 0 else 0.0,
            "improvement": round((full_detected_count - raw_detected_count) / total * 100, 1) if total > 0 else 0.0,
            "missed_examples": [
                r["label"] for r in cat_results if not r["full_pipeline_detected"]
            ],
        }

    overall_total = len(results)
    overall_full = sum(1 for r in results if r["full_pipeline_detected"])
    overall_raw = sum(1 for r in results if r["raw_regex_detected"])

    # Build per-type summary (entity type)
    type_groups: dict[str, list[dict[str, Any]]] = {}
    for r in results:
        etype = r["entity_type"]
        type_groups.setdefault(etype, []).append(r)

    type_summary: dict[str, dict[str, Any]] = {}
    for etype, ers in type_groups.items():
        total = len(ers)
        full = sum(1 for e in ers if e["full_pipeline_detected"])
        raw = sum(1 for e in ers if e["raw_regex_detected"])
        type_summary[etype] = {
            "total": total,
            "full_pipeline_detected": full,
            "full_pipeline_rate": round(full / total * 100, 1),
            "raw_regex_detected": raw,
            "raw_regex_rate": round(raw / total * 100, 1),
            "improvement": round((full - raw) / total * 100, 1),
            "missed_examples": [
                r["label"] for r in ers if not r["full_pipeline_detected"]
            ],
        }

    return {
        "summary": {
            "overall": {
                "total_examples": overall_total,
                "full_pipeline_detected": overall_full,
                "full_pipeline_rate": round(overall_full / overall_total * 100, 1),
                "raw_regex_detected": overall_raw,
                "raw_regex_rate": round(overall_raw / overall_total * 100, 1),
                "deobfuscation_improvement": round((overall_full - overall_raw) / overall_total * 100, 1),
            },
            "by_category": category_summary,
            "by_type": type_summary,
        },
        "entries": results,
    }


def print_summary(data: dict[str, Any]) -> None:
    summary = data["summary"]
    if not summary:
        print("  No results.")
        return
    overall = summary["overall"]
    by_cat = summary["by_category"]
    by_type = summary.get("by_type", {})

    print("=" * 100)
    print("  ADVERSARIAL V3 BENCHMARK — Fresh Dataset (Independent from Training)")
    print("=" * 100)
    print()
    print(f"  Total examples            : {overall['total_examples']}")
    print(f"  Full pipeline (deob+regex) : {overall['full_pipeline_detected']} ({overall['full_pipeline_rate']}%)")
    print(f"  Raw regex only            : {overall['raw_regex_detected']} ({overall['raw_regex_rate']}%)")
    print(f"  Deobfuscation improvement  : +{overall['deobfuscation_improvement']}%")
    print()

    # ── Per-strategy category table ──
    print("  ── By Obfuscation Strategy ──")
    print()
    print(f"  {'Strategy':40s} {'Total':>5s} {'Full Pipe':>10s} {'Raw':>5s} {'Gain':>6s} {'Bar':>10s}")
    print(f"  {'─'*40} {'─'*5} {'─'*10} {'─'*5} {'─'*6} {'─'*10}")
    for cat_name in sorted(by_cat.keys()):
        c = by_cat[cat_name]
        full_pct = c["full_pipeline_rate"]
        raw_pct = c["raw_regex_rate"]
        bar = "█" * int(full_pct / 10) + "░" * (10 - int(full_pct / 10))
        gain = f"+{c['improvement']:.1f}%" if c["improvement"] > 0 else (
            " " if c["improvement"] == 0 else f"{c['improvement']:.1f}%")
        print(f"  {cat_name:40s} {c['total']:5d} {full_pct:>7.1f}%  {raw_pct:>4.1f}% {gain:>6s} {bar:>10s}")

    print()
    print(f"  {'OVERALL':40s} {overall['total_examples']:5d} {overall['full_pipeline_rate']:>7.1f}%  {overall['raw_regex_rate']:>4.1f}% +{overall['deobfuscation_improvement']:.1f}%")
    print()

    # ── Per-entity-type table ──
    print("  ── By Entity Type ──")
    print()
    print(f"  {'Entity Type':24s} {'Total':>5s} {'Full Pipe':>10s} {'Raw':>5s} {'Gain':>6s} {'Bar':>10s}")
    print(f"  {'─'*24} {'─'*5} {'─'*10} {'─'*5} {'─'*6} {'─'*10}")
    for etype in sorted(by_type.keys()):
        c = by_type[etype]
        full_pct = c["full_pipeline_rate"]
        raw_pct = c["raw_regex_rate"]
        bar = "█" * int(full_pct / 10) + "░" * (10 - int(full_pct / 10))
        gain = f"+{c['improvement']:.1f}%" if c["improvement"] > 0 else (
            " " if c["improvement"] == 0 else f"{c['improvement']:.1f}%")
        print(f"  {etype:24s} {c['total']:5d} {full_pct:>7.1f}%  {raw_pct:>4.1f}% {gain:>6s} {bar:>10s}")
    print()

    # Category-level gains
    print("  ── Category Deobfuscation Gains ──")
    print()
    gains = sorted(
        [(c["improvement"], cat_name, c) for cat_name, c in by_cat.items()],
        key=lambda x: -x[0],
    )
    for gain_pct, cat_name, c in gains:
        if gain_pct > 0:
            print(f"  ▲ +{gain_pct:.1f}%  {cat_name:40s}  (raw: {c['raw_regex_rate']:.1f}% → full: {c['full_pipeline_rate']:.1f}%)")
        elif gain_pct == 0 and c["full_pipeline_rate"] == 100 and c["raw_regex_rate"] == 100:
            print(f"  ✓ {cat_name:40s}  (already 100% on raw)")
        elif gain_pct == 0:
            print(f"  ● {cat_name:40s}  (no gain — still {c['full_pipeline_rate']:.1f}%)")
        else:
            print(f"  ▼ {gain_pct:.1f}%  {cat_name:40s}  (raw: {c['raw_regex_rate']:.1f}% → full: {c['full_pipeline_rate']:.1f}%)")

    print()
    print("  ── Remaining Misses (full pipeline) ──")
    print()
    has_misses = False
    for cat_name in sorted(by_cat.keys()):
        c = by_cat[cat_name]
        if c["full_pipeline_rate"] < 100.0:
            has_misses = True
            print(f"  ⚠ {cat_name}  ({c['full_pipeline_rate']:.1f}%)")
            for ex in c["missed_examples"]:
                print(f"      ✗ {ex}")
    if not has_misses:
        print("  ✓ All categories at 100%!")

    print()
    print("=" * 100)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run adversarial benchmark on v3 dataset")
    parser.add_argument("--dataset", type=str, default=str(DATA_DIR / "adversarial_v3.json"),
                        help="Path to the adversarial JSON dataset")
    args = parser.parse_args()

    dataset_path = Path(args.dataset)
    if not dataset_path.exists():
        print(f"[ERROR] Dataset not found: {dataset_path}")
        sys.exit(1)

    print(f"  Loading dataset from: {dataset_path}")
    data = run_benchmark(str(dataset_path))

    output_path = PROJECT_ROOT / "benchmarks" / "adversarial-v3-results.json"
    output_path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"  Results saved to {output_path}\n")

    print_summary(data)


if __name__ == "__main__":
    DATA_DIR = PROJECT_ROOT / "benchmarks" / "data"
    main()