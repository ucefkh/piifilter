#!/usr/bin/env python3
import json
data = json.load(open("benchmarks/recall-results-heldout-arb.json"))
per_type = data["detectors"]["regex"]["per_type"]
for t, v in sorted(per_type.items()):
    r = v["recall"]
    p = v["precision"]
    marker = "*** " if r < 0.95 or p < 0.85 else ""
    print(f'{marker}{t:25s} recall={r:.4f} precision={p:.4f} f1={v["f1"]:.4f} n={v["n"]}')