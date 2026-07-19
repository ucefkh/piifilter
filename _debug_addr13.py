import json, re

data = json.loads(open('benchmarks/data/pii_dataset.json').read())
examples = data['examples']

# Current pattern
p170 = re.compile(r"\b\d{1,5}\s+(?:[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})\s+(?:St(?:reet)?|Ave(?:nue)?|Dr(?:ive)?|Rd|Road|Blvd|Boulevard|Ln|Lane|Way|Ct|Court|Pl|Place|Cir(?:cle)?|Pkwy|Parkway)\b")

# New keyword-prefixed version — match includes the keyword
# Keywords: "at ", "address: ", "address ", "is at ", "office is at ", "home address: ", "visit us at "
# Make each alternative capture from keyword through street
keywords = [
    r"at\s+",
    r"address:\s*",
    r"address\s+",
    r"is\s+at\s+",
    r"office\s+is\s+at\s+",
    r"Home\s+address:\s+",
    r"home\s+address:\s+",
    r"Visit\s+us\s+at\s+",
    r"HQ\s+is\s+at\s+",
    r"mailing\s+address:\s+",
]
kw_group = "|".join(keywords)
new_pat = re.compile(r"(?:" + kw_group + r")(\b\d{1,5}\s+(?:[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})\s+(?:St(?:reet)?|Ave(?:nue)?|Dr(?:ive)?|Rd|Road|Blvd|Boulevard|Ln|Lane|Way|Ct|Court|Pl|Place|Cir(?:cle)?|Pkwy|Parkway)\b)")

for i, ex in enumerate(examples):
    for ee in ex.get('entities', []):
        if ee['type'] == 'ADDRESS':
            text = ex['text']
            # Check current pattern
            m_cur = p170.search(text)
            m_new = new_pat.search(text)
            
            exp_start, exp_end = ee['start'], ee['end']
            
            matched_cur = m_cur is not None
            matched_new = m_new is not None
            
            if matched_new:
                new_start = m_new.start()
                new_end = m_new.end()
                intersection = max(0, min(new_end, exp_end) - max(new_start, exp_start))
                my_len = new_end - new_start
                exp_len = exp_end - exp_start
                smallest = min(my_len, exp_len)
                iou = intersection / smallest if smallest > 0 else 0
                iou_ok = iou >= 0.5
                print(f'Ex {i}: cur={matched_cur} new={matched_new} iou={iou:.2f} {"✓" if iou_ok else "✗"} | new starts at {new_start} (expected {exp_start}) | match="{m_new.group()}"')
            else:
                print(f'Ex {i}: cur={matched_cur} new={matched_new} ✗ MISSED | "{ee["value"]}"')

# Also check FPs
print("\n=== FP check ===")
for i in [95, 101]:
    ex = examples[i]
    text = ex['text']
    m_new = new_pat.search(text)
    print(f'Ex {i}: new_pat matched={bool(m_new)}')
    if m_new:
        print(f'  "{m_new.group()}"')