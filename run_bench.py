#!/usr/bin/env python3
"""Run the PII detection recall benchmark."""
import sys
sys.path.insert(0, '.')

# Try importing benchmark runner
from tests.benchmark_runner import BenchmarkRunner
print("BenchmarkRunner imported OK")

# Run recall benchmark
runner = BenchmarkRunner()
results = runner.run_recall_benchmark()
print(json.dumps(results, indent=2)[:5000])