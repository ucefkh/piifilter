#!/usr/bin/env python3
"""Adversarial Training/Eval Loop — Opus Step 4.

Detects overfit by comparing train vs held-out recall across iterations.

Loads all available adversarial datasets, splits 70/30, and runs the pipeline
detector on mini-batches. If training recall exceeds held-out recall by >10%,
flags the iteration as overfit — catching the 85%→37% generalization crash.
"""

from __future__ import annotations

import asyncio
import json
import math
import random
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

# ── Project path setup ──────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "core" / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "plugins" / "detector-regex" / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "plugins" / "detector-presidio" / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "plugins" / "detector-gliner" / "src"))

DATA_DIR = PROJECT_ROOT / "benchmarks" / "data"

# ── Labeled example model ───────────────────────────────────────────────────

@dataclass
class LabeledExample:
    """A single labeled test example."""
    text: str
    entities: list[dict]  # [{"type": "EMAIL", "value": "...", "start": N, "end": N}]

# ── Adversarial dataset loaders ──────────────────────────────────────────────

def load_adversarial_v3(path: Path) -> list[LabeledExample]:
    """Load adversarial_v3.json format → LabeledExample list.

    Schema: {type, strategy, pii_value, ground_truth, text, seed}
    The pii_value appears literally in the text — we find it by substring search.
    ground_truth is the canonical form (for reference only here).
    """
    raw = json.loads(path.read_text("utf-8"))
    examples: list[LabeledExample] = []
    for ex in raw.get("examples", []):
        text = ex["text"]
        entity_type = ex["type"].upper()
        pii_value = ex["pii_value"]

        # Find the pii_value in the text
        start = text.find(pii_value)
        if start == -1:
            # Try case-insensitive or fuzzy fallback
            # Some pii_values may have encoding issues; skip if not found cleanly
            print(f"  [WARN] Could not locate pii_value in text (v3): {pii_value[:40]!r}...")
            continue

        end = start + len(pii_value)
        examples.append(LabeledExample(
            text=text,
            entities=[{"type": entity_type, "value": pii_value, "start": start, "end": end}],
        ))
    return examples


def load_adversarial_v1(path: Path) -> list[LabeledExample]:
    """Load v1-format adversarial datasets (pii_dataset.json style with text+entities).
    This also works for any dataset in the canonical LabeledExample format.
    """
    raw = json.loads(path.read_text("utf-8"))
    examples = []
    for ex in raw.get("examples", []):
        entities = ex.get("entities", [])
        examples.append(LabeledExample(text=ex["text"], entities=entities))
    return examples


def load_all_adversarial(dirs: list[Path] | None = None) -> list[LabeledExample]:
    """Discover and load ALL available adversarial datasets."""
    if dirs is None:
        dirs = [DATA_DIR]

    all_examples: list[LabeledExample] = []
    loaded_sources: list[str] = []

    search_paths: list[Path] = []
    for d in dirs:
        if d.exists():
            search_paths.extend(sorted(d.glob("*adversarial*")))
            search_paths.extend(sorted(d.glob("*v1*")))
            search_paths.extend(sorted(d.glob("*v2*")))
            search_paths.extend(sorted(d.glob("*v3*")))

    # Deduplicate
    seen = set()
    v3_fnames = {"adversarial_v3.json"}
    for fp in search_paths:
        if fp.suffix != ".json":
            continue
        if fp.name in seen:
            continue
        seen.add(fp.name)

        try:
            # Use v3 loader for files with pii_value/ground_truth schema
            head = fp.read_text("utf-8")[:2000]
            if '"pii_value"' in head and '"ground_truth"' in head:
                examples = load_adversarial_v3(fp)
                fmt = "v3 (adversarial)"
            elif fp.name in v3_fnames:
                examples = load_adversarial_v3(fp)
                fmt = "v3 (adversarial)"
            else:
                examples = load_adversarial_v1(fp)
                fmt = "canonical"
            all_examples.extend(examples)
            loaded_sources.append(f"  {fp.name} ({fmt}): {len(examples)} examples")
        except Exception as exc:
            loaded_sources.append(f"  {fp.name}: SKIPPED ({exc})")

    # Load the main pii_dataset files too
    for fname in ["pii_dataset.json", "pii_dataset_v2.json"]:
        fp = DATA_DIR / fname
        if fp.exists():
            try:
                examples = load_adversarial_v1(fp)
                all_examples.extend(examples)
                loaded_sources.append(f"  {fp.name} (canonical): {len(examples)} examples")
            except Exception as exc:
                loaded_sources.append(f"  {fp.name}: SKIPPED ({exc})")

    print(f"\n{'=' * 80}")
    print(f"  Loaded {len(all_examples)} total adversarial examples from:")
    for s in loaded_sources:
        print(f"    {s}")
    print(f"{'=' * 80}\n")

    return all_examples


