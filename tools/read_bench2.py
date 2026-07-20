import json
d = json.load(open('/tmp/bench_fix.json'))

# Show all types with any issue
issues = []
for et, s in sorted(d['per_type'].items()):
    mark = ''
    if s['n_golden'] == 0 and s['n_detected'] > 0:
        mark = ' FP_ONLY'
    if s['recall'] < 1.0 and s['n_golden'] > 0:
        mark += f' RECALL={s["recall"]}'
    if s['precision'] < 1.0 and s['n_detected'] > 0:
        mark += f' PRECISION={s["precision"]}'
    if mark:
        issues.append((et, s, mark))
        print(f'{et:25s}: {s}{mark}')

if not issues:
    print("All types perfect!")
    
print(f'\nOverall: {d["overall"]}')
print(f'F1 gate failed: {d["f1_gate_failed"]}')