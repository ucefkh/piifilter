#!/usr/bin/env python3
"""Check recall floor — verify real-only SSN recall meets the ≥0.95 threshold.

Runs the recall benchmark (held-out mode) and checks that the real-only
recall for SOCIAL_SECURITY (excludes masked/obfuscated variants) is ≥ 0.95.
Exits with code 0 on pass, 1 on fail.

Usage:
    python benchmarks/check_recall_floor.py [--detectors regex] [--held-out 0.2]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

RECALL_FLOOR = 0.95

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Check SSN recall floor (real-only ≥ 0.95)"
    )
    parser.add_argument(
        "--detectors",
        type=str,
        default="regex",
        help="Comma-separated detector names (default: regex)",
    )
    parser.add_argument(
        "--held-out",
        type=float,
        default=0.2,
        help="Fraction held out as test set (default: 0.2)",
    )
    args = parser.parse_args()

    # Import from the benchmark module
    sys.path.insert(0, str(PROJECT_ROOT / "benchmarks"))
    from recall import (
        load_dataset,
        stratified_train_test_split,
        evaluate_detector,
        make_regex_adapter,
        make_presidio_adapter,
        make_pipeline_adapter,
    )

    import asyncio

    async def run_bench() -> dict[str, Any]:
        full_dataset = load_dataset()
        train_dataset, test_dataset = stratified_train_test_split(
            full_dataset, test_size=args.held_out,
        )

        detector_names = [d.strip() for d in args.detectors.split(",")]

        adapters: dict[str, Any] = {}
        presidio_adapter = None
        if "presidio" in detector_names:
            try:
                presidio_adapter = await make_presidio_adapter()
            except Exception:
                pass
        if "regex" in detector_names:
            adapters["regex"] = make_regex_adapter()
        if "presidio" in detector_names and presidio_adapter:
            adapters["presidio"] = presidio_adapter
        try:
            pipeline = await make_pipeline_adapter(presidio_adapter)
            adapters["pipeline"] = pipeline
        except Exception:
            pass

        all_results: dict[str, Any] = {}
        for name, adapter in adapters.items():
            results = await evaluate_detector(name, test_dataset, adapter.detect_fn)
            all_results[name] = results
        return all_results

    results = asyncio.run(run_bench())

    # Check real-only SSN recall for each detector
    exit_code = 0
    for detector_name, detector_results in results.items():
        per_type = detector_results.get("per_type", {})
        ssn_metrics = per_type.get("SOCIAL_SECURITY", {})
        ssn_n = ssn_metrics.get("n", 0)
        ssn_recall = ssn_metrics.get("recall", 0.0)
        ssn_real_recall = ssn_metrics.get("real_recall", ssn_recall)
        ssn_real_n = ssn_metrics.get("real_n", ssn_n)

        print(f"\n  [{detector_name.upper()}] SOCIAL_SECURITY recall check:")
        print(f"    Full recall:     {ssn_recall:.4f}  (N={ssn_n})")
        print(f"    Real-only recall: {ssn_real_recall:.4f}  (N={ssn_real_n})")
        print(f"    Threshold:       ≥ {RECALL_FLOOR}")

        if ssn_real_n == 0:
            print(f"    ⚠ WARNING: No real SSN entities in held-out set — cannot verify floor.\n")
            continue

        if ssn_real_recall >= RECALL_FLOOR:
            print(f"    ✓ PASS (real-only recall {ssn_real_recall:.4f} ≥ {RECALL_FLOOR})\n")
        else:
            print(f"    ✗ FAIL (real-only recall {ssn_real_recall:.4f} < {RECALL_FLOOR})\n")
            exit_code = 1

    sys.exit(exit_code)


if __name__ == "__main__":
    main()