# ── Stratified split (simple random) ─────────────────────────────────────────

def random_split(
    examples: list[LabeledExample],
    train_frac: float = 0.7,
    seed: int = 42,
) -> tuple[list[LabeledExample], list[LabeledExample]]:
    """Randomly split examples into train and held-out eval sets."""
    rng = random.Random(seed)
    shuffled = list(examples)
    rng.shuffle(shuffled)
    split_idx = max(1, int(len(shuffled) * train_frac))
    train = shuffled[:split_idx]
    eval_ = shuffled[split_idx:]
    return train, eval_


# ── Evaluation helpers (lightweight, no dataclass overhead) ─────────────────

def is_overlapping(start1: int, end1: int, start2: int, end2: int, threshold: float = 0.5) -> bool:
    """Check if two spans overlap significantly."""
    intersection = max(0, min(end1, end2) - max(start1, start2))
    smallest = min(end1 - start1, end2 - start2)
    if smallest == 0:
        return False
    return (intersection / smallest) >= threshold


async def evaluate_on_subset(
    detector_fn: Callable[[str], Any],
    examples: list[LabeledExample],
) -> dict[str, dict[str, int]]:
    """Run detector on examples, return per-type TP, FN.

    Returns {entity_type: {"tp": N, "fn": N, "n": N}}
    """
    per_type: dict[str, dict[str, int]] = {}

    for example in examples:
        text = example.text
        expected = example.entities

        try:
            detected = await detector_fn(text)
        except Exception:
            detected = []

        expected_matched = [False] * len(expected)

        for det in detected:
            det_type = str(det.get("entity_type", "UNKNOWN")).upper()
            det_start = det.get("start", 0)
            det_end = det.get("end", 0)

            for ei, ee in enumerate(expected):
                if expected_matched[ei]:
                    continue
                exp_type = ee["type"].upper()
                exp_start = ee.get("start", 0)
                exp_end = ee.get("end", 0)

                if det_type == exp_type and is_overlapping(det_start, det_end, exp_start, exp_end, 0.5):
                    expected_matched[ei] = True
                    break

        for ee in expected:
            et = ee["type"].upper()
            if et not in per_type:
                per_type[et] = {"tp": 0, "fn": 0, "n": 0}
            per_type[et]["n"] += 1

        for ei, ee in enumerate(expected):
            et = ee["type"].upper()
            if expected_matched[ei]:
                per_type[et]["tp"] += 1
            else:
                per_type[et]["fn"] += 1

    return per_type


# ── Detector adapter (pipeline) ──────────────────────────────────────────────

@dataclass
class DetectorAdapter:
    name: str
    detect_fn: Callable[[str], Any]


