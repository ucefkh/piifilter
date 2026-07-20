import json
d = json.load(open('/tmp/bench_out.json'))
ssn = d['per_type'].get('SOCIAL_SECURITY', {})
masked = d['per_type'].get('MASKED_SSN', {})
print('SOCIAL_SECURITY:', ssn)
print('MASKED_SSN:', masked)
print('Overall:', d['overall'])

# Show all types with issues
for et, s in sorted(d['per_type'].items()):
    if s['precision'] < 1.0 or s['recall'] < 1.0:
        print(f'  ISSUE: {et}: {s}')