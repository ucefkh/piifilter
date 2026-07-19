"""Check recall floor — per-category floors with staged ratchet to 0.95.
CI script.  Reads benchmarks/recall-results.json and runs the ratchet recall gate.

KNOWN EXCEPTIONS: Entity types that had <5 samples in the reference run are
skipped (insufficient data).  Entity types that pass per-category floors and
the global stage target pass.  See benchmarks/ratchet_recall.py for details.

Expected JSON structure:
  {
    "detectors": {
      "<detector_name>": {
        "per_type": {
          "<entity_type>": {"recall": <float>, "real_recall": <float>, "n": <int>, ...},
          ...
        }
      }
    }
  }
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
RESULTS_PATH = PROJECT_ROOT / "benchmarks" / "recall-results.json"
STATE_PATH = PROJECT_ROOT / "benchmarks" / "ratchet-state.json"


def main() -> None:
    if not RESULTS_PATH.exists():
        print(f"FAIL: {RESULTS_PATH} not found — run benchmarks/recall.py first")
        sys.exit(1)

    sys.path.insert(0, str(PROJECT_ROOT / "benchmarks"))
    from ratchet_recall import (
        load_state,
        save_state,
        compute_per_category_floors,
        check_recall,
        print_check,
    )

    # Load results
    try:
        results = json.loads(RESULTS_PATH.read_text())
    except json.JSONDecodeError as e:
        print(f"FAIL: {RESULTS_PATH} is not valid JSON — {e}")
        sys.exit(1)

    if "detectors" not in results:
        print(f"FAIL: No 'detectors' key in {RESULTS_PATH}")
        sys.exit(1)

    # Load state
    state = load_state(STATE_PATH)

    # If floors haven't been initialized, compute them from this run
    if not state.get("reference_floors"):
        print(f"  Initializing reference floors from {RESULTS_PATH.name}...")
        state["reference_floors"] = compute_per_category_floors(results)
        save_state(state, STATE_PATH)

    # Check
    result = check_recall(results, state)
    print_check(result)

    # Save state (consecutive_passes, stage advance)
    save_state(state, STATE_PATH)

    if not result["pass"]:
        fail_count = sum(
            1 for e in result["detector_results"]
            if not e["pass"] and not e["skipped"]
        )
        print(f"FAIL: {fail_count} entity/detector pair(s) below floor or target")

    sys.exit(0 if result["pass"] else 1)


if __name__ == "__main__":
    main()