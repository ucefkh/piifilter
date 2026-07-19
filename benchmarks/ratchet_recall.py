#!/usr/bin/env python3
"""Ratchet recall gate — per-category floors at current values minus small margin,
staged progression to 0.95 global.

Design
------
- Each entity type (per detector) gets its own floor computed from the last
  reference benchmark run: floor = max(0.70, reference_recall - 0.10) for
  full recall, and similarly for real-only recall.
- If a type had < 5 samples in the reference run, its floor is set to 0.0
  (insufficient data to enforce).
- A global progression target is computed from the current stage:
    Stage 0 = 0.80          (same as previous fixed floor)
    Stage 1 = 0.85          (first ratchet)
    Stage 2 = 0.90          (second ratchet)
    Stage 3 = 0.95          (target)
- A pass requires ALL entity types (with >=5 reference samples) to meet
  both their per-category floor AND the current global stage target.
- The stage auto-advances when the current stage passes twice in a row.
- State (stage, history, reference floors) is persisted to a JSON file so
  the ratchet is monotonic and durable across CI runs.

Usage
-----
    # After a benchmark run that produced recall-results-heldout.json:
    python benchmarks/ratchet_recall.py                           # check + maybe advance
    python benchmarks/ratchet_recall.py --state ratchet-state.json # custom state path
    python benchmarks/ratchet_recall.py --force-stage 2            # manual override
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# ── Constants ────────────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_RESULTS = PROJECT_ROOT / "benchmarks" / "recall-results-heldout.json"
DEFAULT_STATE = PROJECT_ROOT / "benchmarks" / "ratchet-state.json"

# Margin subtracted from reference recall to compute the per-category floor
RECALL_MARGIN = 0.10
REAL_RECALL_MARGIN = 0.15

# Absolute minimum floors (never go below these)
ABS_MIN_RECALL_FLOOR = 0.70
ABS_MIN_REAL_RECALL_FLOOR = 0.50

# Minimum sample count to enforce a floor (below this: known-exception table)
MIN_SAMPLES_FOR_FLOOR = 5

# Stages: values are the global target for that stage
# Stage 0 starts at the previous fixed floor (0.80), then ramps up.
# The global target applies to ALL entity types with >= MIN_SAMPLES_FOR_FLOOR,
# independent of their per-category floor.  This means weak types pull the
# global target up gradually as they improve.
STAGES: list[float] = [0.80, 0.85, 0.90, 0.95]

# Passes needed at a stage before auto-advancing
PASSES_TO_ADVANCE = 2


# ── State management ─────────────────────────────────────────────────────────


def load_state(path: Path) -> dict[str, Any]:
    """Load ratchet state from file, or return defaults."""
    if path.exists():
        try:
            return json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return _default_state()


def _default_state() -> dict[str, Any]:
    return {
        "stage": 0,
        "consecutive_passes": 0,
        "reference_floors": {},  # {(detector, entity_type): {"recall": float, "real_recall": float, "n": int}}
        "history": [],           # list of {timestamp, stage, pass, summary}
    }


def save_state(state: dict[str, Any], path: Path) -> None:
    """Persist ratchet state to file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2))


# ── Floor computation ───────────────────────────────────────────────────────


