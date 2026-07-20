#!/usr/bin/env python3
"""PIIFilter F1 CI Gate — exits with 1 if F1 drops below threshold.

Designed to run in CI after a benchmark run. Checks that F1 scores
for all entity types meet or exceed a minimum threshold. The gate
can be configured to use different mode presets.

Usage:
    uv run python tests/f1_ci_gate.py                              # default balanced mode
    uv run python tests/f1_ci_gate.py --mode high_recall            # loose gate
    uv run python tests/f1_ci_gate.py --mode high_precision         # strict gate
    uv run python tests/f1_ci_gate.py --min-f1 0.80 --mode balanced
    uv run python tests/f1_ci_gate.py --output results.json         # save detailed results
    uv run python tests/f1_ci_gate.py --update-ratchet              # auto-anchor at current scores
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# ── Import benchmark runner module ──────────────────────────────────────────
sys.path.insert(0, str(PROJECT_ROOT))
from tests.benchmark_runner import (
    MODE_PRESETS,
    _normalize_entity,
    get_threshold,
    load_golden_corpus,
    score_detections,
    detect_via_detector,
    RegexDetector,
)
import asyncio


# ── Default thresholds per mode for F1 gate ─────────────────────────────────
# These are the MINIMUM F1 scores required per entity type per mode.
# If a type's data is insufficient (< MIN_SAMPLES), it's exempted.
MIN_SAMPLES = 3  # minimum golden examples to enforce the F1 floor

F1_FLOORS: dict[str, dict[str, float]] = {
    "high_recall": {
        "default": 0.70,
    },
    "balanced": {
        "default": 0.80,
        # Some types are inherently harder — lower floor
        "CITY": 0.60,
        "COMPANY": 0.60,
        "CUSTOMER_NAME": 0.60,
        "EMPLOYEE_NAME": 0.60,
        "PROJECT_NAME": 0.60,
        "COUNTRY": 0.60,
        "DOMAIN": 0.70,
        "PERSON": 0.70,
    },
    "high_precision": {
        "default": 0.85,
    },
}

F1_RATCHET_PATH = PROJECT_ROOT / "benchmarks" / "f1-ratchet-state.json"


def _load_ratchet() -> dict[str, dict[str, float]]:
    """Load the F1 ratchet state (per-entity-type reference F1 floors)."""
    if F1_RATCHET_PATH.exists():
        try:
            return json.loads(F1_RATCHET_PATH.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _save_ratchet(state: dict[str, dict[str, float]]) -> None:
    """Save the F1 ratchet state."""
    F1_RATCHET_PATH.parent.mkdir(parents=True, exist_ok=True)
    F1_RATCHET_PATH.write_text(json.dumps(state, indent=2))


def get_f1_floor(mode: str, entity_type: str) -> float:
    """Get the F1 floor for an entity type in the given mode.

    Priority: ratchet state > mode-specific > mode default > 0.70
    """
    # Check ratchet state first (historical best-known floors)
    ratchet = _load_ratchet()
    ratchet_key = f"{mode}:{entity_type}"
    if ratchet_key in ratchet:
        return ratchet[ratchet_key]

    # Fall back to static floors
    mode_floors = F1_FLOORS.get(mode, F1_FLOORS["balanced"])
    return mode_floors.get(entity_type, mode_floors.get("default", 0.80))


def update_ratchet(
    per_type_results: dict[str, dict[str, Any]],
    mode: str,
) -> dict[str, dict[str, float]]:
    """Update the ratchet state with current results (only if they improve).

    The ratchet is monotonic: it only moves upward. If a type's current
    F1 is higher than the stored reference, the reference is updated.
    """
    ratchet = _load_ratchet()
    changed = False
    for et, m in per_type_results.items():
        if m["n_golden"] < MIN_SAMPLES:
            continue
        key = f"{mode}:{et}"
        current_f1 = m["f1"]
        stored = ratchet.get(key, 0.0)
        if current_f1 > stored:
            ratchet[key] = current_f1
            changed = True
            print(f"  ★ Ratchet updated: {et}: {stored:.4f} → {current_f1:.4f}")
    if changed:
        _save_ratchet(ratchet)
        print(f"  Ratchet state saved to {F1_RATCHET_PATH}")
    else:
        print("  No ratchet improvements.")
    return ratchet


# ── Main ──────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="PIIFilter F1 CI Gate — fails build if F1 drops below threshold",
    )
    parser.add_argument(
        "--corpus", type=str,
        default=str(PROJECT_ROOT / "benchmarks" / "data" / "golden_corpus.json"),
        help="Path to golden corpus JSON",
    )
    parser.add_argument(
        "--mode", type=str, default="balanced",
        choices=list(MODE_PRESETS.keys()),
        help="Mode preset (default: balanced)",
    )
    parser.add_argument(
        "--min-f1", type=float, default=None,
        help="Override minimum F1 for ALL entity types (overrides mode defaults)",
    )
    parser.add_argument(
        "--output", type=str, default=None,
        help="Write detailed results JSON to this path",
    )
    parser.add_argument(
        "--update-ratchet", action="store_true",
        help="Update the F1 ratchet state with current results (monotonic increase only)",
    )
    parser.add_argument(
        "--threshold", type=float, default=None,
        help="Confidence threshold override (passed to benchmark_runner)",
    )
    args = parser.parse_args()

    print("=" * 80)
    print("  PIIFilter F1 CI Gate")
    print("=" * 80)
    print(f"  Mode:      {args.mode}")
    print(f"  Corpus:    {args.corpus}")
    print(f"  Min F1:    {args.min_f1 or '(per-type floors)'}")
    print()

    # 1. Load corpus
    examples = load_golden_corpus(Path(args.corpus))
    print(f"  Loaded {len(examples)} examples from golden corpus")

    # 2. Initialize detector
    detector = RegexDetector()
    asyncio.run(detector.initialize())

    # 3. Run detection on each example
    all_golden: list[dict[str, Any]] = []
    all_detected: list[dict[str, Any]] = []

    for ex in examples:
        text = ex["text"]
        golden = ex.get("entities", [])
        detected = detect_via_detector(text, detector)
        normalized = [_normalize_entity(d) for d in detected]
        all_golden.extend(golden)
        all_detected.extend(normalized)

    # 4. Score per entity type with mode-appropriate thresholds
    entity_types = sorted({e["type"] for e in all_golden} | {e["type"] for e in all_detected})
    per_type: dict[str, dict[str, Any]] = {}
    for et in entity_types:
        et_threshold = get_threshold(args.mode, et, args.threshold)
        per_type[et] = score_detections(
            all_golden, all_detected, entity_type=et, threshold=et_threshold,
        )

    # 5. Update ratchet if requested
    if args.update_ratchet:
        update_ratchet(per_type, args.mode)

    # 6. Check F1 gate
    failures: list[tuple[str, float, float]] = []

    for et, m in sorted(per_type.items()):
        if m["n_golden"] < MIN_SAMPLES:
            print(f"  ~ {et:25s}  F1={m['f1']:.4f}  (skipped: only {m['n_golden']} golden examples)")
            continue

        f1_floor = args.min_f1 if args.min_f1 is not None else get_f1_floor(args.mode, et)
        current_f1 = m["f1"]

        if current_f1 < f1_floor - 0.0001:
            failures.append((et, current_f1, f1_floor))
            print(f"  ✗ {et:25s}  F1={current_f1:.4f}  (required >= {f1_floor:.2f})")
        else:
            print(f"  ✓ {et:25s}  F1={current_f1:.4f}  (floor={f1_floor:.2f})")

    # 7. Overall
    print()
    if failures:
        print(f"  ✗ FAILED: {len(failures)} entity type(s) below F1 floor:")
        for et, cf, ff in failures:
            print(f"      {et}: F1={cf:.4f} < {ff:.2f}")
        print()
        # Write results even on failure for debugging
        if args.output:
            _write_output(args.output, per_type, failures)
        sys.exit(1)
    else:
        print("  ✓ PASSED: All entity types meet F1 requirements")
        if args.output:
            _write_output(args.output, per_type, failures)
        sys.exit(0)


def _write_output(path: str, per_type: dict, failures: list) -> None:
    """Write detailed results to a JSON file."""
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps({
        "per_type": {
            k: {
                "n_golden": v["n_golden"],
                "n_detected": v["n_detected"],
                "tp": v["tp"],
                "fp": v["fp"],
                "fn": v["fn"],
                "precision": v["precision"],
                "recall": v["recall"],
                "f1": v["f1"],
            }
            for k, v in per_type.items()
        },
        "failures": [(et, cf, ff) for et, cf, ff in failures],
        "passed": len(failures) == 0,
    }, indent=2))
    print(f"  Results written to {output_path}")


if __name__ == "__main__":
    main()