def make_regex_adapter() -> DetectorAdapter:
    """Create adapter for the RegexDetector plugin."""
    from piifilter_detector_regex.detector import RegexDetector as _RealRegexDetector

    _detector_instance: _RealRegexDetector | None = None

    async def detect(text: str) -> list[dict[str, Any]]:
        nonlocal _detector_instance
        if _detector_instance is None:
            _detector_instance = _RealRegexDetector()
            await _detector_instance.initialize()
        raw = await _detector_instance.detect(text)
        return [
            {
                "entity_type": d["type"],
                "value": d["text"],
                "start": d["start"],
                "end": d["end"],
                "score": d["score"],
                "detector": d["detector"],
            }
            for d in raw
        ]

    return DetectorAdapter(name="regex", detect_fn=detect)


async def make_presidio_adapter() -> DetectorAdapter | None:
    """Create adapter for PresidioDetector plugin."""
    try:
        from piifilter_detector_presidio.detector import PresidioDetector
        detector = PresidioDetector()
        await detector.initialize()

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
    except Exception as exc:
        print(f"  Presidio not available: {exc}")
        return None


async def make_pipeline_adapter() -> DetectorAdapter:
    """Combined pipeline (regex + presidio, deduped)."""
    rd = make_regex_adapter()
    pd = await make_presidio_adapter()

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

        # Dedup by detector priority
        detector_priority = {"regex": 0, "presidio": 1, "gliner": 2}
        all_entities.sort(
            key=lambda e: (
                detector_priority.get(e.get("detector", ""), 99),
                -e.get("score", 0),
                e.get("start", 0),
            )
        )

        seen_intervals: dict[str, list[tuple[int, int]]] = {}
        deduped = []
        for e in all_entities:
            et = e.get("entity_type", "UNKNOWN")
            start, end = e.get("start", 0), e.get("end", 0)
            intervals = seen_intervals.get(et, [])
            contained = any(s <= start and end <= e2 for s, e2 in intervals)
            if not contained:
                seen_intervals.setdefault(et, []).append((start, end))
                deduped.append(e)

        deduped.sort(key=lambda e: e.get("start", 0))
        return deduped

    return DetectorAdapter(name="pipeline", detect_fn=detect)


# ── Overfit detection ────────────────────────────────────────────────────────

def compute_weighted_recall(
    per_type: dict[str, dict[str, int]],
) -> dict[str, float]:
    """Compute recall per entity type from {tp, fn, n} counts."""
    result = {}
    for et, counts in per_type.items():
        n = counts["n"]
        if n > 0:
            result[et] = counts["tp"] / n
        else:
            result[et] = 0.0
    return result


def detect_overfit(
    train_recalls: dict[str, float],
    eval_recalls: dict[str, float],
) -> tuple[list[str], dict[str, float]]:
    """Return (overfit_types, degradation_map).

    A type is overfit if train_recall > eval_recall by >10 absolute percentage points.
    degradation = train - eval.
    """
    all_types = set(train_recalls.keys()) | set(eval_recalls.keys())
    overfit: list[str] = []
    degradation: dict[str, float] = {}
    for et in sorted(all_types):
        tr = train_recalls.get(et, 0.0)
        er = eval_recalls.get(et, 0.0)
        deg = tr - er
        degradation[et] = round(deg, 4)
        if deg > 0.10:
            overfit.append(et)
        elif tr > 0.0 and er == 0.0:
            # Train had some success but eval none — strong overfit signal
            overfit.append(et)
    return overfit, degradation


# ── Table formatting ─────────────────────────────────────────────────────────

