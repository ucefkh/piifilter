import json
d = json.load(open('/tmp/bench_high.json'))
issues = []
for et, s in sorted(d['per_type'].items()):
    mark = ''
    if s['n_golden'] == 0 and s['n_detected'] > 0:
        mark = ' FP_ONLY'
    if s['recall'] < 1.0 and s['n_golden'] > 0:
        mark += f' RECALL={s["recall"]:.4f}'
    if s['precision'] < 1.0 and s['n_detected'] > 0:
        mark += f' PRECISION={s["precision"]:.4f}'
    if mark:
        print(f'{et:25s}: {mark}')
        print(f'  {s}')
if not issues:
    print("All types perfect in high_recall!")
print(f'\nOverall: tp={d["overall"]["tp"]} fp={d["overall"]["fp"]} fn={d["overall"]["fn"]} rec={d["overall"]["recall"]:.4f} prec={d["overall"]["precision"]:.4f}')