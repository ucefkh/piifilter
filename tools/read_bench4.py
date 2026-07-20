import json
d = json.load(open('/tmp/bench_fixed2.json'))
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
        print(f'{et:25s}: {mark}')
        print(f'  {s}')
if not issues:
    print("All types perfect!")
print(f'\nOverall: {d["overall"]}')