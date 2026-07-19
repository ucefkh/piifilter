#!/usr/bin/env python3
"""PIIFilter Detection Recall Benchmark — measures precision/recall/F1 per entity type
for each detector using a labeled synthetic dataset.

Usage:
    python benchmarks/recall.py
    python benchmarks/recall.py --detectors regex presidio
    python benchmarks/recall.py --output benchmarks/recall-results.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Callable

# ── Project path setup ──────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "core" / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "plugins" / "detector-regex" / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "plugins" / "detector-presidio" / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "plugins" / "detector-gliner" / "src"))

DATA_DIR = Path(__file__).resolve().parent / "data"

# ── Labeled example model ───────────────────────────────────────────────────


@dataclass
class LabeledExample:
    """A single labeled test example."""
    text: str
    entities: list[dict]  # [{"type": "EMAIL", "value": "test@example.com", "start": 0, "end": 16}]


@dataclass
class RecallResult:
    entity_type: str
    true_positives: int = 0
    false_positives: int = 0
    false_negatives: int = 0

    @property
    def precision(self) -> float:
        denom = self.true_positives + self.false_positives
        return self.true_positives / denom if denom else 0.0

    @property
    def recall(self) -> float:
        denom = self.true_positives + self.false_negatives
        return self.true_positives / denom if denom else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) else 0.0


@dataclass
class ConfusionEntry:
    """A single confusion observation: expected type → actual type."""
    expected: str
    actual: str
    count: int = 0


# ── Dataset loader ──────────────────────────────────────────────────────────


def load_dataset(path: Path | None = None) -> list[LabeledExample]:
    """Load labeled dataset from JSON file."""
    if path is None:
        path = DATA_DIR / "pii_dataset.json"
    raw = json.loads(path.read_text())
    return [
        LabeledExample(text=ex["text"], entities=ex.get("entities", []))
        for ex in raw.get("examples", [])
    ]


# ── Detector adapter (same pattern as run.py) ───────────────────────────────


@dataclass
class DetectorAdapter:
    """Uniform interface around any detector implementation."""
    name: str
    detect_fn: Callable[[str], list[dict[str, Any]]]


def make_regex_adapter() -> DetectorAdapter:
    """Create adapter for the RegexDetector plugin."""
    from piifilter.shared.models import EntityType
    from piifilter_detector_regex.patterns import PATTERN_DEFS
    import re

    patterns: list[Any] = []
    for type_name, raw_pattern, score in PATTERN_DEFS:
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
        et_name = type_map.get(type_name, type_name.upper())
        try:
            entity_type = EntityType(et_name)
        except ValueError:
            entity_type = EntityType("PERSON") if hasattr(EntityType, "PERSON") else EntityType("UNKNOWN")
        compiled = re.compile(raw_pattern, re.IGNORECASE)
        patterns.append((entity_type, compiled, score))

    async def detect(text: str) -> list[dict[str, Any]]:
        if not text:
            return []
        entities: list[dict[str, Any]] = []
        seen_intervals: list[tuple[int, int]] = []
        for entity_type, pattern, score in patterns:
            for match in pattern.finditer(text):
                start, end = match.start(), match.end()
                if start == end:
                    continue
                if any(s <= start and end <= e for s, e in seen_intervals):
                    continue
                entities.append({
                    "entity_type": entity_type.value,
                    "value": match.group(),
                    "start": start,
                    "end": end,
                    "score": score,
                    "detector": "regex",
                })
                seen_intervals.append((start, end))
        entities.sort(key=lambda e: e["start"])
        return entities

    return DetectorAdapter(name="regex", detect_fn=detect)


async def make_presidio_adapter() -> DetectorAdapter:
    """Create adapter for the PresidioDetector plugin."""
    from piifilter_detector_presidio.detector import PresidioDetector

    detector = PresidioDetector()
    try:
        await detector.initialize()
    except Exception:
        pass

    async def detect(text: str) -> list[dict[str, Any]]:
        if not text:
            return []
        results = await detector.detect(text)
        entities = []
        for r in results:
            entities.append({
                "entity_type": r.get("entity_type", "UNKNOWN"),
                "value": r.get("value", ""),
                "start": r.get("start", 0),
                "end": r.get("end", 0),
                "score": r.get("score", 1.0),
                "detector": "presidio",
            })
        return entities

    return DetectorAdapter(name="presidio", detect_fn=detect)


def make_gliner_adapter() -> DetectorAdapter:
    """Stub adapter for GLiNER (returns empty)."""
    async def detect(text: str) -> list[dict[str, Any]]:
        return []
    return DetectorAdapter(name="gliner", detect_fn=detect)


async def make_pipeline_adapter(shared_presidio: DetectorAdapter | None = None) -> DetectorAdapter:
    """Combined pipeline adapter (regex + presidio, deduped)."""
    rd = make_regex_adapter()
    pd = shared_presidio
    if pd is None:
        try:
            pd = await make_presidio_adapter()
        except Exception:
            pass

    async def detect(text: str) -> list[dict[str, Any]]:
        all_entities: list[dict[str, Any]] = []
        try:
            all_entities.extend(await rd.detect_fn(text))
        except Exception:
            pass
        if pd is not None:
            try:
                pd_results = await pd.detect_fn(text)
                if pd_results:
                    all_entities.extend(pd_results)
            except Exception:
                pass
        # Dedup by (start, end, entity_type)
        all_entities.sort(key=lambda e: (-e.get("score", 0), e["start"]))
        seen = set()
        deduped = []
        for e in all_entities:
            key = (e["start"], e["end"], e["entity_type"])
            if key not in seen:
                seen.add(key)
                deduped.append(e)
        deduped.sort(key=lambda e: e["start"])
        return deduped

    return DetectorAdapter(name="pipeline", detect_fn=detect)


# ── Evaluation logic ────────────────────────────────────────────────────────


def normalize_type(t: str) -> str:
    """Normalize entity type strings for comparison."""
    return t.upper().replace("_ADDRESS", "").replace("_NUMBER", "")


def is_overlapping(start1: int, end1: int, start2: int, end2: int, threshold: float = 0.5) -> bool:
    """Check if two spans overlap significantly (IoU > threshold)."""
    intersection = max(0, min(end1, end2) - max(start1, start2))
    smallest = min(end1 - start1, end2 - start2)
    if smallest == 0:
        return False
    return (intersection / smallest) >= threshold


async def evaluate_detector(detector_name: str, dataset: list[LabeledExample],
                           detector_fn: Callable[[str], Any]) -> dict[str, Any]:
    """Run a detector across the dataset and compute precision/recall/F1 per entity type.

    Uses strict span matching: a detection is a true positive only if it overlaps
    sufficiently with the labeled entity AND its type matches.
    """
    # Per-type results
    type_results: dict[str, RecallResult] = defaultdict(lambda: RecallResult(entity_type=""))

    # Confusion matrix: expected_type -> {actual_type: count}
    confusion: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    # Per-example tracking
    example_results: list[dict[str, Any]] = []

    total_expected = 0
    total_detected = 0
    total_tp = 0
    total_fp = 0
    total_fn = 0

    detector_name_lower = detector_name.lower()

    for idx, example in enumerate(dataset):
        text = example.text
        expected_entities = example.entities

        # Run detector (async, await it)
        try:
            detected = await detector_fn(text)
        except Exception as exc:
            detected = []
            print(f"  [WARN] Detector '{detector_name}' failed on example {idx}: {exc}")

        # Track which expected entities were found and which detections were used
        expected_matched = [False] * len(expected_entities)
        detected_matched = [False] * len(detected)

        expected_by_type: dict[str, list[dict]] = defaultdict(list)
        for ee in expected_entities:
            expected_by_type[ee["type"]].append(ee)

        for di, det in enumerate(detected):
            det_type = str(det.get("entity_type", "UNKNOWN")).upper()
            det_start = det.get("start", 0)
            det_end = det.get("end", 0)
            det_text = det.get("value", "")

            matched = False
            for ei, ee in enumerate(expected_entities):
                if expected_matched[ei]:
                    continue
                exp_type = ee["type"].upper()
                exp_start = ee.get("start", 0)
                exp_end = ee.get("end", 0)

                # Check type match first (flexible)
                type_match = (det_type == exp_type)

                # Check span overlap
                span_match = is_overlapping(det_start, det_end, exp_start, exp_end, 0.5)

                if type_match and span_match:
                    expected_matched[ei] = True
                    detected_matched[di] = True
                    matched = True
                    break

            if not matched:
                # Record confusion: what was expected at this span vs what was detected
                # Find expected entity at this location
                found_expected = None
                for ee in expected_entities:
                    if is_overlapping(det_start, det_end, ee["start"], ee["end"], 0.25):
                        found_expected = ee["type"].upper()
                        break
                if found_expected:
                    confusion[found_expected][det_type] += 1
                else:
                    confusion["NONE"][det_type] += 1

        # Count per-type statistics
        for exp_type in set(ee["type"] for ee in expected_entities):
            et = exp_type.upper()
            tp = sum(1 for ei, ee in enumerate(expected_entities)
                     if ee["type"].upper() == et and expected_matched[ei])
            fn = sum(1 for ei, ee in enumerate(expected_entities)
                     if ee["type"].upper() == et and not expected_matched[ei])

            if et not in type_results:
                type_results[et] = RecallResult(entity_type=et)
            type_results[et].true_positives += tp
            type_results[et].false_negatives += fn

        for di, det in enumerate(detected):
            det_type = str(det.get("entity_type", "UNKNOWN")).upper()
            if detected_matched[di]:
                if det_type not in type_results:
                    type_results[det_type] = RecallResult(entity_type=det_type)
                type_results[det_type].true_positives += 1
            else:
                if det_type not in type_results:
                    type_results[det_type] = RecallResult(entity_type=det_type)
                type_results[det_type].false_positives += 1

        # Track totals
        total_expected += len(expected_entities)
        total_detected += len(detected)
        total_tp += sum(1 for m in expected_matched if m)
        total_fp += sum(1 for m in detected_matched if not m)
        total_fn += sum(1 for m in expected_matched if not m)

        example_results.append({
            "index": idx,
            "text_preview": text[:80],
            "expected": len(expected_entities),
            "detected": len(detected),
            "true_positives": sum(1 for m in expected_matched if m),
            "false_positives": sum(1 for m in detected_matched if not m),
            "false_negatives": sum(1 for m in expected_matched if not m),
            "expected_types": sorted(set(ee["type"].upper() for ee in expected_entities)),
            "detected_types": sorted(set(str(d.get("entity_type", "")).upper() for d in detected)),
        })

    # Build results dict
    results_dict: dict[str, Any] = {
        "detector": detector_name_lower,
        "total_examples": len(dataset),
        "total_expected_entities": total_expected,
        "total_detected_entities": total_detected,
        "total_true_positives": total_tp,
        "total_false_positives": total_fp,
        "total_false_negatives": total_fn,
        "overall_precision": total_tp / (total_tp + total_fp) if (total_tp + total_fp) else 0.0,
        "overall_recall": total_tp / (total_tp + total_fn) if (total_tp + total_fn) else 0.0,
        "overall_f1": 2 * (total_tp / (total_tp + total_fp)) * (total_tp / (total_tp + total_fn)) / ((total_tp / (total_tp + total_fp)) + (total_tp / (total_tp + total_fn))) if (total_tp + total_fp) and (total_tp + total_fn) else 0.0,
        "per_type": {},
        "confusion_matrix": {k: dict(v) for k, v in confusion.items()},
        "example_results": example_results,
    }

    # Sort entity types for consistent output
    for et in sorted(type_results.keys()):
        tr = type_results[et]
        results_dict["per_type"][et] = {
            "true_positives": tr.true_positives,
            "false_positives": tr.false_positives,
            "false_negatives": tr.false_negatives,
            "precision": round(tr.precision, 4),
            "recall": round(tr.recall, 4),
            "f1": round(tr.f1, 4),
        }

    return results_dict


# ── Console output ──────────────────────────────────────────────────────────


def print_table(rows: list[list[str]], headers: list[str]) -> None:
    """Print a formatted table to the console."""
    col_widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            col_widths[i] = max(col_widths[i], len(cell))

    sep = "  " + "  ".join(["-" * w for w in col_widths])
    hdr = "  " + "  ".join(h.ljust(col_widths[i]) for i, h in enumerate(headers))
    print(hdr)
    print(sep)
    for row in rows:
        print("  " + "  ".join(cell.ljust(col_widths[i]) for i, cell in enumerate(row)))


def print_results(all_results: dict[str, dict[str, Any]]) -> None:
    """Print recall benchmark results."""
    print("\n" + "=" * 90)
    print("  PIIFilter Detection Recall Benchmark Report")
    print("=" * 90)
    print(f"  Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}")
    print()

    for detector_name, results in all_results.items():
        print(f"  ── {detector_name.upper()} ──")
        print(f"  Examples: {results['total_examples']}  |  "
              f"Expected: {results['total_expected_entities']}  |  "
              f"Detected: {results['total_detected_entities']}")
        print(f"  Overall: Precision={results['overall_precision']:.4f}  "
              f"Recall={results['overall_recall']:.4f}  "
              f"F1={results['overall_f1']:.4f}  "
              f"TP={results['total_true_positives']}  "
              f"FP={results['total_false_positives']}  "
              f"FN={results['total_false_negatives']}")
        print()

        # Per-type table
        headers = ["Entity Type", "Precision", "Recall", "F1", "TP", "FP", "FN"]
        rows = []
        for et, metrics in sorted(results["per_type"].items()):
            rows.append([
                et,
                f"{metrics['precision']:.4f}",
                f"{metrics['recall']:.4f}",
                f"{metrics['f1']:.4f}",
                str(metrics['true_positives']),
                str(metrics['false_positives']),
                str(metrics['false_negatives']),
            ])
        print_table(rows, headers)
        print()

        # Confusion matrix
        confusion = results.get("confusion_matrix", {})
        if confusion:
            print("  Confusion Matrix (expected → detected):")
            all_actual_types: set[str] = set()
            for v in confusion.values():
                all_actual_types.update(v.keys())
            sorted_actual = sorted(all_actual_types)
            cm_headers = ["Expected \\ Actual"] + sorted_actual
            cm_rows = []
            for exp_type in sorted(confusion.keys()):
                row = [exp_type]
                for act_type in sorted_actual:
                    row.append(str(confusion[exp_type].get(act_type, 0)))
                cm_rows.append(row)
            print_table(cm_rows, cm_headers)
            print()

        # Bottom N false positives and false negatives
        example_results = results.get("example_results", [])
        fp_examples = [ex for ex in example_results if ex["false_positives"] > 0][:3]
        fn_examples = [ex for ex in example_results if ex["false_negatives"] > 0][:3]

        if fp_examples:
            print("  Sample false positives (top 3):")
            for ex in fp_examples:
                print(f"    Example {ex['index']}: text={ex['text_preview'][:60]}... "
                      f"(detected {ex['false_positives']} extra)")

        if fn_examples:
            print("  Sample false negatives (top 3):")
            for ex in fn_examples:
                print(f"    Example {ex['index']}: text={ex['text_preview'][:60]}... "
                      f"(missed {ex['false_negatives']} entities)")

        print()

    # Inter-detector comparison
    if len(all_results) > 1:
        print("  ── INTER-DETECTOR COMPARISON ──")
        headers = ["Metric"] + list(all_results.keys())
        rows = []
        for metric_key, metric_label in [("overall_precision", "Precision"),
                                          ("overall_recall", "Recall"),
                                          ("overall_f1", "F1"),
                                          ("total_true_positives", "TP"),
                                          ("total_false_positives", "FP"),
                                          ("total_false_negatives", "FN")]:
            row = [metric_label]
            for det_name in all_results.keys():
                val = all_results[det_name][metric_key]
                if isinstance(val, float):
                    row.append(f"{val:.4f}")
                else:
                    row.append(str(val))
            rows.append(row)
        print_table(rows, headers)
        print()


# ── Main ────────────────────────────────────────────────────────────────────


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="PIIFilter Detection Recall Benchmark",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--detectors",
        type=str,
        nargs="+",
        default=["regex", "presidio"],
        help="Detectors to benchmark (default: regex presidio)",
    )
    parser.add_argument(
        "--dataset",
        type=str,
        default=None,
        help="Path to labeled dataset JSON (default: benchmarks/data/pii_dataset.json)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="benchmarks/recall-results.json",
        help="Output path for JSON results (default: benchmarks/recall-results.json)",
    )
    args = parser.parse_args()

    # Load dataset
    dataset_path = Path(args.dataset) if args.dataset else None
    dataset = load_dataset(dataset_path)
    print(f"\n  Loaded dataset: {len(dataset)} examples")
    total_entities = sum(len(ex.entities) for ex in dataset)
    print(f"  Total labeled entities: {total_entities}")
    entity_types = sorted(set(ee["type"] for ex in dataset for ee in ex.entities))
    print(f"  Entity types covered: {len(entity_types)} → {', '.join(entity_types)}")
    print()

    # Build detector adapters
    adapter_factories: dict[str, Callable[[], DetectorAdapter]] = {
        "regex": make_regex_adapter,
        "presidio": make_presidio_adapter,
        "gliner": make_gliner_adapter,
    }

    adapters: list[DetectorAdapter] = []
    for name in args.detectors:
        if name in adapter_factories:
            factory = adapter_factories[name]
            try:
                result = factory()
                if asyncio.iscoroutine(result):
                    result = await result
                adapters.append(result)
            except Exception as exc:
                print(f"  Warning: Failed to create detector '{name}': {exc}")
        else:
            print(f"  Warning: Unknown detector '{name}', skipping")

    # Also add pipeline if both regex and presidio are selected
    presidio_adapter = None
    for a in adapters:
        if a.name == "presidio":
            presidio_adapter = a
            break
    if "regex" in args.detectors and presidio_adapter is not None:
        try:
            pipeline = await make_pipeline_adapter(shared_presidio=presidio_adapter)
            adapters.append(pipeline)
        except Exception as exc:
            print(f"  Warning: Pipeline benchmark unavailable: {exc}")

    if not adapters:
        print("No detectors to benchmark!")
        sys.exit(1)

    print(f"  Detectors: {[a.name for a in adapters]}")
    print()

    # Run evaluation
    all_results: dict[str, dict[str, Any]] = {}

    for adapter in adapters:
        print(f"  Evaluating '{adapter.name}'...")
        t_start = time.perf_counter()

        results = await evaluate_detector(
            adapter.name,
            dataset,
            adapter.detect_fn,
        )

        elapsed = time.perf_counter() - t_start
        print(f"    Completed in {elapsed:.2f}s")
        all_results[adapter.name] = results

    # Assemble full report
    report: dict[str, Any] = {
        "title": "PIIFilter Detection Recall Benchmark Report",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "dataset": {
            "path": str(dataset_path or DATA_DIR / "pii_dataset.json"),
            "examples": len(dataset),
            "total_entities": total_entities,
            "entity_types": entity_types,
        },
        "detectors": all_results,
        "comparison": {},
    }

    # Build comparison section
    if len(all_results) > 1:
        comparison = {
            "overall_precision": {},
            "overall_recall": {},
            "overall_f1": {},
            "total_tp": {},
            "total_fp": {},
            "total_fn": {},
        }
        for det_name, results in all_results.items():
            comparison["overall_precision"][det_name] = round(results["overall_precision"], 4)
            comparison["overall_recall"][det_name] = round(results["overall_recall"], 4)
            comparison["overall_f1"][det_name] = round(results["overall_f1"], 4)
            comparison["total_tp"][det_name] = results["total_true_positives"]
            comparison["total_fp"][det_name] = results["total_false_positives"]
            comparison["total_fn"][det_name] = results["total_false_negatives"]
        report["comparison"] = comparison

    # Save results
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, default=str))
    print(f"\n  Results saved to {output_path.resolve()}")

    # Print to console
    print_results(all_results)


if __name__ == "__main__":
    asyncio.run(main())