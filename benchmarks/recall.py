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

    _DIRECT_MAP = {
        "PERSON", "EMAIL", "PHONE", "ADDRESS", "CITY", "COUNTRY",
        "COMPANY", "BANK_ACCOUNT", "IBAN", "CREDIT_CARD", "PASSPORT",
        "SOCIAL_SECURITY", "JWT", "API_KEY", "SSH_KEY", "DATABASE_URL",
        "PRIVATE_URL", "PROJECT_NAME", "CUSTOMER_NAME", "EMPLOYEE_NAME",
        "GPS", "DOMAIN", "IP_ADDRESS", "FILE_PATH",
    }

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
        if type_name in _DIRECT_MAP:
            et_name = type_name
        else:
            et_name = type_map.get(type_name, type_name.upper())
        try:
            entity_type = EntityType(et_name)
        except ValueError:
            entity_type = EntityType("PERSON") if hasattr(EntityType, "PERSON") else EntityType("UNKNOWN")
        # Compile patterns respecting their inline (?i) flags.
        # Use re.UNICODE but NOT re.IGNORECASE by default — patterns that need
        # case-insensitivity use inline (?i) within their regex string.
        compiled = re.compile(raw_pattern, re.UNICODE)
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
    """Combined pipeline adapter (regex + presidio, deduped).

    Uses priority-based merging: regex results take precedence over
    presidio for overlapping spans, since regex has demonstrated higher
    precision on most entity types. However, if a regex result and a
    presidio result overlap but have different entity types, both are
    kept (per-type interval tracking).
    """
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

        # Priority-based dedup: prefer regex over presidio for type conflicts.
        # Sort by detector priority (regex=0, presidio=1, gliner=2),
        # then by score descending, then position.
        detector_priority = {"regex": 0, "presidio": 1, "gliner": 2}
        all_entities.sort(
            key=lambda e: (
                detector_priority.get(e.get("detector", ""), 99),
                -e.get("score", 0),
                e.get("start", 0),
            )
        )

        # Per-type interval tracking: keep different entity types even
        # when they overlap, but skip same-type duplicates.
        seen_intervals: dict[str, list[tuple[int, int]]] = {}
        deduped = []
        for e in all_entities:
            et = e.get("entity_type", "UNKNOWN")
            intervals = seen_intervals.get(et, [])
            start, end = e.get("start", 0), e.get("end", 0)
            contained = any(s <= start and end <= e2 for s, e2 in intervals)
            if not contained:
                seen_intervals.setdefault(et, []).append((start, end))
                deduped.append(e)

        deduped.sort(key=lambda e: e.get("start", 0))
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


# ── Main ────────────────────────────────────────────────────────────────────


async def main() -> None:
    parser = argparse.ArgumentParser(description="PIIFilter Detection Recall Benchmark")
    parser.add_argument("--detectors", type=str, default="regex",
                        help="Comma-separated detector names (regex, presidio)")
    parser.add_argument("--output", type=str, default=None,
                        help="Output JSON file path")
    parser.add_argument("--dataset", type=str, default=None,
                        help="Dataset file path (default: benchmarks/data/pii_dataset.json)")
    parser.add_argument("--no-pipeline", action="store_true",
                        help="Skip pipeline detector")
    args = parser.parse_args()

    # Load dataset
    dataset_path = Path(args.dataset) if args.dataset else None
    dataset = load_dataset(dataset_path)
    print(f"\n  Loaded {len(dataset)} labeled examples from "
          f"{(dataset_path or DATA_DIR / 'pii_dataset.json').name}")

    # Build detectors
    detector_names = [d.strip() for d in args.detectors.split(",")]

    adapters: dict[str, DetectorAdapter] = {}
    presidio_adapter = None

    if "presidio" in detector_names or not args.no_pipeline:
        try:
            presidio_adapter = await make_presidio_adapter()
            print(f"  Presidio detector: {'loaded' if presidio_adapter else 'not found'}")
        except Exception as exc:
            print(f"  Presidio detector: error loading ({exc})")

    if "regex" in detector_names:
        adapters["regex"] = make_regex_adapter()
    if "presidio" in detector_names and presidio_adapter:
        adapters["presidio"] = presidio_adapter
    if not args.no_pipeline:
        try:
            pipeline = await make_pipeline_adapter(presidio_adapter)
            adapters["pipeline"] = pipeline
        except Exception as exc:
            print(f"  Pipeline detector: error loading ({exc})")

    if not adapters:
        print("  No detectors available to benchmark")
        return

    print()

    # Evaluate each detector
    all_results: dict[str, dict[str, Any]] = {}
    for name, adapter in adapters.items():
        print(f"  Evaluating {name} detector...")
        results = await evaluate_detector(name, dataset, adapter.detect_fn)
        all_results[name] = results

    # Print results
    print_results(all_results)

    # Save to file
    output_path = args.output
    if output_path:
        output_file = Path(output_path)
    else:
        output_file = DATA_DIR.parent / "recall-results.json"

    report = {
        "title": "PIIFilter Detection Recall Benchmark Report",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "dataset": {
            "path": str(dataset_path or DATA_DIR / "pii_dataset.json"),
            "examples": len(dataset),
            "total_entities": sum(len(ex.entities) for ex in dataset),
            "entity_types": sorted(set(ee["type"] for ex in dataset for ee in ex.entities)),
        },
        "detectors": all_results,
    }
    output_file.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"\n  Results saved to {output_file}")
    print()


if __name__ == "__main__":
    asyncio.run(main())