def compute_per_category_floors(
    results: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    """Compute per-category recall floors from benchmark results.

    Returns a dict keyed by ``"{detector}:{entity_type}"`` with values:
        {"recall_floor": float, "real_recall_floor": float, "n": int}
    """
    floors: dict[str, dict[str, Any]] = {}
    for det_name, det_data in results.get("detectors", {}).items():
        per_type = det_data.get("per_type", {})
        for et, m in per_type.items():
            key = f"{det_name}:{et}"
            n = m.get("n", 0)
            recall = m.get("recall", 0.0)
            real_recall = m.get("real_recall", recall)

            if n < MIN_SAMPLES_FOR_FLOOR:
                # Not enough data — floor stays 0 (effectively no constraint)
                recall_floor = 0.0
                real_recall_floor = 0.0
            else:
                recall_floor = max(ABS_MIN_RECALL_FLOOR, recall - RECALL_MARGIN)
                real_recall_floor = max(ABS_MIN_REAL_RECALL_FLOOR, real_recall - REAL_RECALL_MARGIN)

            floors[key] = {
                "recall_floor": round(recall_floor, 4),
                "real_recall_floor": round(real_recall_floor, 4),
                "n": n,
                "reference_recall": recall,
                "reference_real_recall": real_recall,
            }
    return floors


# ── Check logic ──────────────────────────────────────────────────────────────


def check_recall(
    results: dict[str, Any],
    state: dict[str, Any],
) -> dict[str, Any]:
    """Check recall against per-category floors and global stage target.

    Returns a dict with:
        pass: bool
        detector_results: list[DetectorCheck]
        global_stage_target: float
        max_floor_target: float
        next_stage: int | None
        stage_advanced: bool
    """
    # 1. Use reference floors from state if available, otherwise compute fresh
    floors: dict[str, dict[str, Any]]
    if state.get("reference_floors") and not _results_are_refresh(results, state):
        # Use stored floors (don't re-anchor from a run that isn't authoritative)
        floors = state["reference_floors"]
    else:
        # This is an authoritative run — update reference floors
        floors = compute_per_category_floors(results)
        state["reference_floors"] = floors

    # 2. Compute global stage target
    stage = state.get("stage", 0)
    global_target = STAGES[stage] if stage < len(STAGES) else STAGES[-1]

    # 3. Check each detector/entity-type pair
    detector_results: list[dict[str, Any]] = []
    all_pass = True
    any_failures = False

    for det_name, det_data in results.get("detectors", {}).items():
        per_type = det_data.get("per_type", {})
        for et, m in sorted(per_type.items()):
            key = f"{det_name}:{et}"
            floor_info = floors.get(key, {})
            floor_n = floor_info.get("n", 0)

            recall = m.get("recall", 0.0)
            real_recall = m.get("real_recall", recall)

            recall_floor = floor_info.get("recall_floor", 0.0)
            real_recall_floor = floor_info.get("real_recall_floor", 0.0)

            # Per-category floor check
            recall_ok = recall >= recall_floor - 1e-9
            real_recall_ok = real_recall >= real_recall_floor - 1e-9

            # Global stage target check
            global_ok: bool = True
            if floor_n >= MIN_SAMPLES_FOR_FLOOR:
                global_ok = recall >= global_target - 1e-9

            pc_pass = recall_ok and real_recall_ok
            g_pass = global_ok
            overall_pass = pc_pass and g_pass

            if not overall_pass:
                any_failures = True

            entry = {
                "detector": det_name,
                "entity_type": et,
                "n": m.get("n", 0),
                "recall": recall,
                "real_recall": real_recall,
                "recall_floor": recall_floor,
                "real_recall_floor": real_recall_floor,
                "global_target": global_target if floor_n >= MIN_SAMPLES_FOR_FLOOR else None,
                "per_category_pass": pc_pass,
                "global_pass": g_pass or floor_n < MIN_SAMPLES_FOR_FLOOR,
                "pass": overall_pass or floor_n < MIN_SAMPLES_FOR_FLOOR,
                "skipped": floor_n < MIN_SAMPLES_FOR_FLOOR,
            }
            detector_results.append(entry)

    overall_pass = not any_failures

    # 4. Auto-advance logic
    stage_advanced = False
    next_stage: int | None = None

    if overall_pass:
        consecutive = state.get("consecutive_passes", 0) + 1
        state["consecutive_passes"] = consecutive

        if consecutive >= PASSES_TO_ADVANCE and stage < len(STAGES) - 1:
            # Advance to next stage
            state["stage"] = stage + 1
            state["consecutive_passes"] = 0
            stage_advanced = True
            next_stage = state["stage"] if state["stage"] < len(STAGES) - 1 else None
    else:
        state["consecutive_passes"] = 0

    return {
        "pass": overall_pass,
        "detector_results": detector_results,
        "global_stage_target": global_target,
        "current_stage": state.get("stage", 0),
        "consecutive_passes": state.get("consecutive_passes", 0),
        "next_stage": next_stage,
        "stage_advanced": stage_advanced,
        "any_failures": any_failures,
    }


def _results_are_refresh(results: dict[str, Any], state: dict[str, Any]) -> bool:
    """Heuristic: are these results meant to refresh the reference?
    
    We consider them a refresh if they come from the same benchmark
    configuration (held-out, dataset v2) as the reference run.
    Currently, we just return False (don't auto-refresh) — the user
    must pass --update-floors to explicitly re-anchor.
    """
    return False


# ── Console output ───────────────────────────────────────────────────────────


def print_check(result: dict[str, Any]) -> None:
    """Print a formatted check summary."""
    print("=" * 80)
    print("  PIIFilter Recall Ratchet Gate")
    print("=" * 80)

    stage = result["current_stage"]
    if stage < len(STAGES):
        stage_target = STAGES[stage]
        stage_label = f"Stage {stage} (target ≥ {stage_target})"
    else:
        stage_label = f"Stage {stage} (target ≥ {STAGES[-1]}, final)"
    print(f"  Current stage:    {stage_label}")
    print(f"  Global target:    ≥ {result['global_stage_target']:.4f}")
    print(f"  Consecutive passes: {result['consecutive_passes']} / {PASSES_TO_ADVANCE}")
    print()

    # Group by detector
    seen_detectors: dict[str, list[dict[str, Any]]] = {}
    for entry in result["detector_results"]:
        seen_detectors.setdefault(entry["detector"], []).append(entry)

    for det_name, entries in sorted(seen_detectors.items()):
        print(f"  ── {det_name.upper()} ──")
        for e in entries:
            label = "✓" if e["pass"] else "✗"
            if e["skipped"]:
                label = "~"

            recall_str = f"recall={e['recall']:.4f}"
            if not e["skipped"]:
                recall_str += f" (floor={e['recall_floor']:.2f})"
            real_str = f"real={e['real_recall']:.4f}"
            if not e["skipped"]:
                real_str += f" (floor={e['real_recall_floor']:.2f})"

            extra = ""
            if not e["pass"] and not e["skipped"]:
                if not e["per_category_pass"]:
                    extra += " [PC FAIL]"
                if not e["global_pass"]:
                    extra += f" [GLOBAL FAIL: {e['recall']:.4f} < {e['global_target']:.4f}]"

            print(f"    {label}  {e['entity_type']:20s}  "
                  f"{recall_str:30s}  {real_str:30s}"
                  f"{extra}")

        print()

    if result["stage_advanced"]:
        new_stage = result["current_stage"]
        new_target = STAGES[new_stage] if new_stage < len(STAGES) else STAGES[-1]
        print(f"  ★ STAGE ADVANCED to Stage {new_stage} (target ≥ {new_target})!")
        print()

    if result["any_failures"]:
        fail_count = sum(1 for e in result["detector_results"] if not e["pass"] and not e["skipped"])
        print(f"  ✗ FAIL: {fail_count} entity/detector pair(s) below their floor or target")
    else:
        print(f"  ✓ PASS: All entity types meet per-category floors and global target")
    print()


# ── Main ─────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="PIIFilter Recall Ratchet Gate — per-category floors with "
                    "staged progression to 0.95",
    )
    parser.add_argument(
        "--results", type=str, default=str(DEFAULT_RESULTS),
        help=f"Path to benchmark results JSON (default: {DEFAULT_RESULTS})",
    )
    parser.add_argument(
        "--state", type=str, default=str(DEFAULT_STATE),
        help=f"Path to ratchet state JSON (default: {DEFAULT_STATE})",
    )
    parser.add_argument(
        "--force-stage", type=int, default=None,
        help="Override the current stage (advanced use)",
    )
    parser.add_argument(
        "--reset", action="store_true",
        help="Reset ratchet state and re-compute floors from current results",
    )
    parser.add_argument(
        "--update-floors", action="store_true",
        help="Re-compute reference floors from the current benchmark results",
    )
    args = parser.parse_args()

    results_path = Path(args.results)
    state_path = Path(args.state)

    # Load benchmark results
    if not results_path.exists():
        print(f"FAIL: {results_path} not found — run benchmarks/recall.py --held-out 0.2 first")
        sys.exit(1)

    try:
        results = json.loads(results_path.read_text())
    except json.JSONDecodeError as e:
        print(f"FAIL: {results_path} is not valid JSON — {e}")
        sys.exit(1)

    if "detectors" not in results:
        print(f"FAIL: No 'detectors' key in {results_path}")
        sys.exit(1)

    # Load or init state
    if args.reset:
        state = _default_state()
    else:
        state = load_state(state_path)

    if args.force_stage is not None:
        if args.force_stage < 0 or args.force_stage >= len(STAGES):
            print(f"FAIL: --force-stage must be 0-{len(STAGES)-1}")
            sys.exit(1)
        state["stage"] = args.force_stage
        state["consecutive_passes"] = 0

    if args.update_floors:
        print("  Updating reference floors from current benchmark results...")
        state["reference_floors"] = compute_per_category_floors(results)

    # Check
    result = check_recall(results, state)

    # Print
    print_check(result)

    # Save state (always, so consecutive_passes and potential stage advance persist)
    save_state(state, state_path)

    # Exit code
    sys.exit(0 if result["pass"] else 1)


if __name__ == "__main__":
    main()