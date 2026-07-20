import json
d = json.load(open('/tmp/bench_new.json'))

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
        print(f'{et:25s}: n_gold={s["n_golden"]} n_det={s["n_detected"]} tp={s["tp"]} fp={s["fp"]} fn={s["fn"]} prec={s["precision"]} rec={s["recall"]}{mark}')

if not issues:
    print("All types perfect!")
    
print(f'\nOverall: tp={d["overall"]["tp"]} fp={d["overall"]["fp"]} fn={d["overall"]["fn"]} rec={d["overall"]["recall"]} prec={d["overall"]["precision"]}')
print(f'F1 gate failed: {d["f1_gate_failed"]}')