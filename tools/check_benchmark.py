"""Run benchmark and check what's below 1.0."""
import subprocess, json, sys

result = subprocess.run(
    [sys.executable, 'tests/benchmark_runner.py', '--mode', 'balanced', '--json'],
    capture_output=True, text=True, cwd='/home/ucefkh/projects/privacy-proxy-ai'
)
d = json.loads(result.stdout)
for et, stats in sorted(d['per_type'].items()):
    if stats['n_golden'] > 0 or stats['tp'] > 0 or stats['fp'] > 0:
        if stats['recall'] < 1.0 or stats['precision'] < 1.0:
            print(f'{et:25s} recall={stats["recall"]:.4f} precision={stats["precision"]:.4f} tp={stats["tp"]} fp={stats["fp"]} fn={stats["fn"]} n_gold={stats["n_golden"]}')
print(f'\nOverall: {d["overall"]}')
print(f'Failed: {d["f1_gate_failed"]}')