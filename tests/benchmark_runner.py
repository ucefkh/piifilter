"""PIIFilter Golden Corpus Benchmark Runner — precision, recall, F1 evaluation.

Evaluates the RegexDetector against a labeled golden corpus and reports
per-entity-type and overall precision/recall/F1. Supports mode presets
(high_recall, balanced, high_precision) that set confidence thresholds.

Usage:
    uv run python -m tests.benchmark_runner
    uv run python tests/benchmark_runner.py
    uv run python tests/benchmark_runner.py --mode high_precision
    uv run python tests/benchmark_runner.py --threshold 0.80
    uv run python tests/benchmark_runner.py --f1-gate 0.85  # CI mode
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# ── Imports ───────────────────────────────────────────────────────────────
sys.path.insert(0, str(PROJECT_ROOT / "core" / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "plugins" / "detector-regex" / "src"))

from piifilter_detector_regex.detector import RegexDetector
from piifilter.shared.models import EntityType

# ── Mode presets ──────────────────────────────────────────────────────────
# Each mode defines per-entity-type confidence thresholds.
# Entities whose detection confidence is below the threshold are filtered out
# (treated as not detected) for scoring purposes.
#
# high_recall:   low thresholds — catch as much as possible, accept FPs
# balanced:      moderate thresholds — trade-off between precision and recall
# high_precision: high thresholds — only emit high-confidence detections

MODE_PRESETS: dict[str, dict[str, float]] = {
    "high_recall": {
        # Near-zero thresholds for all types — accept everything
        "default": 0.0,
        # Slightly higher for types prone to FP so we don't drown in noise
        "CITY": 0.30,
        "COMPANY": 0.30,
        "PERSON": 0.30,
        "CUSTOMER_NAME": 0.30,
        "EMPLOYEE_NAME": 0.30,
        "PROJECT_NAME": 0.30,
        "PHONE": 0.40,
        "COUNTRY": 0.30,
        "DOMAIN": 0.30,
    },
    "balanced": {
        # Default moderate threshold
        "default": 0.50,
        # High-precision types — these are exact matches, keep low threshold
        "EMAIL": 0.0,
        "IP_ADDRESS": 0.0,
        "CREDIT_CARD": 0.0,
        "JWT": 0.0,
        "API_KEY": 0.0,
        "SSH_KEY": 0.0,
        "DATABASE_URL": 0.0,
        "PRIVATE_URL": 0.0,
        "PASSPORT": 0.0,
        "SOCIAL_SECURITY": 0.0,
        "BANK_ACCOUNT": 0.0,
        "IBAN": 0.0,
        "GPS": 0.0,
        "DATE": 0.0,
        "URL": 0.0,
        "FILE_PATH": 0.0,
        # Context-dependent types need moderate threshold to avoid FP
        "PERSON": 0.60,
        "CITY": 0.50,
        "COMPANY": 0.50,
        "COUNTRY": 0.50,
        "CUSTOMER_NAME": 0.50,
        "EMPLOYEE_NAME": 0.50,
        "PROJECT_NAME": 0.50,
        "PHONE": 0.50,
        "ADDRESS": 0.50,
        "DOMAIN": 0.50,
    },
    "high_precision": {
        # High thresholds — only accept strong signals
        "default": 0.80,
        # Structural/algorithmic types are already high precision
        "CREDIT_CARD": 0.0,
        "SOCIAL_SECURITY": 0.0,
        "JWT": 0.0,
        "SSH_KEY": 0.0,
        "DATABASE_URL": 0.0,
        "PRIVATE_URL": 0.0,
        "IBAN": 0.0,
        # Context-dependent types need high threshold to avoid FP
        "PERSON": 0.75,
        "CITY": 0.70,
        "COMPANY": 0.70,
        "COUNTRY": 0.70,
        "CUSTOMER_NAME": 0.75,
        "EMPLOYEE_NAME": 0.75,
        "PROJECT_NAME": 0.75,
        "PHONE": 0.75,
        "ADDRESS": 0.75,
        "DOMAIN": 0.75,
        "EMAIL": 0.75,
        "IP_ADDRESS": 0.75,
        "GPS": 0.75,
        "DATE": 0.75,
        "URL": 0.75,
        "FILE_PATH": 0.75,
        "API_KEY": 0.80,
        "PASSPORT": 0.75,
        "BANK_ACCOUNT": 0.75,
    },
}


def get_threshold(mode: str, entity_type: str, override: float | None = None) -> float:
    """Resolve the confidence threshold for a given entity type and mode.

    Priority: explicit override > per-type in mode preset > mode default > 0.0
    """
    if override is not None:
        return override
    preset = MODE_PRESETS.get(mode, MODE_PRESETS["balanced"])
    return preset.get(entity_type, preset.get("default", 0.0))


# ── Scoring ────────────────────────────────────────────────────────────────


def compute_metrics(
    true_positives: int,
    false_positives: int,
    false_negatives: int,
) -> dict[str, float]:
    """Compute precision, recall, and F1 from counts.

    Returns dict with 'precision', 'recall', 'f1' keys.
    For edge cases where denominator is 0, the metric is 0.0.
    """
    precision = (
        true_positives / (true_positives + false_positives)
        if (true_positives + false_positives) > 0
        else 0.0
    )
    recall = (
        true_positives / (true_positives + false_negatives)
        if (true_positives + false_negatives) > 0
        else 0.0
    )
    f1 = (
        2 * precision * recall / (precision + recall)
        if (precision + recall) > 0
        else 0.0
    )
    return {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
    }


def _normalize_entity(e: dict[str, Any] | Any) -> dict[str, Any]:
    """Normalize a detection result to a dict with type/value/start/end/score keys.

    Handles both CandidateSpan dataclass objects and plain dicts.
    """
    if isinstance(e, dict):
        return {
            "type": e.get("type", e.get("entity_type", "UNKNOWN")),
            "value": e.get("value", e.get("text", "")),
            "start": e.get("start", 0),
            "end": e.get("end", 0),
            "score": e.get("score", e.get("confidence", 1.0)),
        }
    # dataclass-style object (CandidateSpan or DetectedEntity)
    return {
        "type": e.entity_type.value if hasattr(e, 'entity_type') else getattr(e, 'type', 'UNKNOWN'),
        "value": getattr(e, 'value', getattr(e, 'text', '')),
        "start": getattr(e, 'start', 0),
        "end": getattr(e, 'end', 0),
        "score": getattr(e, 'confidence', getattr(e, 'score', 1.0)),
    }


def score_detections(
    golden_entities: list[dict[str, Any]],
    detected_entities: list[dict[str, Any] | Any],
    entity_type: str | None = None,
    threshold: float = 0.0,
) -> dict[str, Any]:
    """Score detections against golden annotations for one or all entity types.

    Entity matching rules:
    - Type must match exactly.
    - Predicted span must overlap the golden span (start <= predicted_end AND
      end >= predicted_start).
    - Predicted confidence must be >= threshold.
    - A golden entity counts as 'detected' (TP) if ANY predicted entity of
      the same type overlaps it.
    - A predicted entity counts as FP if it does NOT overlap any golden
      entity of the same type.

    Returns dict with tp, fp, fn counts plus precision/recall/f1.
    """
    # Filter by entity type
    gold: list[dict[str, Any]] = [
        e for e in golden_entities
        if entity_type is None or e["type"] == entity_type
    ]

    # Normalize detected entities
    normalized = [_normalize_entity(d) for d in detected_entities]
    if entity_type is not None:
        normalized = [d for d in normalized if d["type"] == entity_type]

    # Apply threshold filter
    normalized = [d for d in normalized if d["score"] >= threshold]

    # Track which golden entities were matched
    gold_matched = [False] * len(gold)
    # Track which predicted entities are FPs
    pred_fp = [True] * len(normalized)

    for gi, g in enumerate(gold):
        g_start = g.get("start", 0)
        g_end = g.get("end", 0)
        for pi, p in enumerate(normalized):
            p_start = p.get("start", 0)
            p_end = p.get("end", 0)
            # Overlap check: intervals [g_start, g_end) and [p_start, p_end)
            if p_start < g_end and p_end > g_start:
                gold_matched[gi] = True
                pred_fp[pi] = False

    tp = sum(gold_matched)
    fn = len(gold) - tp
    fp = sum(pred_fp)

    metrics = compute_metrics(tp, fp, fn)
    return {
        "n_golden": len(gold),
        "n_detected": len(normalized),
        "tp": tp,
        "fp": fp,
        "fn": fn,
        **metrics,
    }


# ── Benchmark runner ──────────────────────────────────────────────────────


def load_golden_corpus(path: Path | None = None) -> list[dict[str, Any]]:
    """Load the golden corpus JSON file.

    Default path: benchmarks/data/golden_corpus.json
    """
    if path is None:
        path = PROJECT_ROOT / "benchmarks" / "data" / "golden_corpus.json"
    if not path.exists():
        print(f"FAIL: Golden corpus not found at {path}", file=sys.stderr)
        sys.exit(1)
    data = json.loads(path.read_text())
    return data["examples"]


def detect_via_detector(text: str, detector: RegexDetector) -> list[Any]:
    """Run text through the actual RegexDetector detection pipeline."""
    return asyncio.run(detector.detect(text))


# ── Reporting ─────────────────────────────────────────────────────────────


def format_pct(value: float) -> str:
    """Format a 0-1 value as percentage string."""
    if isinstance(value, str):
        return value
    return f"{value * 100:.2f}%"


def print_results(
    overall: dict[str, Any],
    per_type: dict[str, dict[str, Any]],
    mode: str,
    threshold: float | None,
    f1_gate: float | None,
    failed_types: list[str]
        | dict[str, dict[str, Any]],
) -> None:
    """Print formatted benchmark results to stdout."""
    print("=" * 80)
    print("  PIIFilter Golden Corpus Benchmark")
    print("=" * 80)
    print(f"  Mode:        {mode}")
    if threshold is not None:
        print(f"  Override threshold: {threshold:.2f}")
    print(f"  Total golden entities: {overall['n_golden']}")
    print(f"  Total detections:     {overall['n_detected']}")
    print()
    print(f"  {'Entity Type':25s} {'Golden':>6s} {'Detected':>8s} {'TP':>4s} {'FP':>4s} {'FN':>4s} "
          f"{'Precision':>10s} {'Recall':>10s} {'F1':>8s}")
    print(f"  {'─' * 25} {'─' * 6} {'─' * 8} {'─' * 4} {'─' * 4} {'─' * 4} "
          f"{'─' * 10} {'─' * 10} {'─' * 8}")

    for et in sorted(per_type.keys()):
        m = per_type[et]
        pct_p = format_pct(m["precision"])
        pct_r = format_pct(m["recall"])
        pct_f = format_pct(m["f1"])
        marker = " ✗" if (isinstance(failed_types, dict) and et in failed_types) or (isinstance(failed_types, list) and et in failed_types) else ""
        print(f"  {et:25s} {m['n_golden']:6d} {m['n_detected']:8d} {m['tp']:4d} {m['fp']:4d} "
              f"{m['fn']:4d} {pct_p:>10s} {pct_r:>10s} {pct_f:>8s}{marker}")

    print(f"  {'─' * 25} {'─' * 6} {'─' * 8} {'─' * 4} {'─' * 4} {'─' * 4} "
          f"{'─' * 10} {'─' * 10} {'─' * 8}")
    pct_p = format_pct(overall["precision"])
    pct_r = format_pct(overall["recall"])
    pct_f = format_pct(overall["f1"])
    print(f"  {'OVERALL':25s} {overall['n_golden']:6d} {overall['n_detected']:8d} {overall['tp']:4d} "
          f"{overall['fp']:4d} {overall['fn']:4d} {pct_p:>10s} {pct_r:>10s} {pct_f:>8s}")

    print()
    if f1_gate is not None and isinstance(failed_types, dict) and failed_types:
        print(f"  ✗ F1 GATE FAILED: {len(failed_types)} type(s) below F1={f1_gate:.2f}:")
        for et, fm in sorted(failed_types.items()):
            print(f"      {et:25s}  F1={fm['f1']:.4f}  (required >= {f1_gate:.4f})")
    elif f1_gate is not None:
        print(f"  ✓ F1 GATE PASSED: all types >= F1={f1_gate:.2f}")

    if mode:
        print(f"  Mode preset: {mode}")
        print()


# ── Main ──────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="PIIFilter Golden Corpus Benchmark — precision/recall/F1 evaluation",
    )
    parser.add_argument(
        "--corpus", type=str,
        default=str(PROJECT_ROOT / "benchmarks" / "data" / "golden_corpus.json"),
        help="Path to golden corpus JSON",
    )
    parser.add_argument(
        "--mode", type=str, default="balanced",
        choices=list(MODE_PRESETS.keys()),
        help="Mode preset for confidence thresholds (default: balanced)",
    )
    parser.add_argument(
        "--threshold", type=float, default=None,
        help="Override confidence threshold for all types (0.0-1.0)",
    )
    parser.add_argument(
        "--f1-gate", type=float, default=None,
        help="Exit with code 1 if any entity type's F1 is below this value",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Output results as JSON to stdout",
    )
    parser.add_argument(
        "--output", type=str, default=None,
        help="Write detailed results JSON to this path",
    )
    args = parser.parse_args()

    # 1. Load corpus
    examples = load_golden_corpus(Path(args.corpus))

    # 2. Initialize detector
    detector = RegexDetector()
    asyncio.run(detector.initialize())

    # 3. Run detection on each example
    all_golden: list[dict[str, Any]] = []
    all_detected: list[dict[str, Any]] = []
    per_text_results: list[dict[str, Any]] = []

    for i, ex in enumerate(examples):
        text = ex["text"]
        golden = ex.get("entities", [])

        detected = detect_via_detector(text, detector)

        # Normalize detected entities
        normalized = [_normalize_entity(d) for d in detected]

        all_golden.extend(golden)
        all_detected.extend(normalized)

        per_text_results.append({
            "index": i,
            "text": text,
            "golden": golden,
            "detected": normalized,
        })

    # 4. Score overall
    overall = score_detections(all_golden, all_detected, threshold=0.0)

    # 5. Score per entity type
    entity_types = sorted({e["type"] for e in all_golden} | {e["type"] for e in all_detected})
    per_type: dict[str, dict[str, Any]] = {}
    for et in entity_types:
        et_threshold = get_threshold(args.mode, et, args.threshold)
        per_type[et] = score_detections(
            all_golden, all_detected, entity_type=et, threshold=et_threshold,
        )

    # 6. F1 gate check
    failed_types: dict[str, dict[str, Any]] = {}
    if args.f1_gate is not None:
        for et, m in per_type.items():
            if m["n_golden"] > 0 and m["f1"] < args.f1_gate:
                failed_types[et] = {"f1": m["f1"], "n_golden": m["n_golden"]}

    # 7. Print / output
    if args.json:
        output = {
            "mode": args.mode,
            "threshold": args.threshold,
            "f1_gate": args.f1_gate,
            "overall": overall,
            "per_type": per_type,
            "f1_gate_failed": bool(failed_types),
            "failed_types": list(failed_types.keys()),
            "n_examples": len(examples),
        }
        print(json.dumps(output, indent=2))
    else:
        print_results(overall, per_type, args.mode, args.threshold, args.f1_gate, failed_types)

    # 8. Write detailed output
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_data = {
            "mode": args.mode,
            "threshold": args.threshold,
            "f1_gate": args.f1_gate,
            "overall": overall,
            "per_type": per_type,
            "per_text": per_text_results,
            "f1_gate_failed": bool(failed_types),
            "failed_types": list(failed_types.keys()),
            "n_examples": len(examples),
        }
        output_path.write_text(json.dumps(output_data, indent=2))
        print(f"\n  Detailed results written to {output_path}")

    # 9. Exit code
    if failed_types:
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()