def print_iteration_table(
    iteration: int,
    train_per_type: dict[str, dict[str, int]],
    eval_per_type: dict[str, dict[str, int]],
    overfit_types: list[str],
    degradation: dict[str, float],
    n_train: int,
    n_eval: int,
    wall_sec: float,
) -> None:
    """Print a compact per-iteration results table."""
    all_types = sorted(set(train_per_type.keys()) | set(eval_per_type.keys()))
    train_recalls = compute_weighted_recall(train_per_type)
    eval_recalls = compute_weighted_recall(eval_per_type)

    # Overall weighted recall
    train_total_tp = sum(c["tp"] for c in train_per_type.values())
    train_total_n = sum(c["n"] for c in train_per_type.values())
    eval_total_tp = sum(c["tp"] for c in eval_per_type.values())
    eval_total_n = sum(c["n"] for c in eval_per_type.values())
    train_overall = train_total_tp / train_total_n if train_total_n else 0.0
    eval_overall = eval_total_tp / eval_total_n if eval_total_n else 0.0
    overall_gap = train_overall - eval_overall
    overfit_flag = " ⚠️ OVERFIT" if overall_gap > 0.10 else ""

    # Header
    print(f"\n{'─' * 90}")
    print(f"  Iteration {iteration:2d}  |  train n={n_train}  eval n={n_eval}  "
          f"({wall_sec:.1f}s)")
    print(f"{'─' * 90}")
    print(f"  {'Type':<28s} | {'Train Recall':>12s} | {'Eval Recall':>12s} | "
          f"{'Gap':>6s} | {'Status':<10s}")
    print(f"  {'-'*28} | {'-'*12} | {'-'*12} | {'-'*6} | {'-'*10}")

    for et in all_types:
        tr = train_recalls.get(et, 0.0)
        er = eval_recalls.get(et, 0.0)
        deg = degradation.get(et, 0.0)
        gap_str = f"{deg:+.4f}"
        if deg > 0.10:
            status = "⚠️ OVERFIT"
        elif deg > 0.05:
            status = "warning"
        else:
            status = "ok"

        train_n = train_per_type.get(et, {}).get("n", 0)
        eval_n = eval_per_type.get(et, {}).get("n", 0)
        type_label = f"{et} (n_train={train_n}, n_eval={eval_n})"

        print(f"  {type_label:<28s} | {tr:>12.4f} | {er:>12.4f} | {gap_str:>6s} | {status:<10s}")

    print(f"  {'─' * 28} | {'─' * 12} | {'─' * 12} | {'─' * 6} | {'─' * 10}")
    print(f"  {'OVERALL':<28s} | {train_overall:>12.4f} | {eval_overall:>12.4f} | "
          f"{overall_gap:+.4f} |{' OVERFIT' if overfit_flag else ' ok':<10s}")


def print_summary_table(rows: list[list[str]], headers: list[str]) -> None:
    """Print a formatted summary table."""
    col_widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            col_widths[i] = max(col_widths[i], len(cell))

    sep = "  " + "  ".join(["─" * w for w in col_widths])
    hdr = "  " + "  ".join(h.ljust(col_widths[i]) for i, h in enumerate(headers))
    print(hdr)
    print(sep)
    for row in rows:
        print("  " + "  ".join(cell.ljust(col_widths[i]) for i, cell in enumerate(row)))


# ── Degradation table ────────────────────────────────────────────────────────

@dataclass
class IterationSummary:
    iteration: int
    n_train: int
    n_eval: int
    wall_sec: float
    train_overall_recall: float
    eval_overall_recall: float
    gap: float
    overfit: bool
    per_type: dict[str, dict[str, float]]  # type -> {train_recall, eval_recall, gap}


# ── Main training/eval loop ──────────────────────────────────────────────────

