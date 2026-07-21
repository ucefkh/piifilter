"""Find exact texts for FP names"""
import json
with open('/home/ucefkh/projects/privacy-proxy-ai/benchmarks/data/ood_corpus_v1.json') as f:
    data = json.load(f)

for ex in data['examples']:
    text = ex['text']
    # Check if it contains Yuki, Thabo, Mei, Fatima, Hiroshi, Ingrid, Bjorn, Raj, Subdomain
    for name in ['Yuki', 'Thabo', 'Mei', 'Fatima', 'Hiroshi', 'Ingrid', 'Bjorn', 'Raj', 'Subdomain']:
        if name in text:
            need_person = any(e['type'] == 'PERSON' for e in ex.get('entities', []))
            print(f'{name}: PERSON={need_person}: {text}')