#!/usr/bin/env python3
"""Check recall floor — per-category floors with staged ratchet to 0.95.

Reads benchmarks/recall-results.json (or --results file) and runs the
ratchet recall gate.  Exits with 0 on pass, 1 on fail.

Usage:
    python benchmarks/check_recall_floor.py
    python benchmarks/check_recall_floor.py --results recall-results-heldout.json
    python benchmarks/check_recall_floor.py --state ratchet-state.json --update-floors
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Check recall floor via ratchet gate (per-category floors → 0.95)",
    )
    parser.add_argument(
        "--results", type=str,
        default=str(PROJECT_ROOT / "benchmarks" / "recall-results.json"),
        help="Path to recall results JSON",
    )
    parser.add_argument(
        "--state", type=str,
        default=str(PROJECT_ROOT / "benchmarks" / "ratchet-state.json"),
        help="Path to ratchet state JSON",
    )
    parser.add_argument(
        "--update-floors", action="store_true",
        help="Re-compute reference floors from current results",
    )
    parser.add_argument(
        "--reset", action="store_true",
        help="Reset ratchet state",
    )
    parser.add_argument(
        "--force-stage", type=int, default=None,
        help="Override current stage",
    )
    args = parser.parse_args()

    # Delegate to ratchet_recall module
    sys.path.insert(0, str(PROJECT_ROOT / "benchmarks"))
    from ratchet_recall import main as ratchet_main

    # Build argv for ratchet_main
    ratchet_argv = ["ratchet_recall.py"]
    ratchet_argv.extend(["--results", args.results])
    ratchet_argv.extend(["--state", args.state])
    if args.update_floors:
        ratchet_argv.append("--update-floors")
    if args.reset:
        ratchet_argv.append("--reset")
    if args.force_stage is not None:
        ratchet_argv.extend(["--force-stage", str(args.force_stage)])

    sys.argv = ratchet_argv
    try:
        ratchet_main()
    except SystemExit as e:
        sys.exit(e.code)


if __name__ == "__main__":
    main()