async def main() -> None:
    print("=" * 90)
    print("  PIIFilter Adversarial Training/Eval Loop")
    print("  Detecting overfit: train recall - eval recall > 10% → OVERFIT")
    print("=" * 90)

    # 1. Load ALL available adversarial datasets
    all_examples = load_all_adversarial()

    if not all_examples:
        print("  ERROR: No adversarial examples loaded. Cannot run.")
        return

    # 2. Randomly split into training set (70%) and held-out eval set (30%)
    train_examples, eval_examples = random_split(all_examples, train_frac=0.7, seed=42)
    print(f"  Training set:   {len(train_examples)} examples")
    print(f"  Held-out eval:  {len(eval_examples)} examples")

    # Report entity-type distribution
    def count_types(examples: list[LabeledExample]) -> dict[str, int]:
        counts: dict[str, int] = defaultdict(int)
        for ex in examples:
            for ee in ex.entities:
                counts[ee["type"].upper()] += 1
        return dict(counts)

    train_type_counts = count_types(train_examples)
    eval_type_counts = count_types(eval_examples)
    all_types = sorted(set(train_type_counts) | set(eval_type_counts))
    print(f"\n  Entity type distribution:")
    for et in all_types:
        tc = train_type_counts.get(et, 0)
        ec = eval_type_counts.get(et, 0)
        print(f"    {et:<25s}: train={tc:>4d}  eval={ec:>4d}")

    # 3. Build pipeline detector once
    print(f"\n  Initializing pipeline detector...")
    pipeline = await make_pipeline_adapter()
    print(f"  Pipeline detector ready: {pipeline.name}")

    # 4. Iteration loop
    NUM_ITERATIONS = 10
    BATCH_SIZE = 50
    rng = random.Random(123)  # Fixed seed for reproducibility across runs

    summaries: list[IterationSummary] = []

    for it in range(1, NUM_ITERATIONS + 1):
        iter_start = time.monotonic()

        # Sample 50 examples from training set
        train_sample = rng.sample(train_examples, min(BATCH_SIZE, len(train_examples)))

        # Run on training sample
        train_per_type = await evaluate_on_subset(pipeline.detect_fn, train_sample)

        # Run on full held-out eval set
        eval_per_type = await evaluate_on_subset(pipeline.detect_fn, eval_examples)

        wall_sec = time.monotonic() - iter_start

        # Detect overfit
        train_recalls = compute_weighted_recall(train_per_type)
        eval_recalls = compute_weighted_recall(eval_per_type)
        overfit_types, degradation = detect_overfit(train_recalls, eval_recalls)

        # Compute overall
        train_total_tp = sum(c["tp"] for c in train_per_type.values())
        train_total_n = sum(c["n"] for c in train_per_type.values())
        eval_total_tp = sum(c["tp"] for c in eval_per_type.values())
        eval_total_n = sum(c["n"] for c in eval_per_type.values())
        train_overall = train_total_tp / train_total_n if train_total_n else 0.0
        eval_overall = eval_total_tp / eval_total_n if eval_total_n else 0.0
        gap = train_overall - eval_overall

        # Store summary
        per_type_summary: dict[str, dict[str, float]] = {}
        for et in sorted(set(train_recalls) | set(eval_recalls)):
            per_type_summary[et] = {
                "train_recall": round(train_recalls.get(et, 0.0), 4),
                "eval_recall": round(eval_recalls.get(et, 0.0), 4),
                "gap": round(degradation.get(et, 0.0), 4),
            }

        summaries.append(IterationSummary(
            iteration=it,
            n_train=len(train_sample),
            n_eval=len(eval_examples),
            wall_sec=wall_sec,
            train_overall_recall=round(train_overall, 4),
            eval_overall_recall=round(eval_overall, 4),
            gap=round(gap, 4),
            overfit=gap > 0.10,
            per_type=per_type_summary,
        ))

        # Print iteration table
        print_iteration_table(
            it, train_per_type, eval_per_type,
            overfit_types, degradation,
            len(train_sample), len(eval_examples), wall_sec,
        )

    # 5. Final degradation summary table
    print(f"\n{'=' * 90}")
    print("  DEGRADATION OVER ITERATIONS")
    print(f"{'=' * 90}")

    headers = ["Iter", "Train Recall", "Eval Recall", "Gap", "Overfit?", "Time(s)",
               "Overfit Types"]
    rows = []
    overfit_count = 0
    for s in summaries:
        # Find which types are overfit in this iteration
        overfit_types_str = ""
        overfit_types_list = [
            et for et, d in s.per_type.items()
            if d["gap"] > 0.10
        ]
        if overfit_types_list:
            overfit_types_str = ", ".join(overfit_types_list[:4])
            if len(overfit_types_list) > 4:
                overfit_types_str += f" +{len(overfit_types_list)-4} more"

        overfit_label = "YES ⚠️" if s.overfit else "no"
        if s.overfit:
            overfit_count += 1

        rows.append([
            str(s.iteration),
            f"{s.train_overall_recall:.4f}",
            f"{s.eval_overall_recall:.4f}",
            f"{s.gap:+.4f}",
            overfit_label,
            f"{s.wall_sec:.1f}s",
            overfit_types_str,
        ])

    print_summary_table(rows, headers)

    print(f"\n  Overfit detected in {overfit_count}/{NUM_ITERATIONS} iterations")

    # Analyze which types degrade most consistently
    print(f"\n{'─' * 90}")
    print("  CONSISTENTLY DEGRADING TYPES (average gap across iterations)")
    print(f"{'─' * 90}")

    # Collect average gap per type
    type_gaps: dict[str, list[float]] = defaultdict(list)
    for s in summaries:
        for et, d in s.per_type.items():
            type_gaps[et].append(d["gap"])

    type_avg_gap = []
    for et, gaps in type_gaps.items():
        avg_gap = sum(gaps) / len(gaps)
        max_gap = max(gaps)
        overfit_count_t = sum(1 for g in gaps if g > 0.10)
        type_avg_gap.append((et, avg_gap, max_gap, overfit_count_t, len(gaps)))

    type_avg_gap.sort(key=lambda x: -x[1])  # Sort by avg gap descending

    print(f"  {'Type':<25s} | {'Avg Gap':>8s} | {'Max Gap':>8s} | {'Overfit/Iters':>14s}")
    print(f"  {'─'*25} | {'─'*8} | {'─'*8} | {'─'*14}")
    for et, avg, mx, oc, niter in type_avg_gap:
        print(f"  {et:<25s} | {avg:>8.4f} | {mx:>8.4f} | {oc:>3d}/{niter:<9d}")

    # 6. Final verdict
    print(f"\n{'=' * 90}")
    print("  VERDICT")
    print(f"{'=' * 90}")
    if overfit_count == NUM_ITERATIONS:
        print(f"  ❌ Persistent overfit detected in ALL {NUM_ITERATIONS} iterations.")
        print(f"     The detector memorized training patterns without generalizing.")
        print(f"     Average overall gap: {sum(s.gap for s in summaries)/len(summaries):.4f}")
    elif overfit_count >= NUM_ITERATIONS // 2:
        print(f"  ⚠️  Frequent overfit detected ({overfit_count}/{NUM_ITERATIONS} iterations).")
        print(f"     Average overall gap: {sum(s.gap for s in summaries)/len(summaries):.4f}")
    elif overfit_count > 0:
        print(f"  ⚡ Occasional overfit detected ({overfit_count}/{NUM_ITERATIONS} iterations).")
        print(f"     Average overall gap: {sum(s.gap for s in summaries)/len(summaries):.4f}")
    else:
        print(f"  ✅ No overfit detected across {NUM_ITERATIONS} iterations.")
        print(f"     Average overall gap: {sum(s.gap for s in summaries)/len(summaries):.4f}")

    # Top degrading types
    if type_avg_gap:
        worst = type_avg_gap[0]
        print(f"\n  Most degrading type: {worst[0]} (avg gap={worst[1]:.4f}, "
              f"overfit in {worst[3]}/{worst[4]} iterations)")

    # Recommend action
    print(f"\n  Recommendation:")
    if overfit_count > 0:
        print(f"    - Add more diverse adversarial training data for degrading types")
        print(f"    - Apply regularization (dropout, weight decay) to pipeline detectors")
        print(f"    - Implement early stopping based on eval recall plateau")
        print(f"    - Review deobfuscation rules: are they too narrow for held-out patterns?")
    else:
        print(f"    - Good generalization — consider expanding adversarial coverage")

    print(f"\n{'=' * 90}\n")


if __name__ == "__main__":
    asyncio.run(main())