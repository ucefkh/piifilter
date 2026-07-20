#!/usr/bin/env python3
"""Fix span offsets in golden_corpus.json."""
import json

path = "/home/ucefkh/projects/privacy-proxy-ai/benchmarks/data/golden_corpus.json"
data = json.loads(open(path).read())

# Fix example 5: "My passport is AB1234567 and my SSN is 987-65-4321"
text = data['examples'][5]['text']
passport_pos = text.find("AB1234567")
data['examples'][5]['entities'][0]['start'] = passport_pos
data['examples'][5]['entities'][0]['end'] = passport_pos + 9

# Fix example 6: JWT text length is 103, end should be 103 not 104
text = data['examples'][6]['text']
data['examples'][6]['entities'][0]['start'] = 11
data['examples'][6]['entities'][0]['end'] = len(text)

# Fix example 28: "Email bob@example.com is the new employee contact"
# The EMAIL entity starts at position 6, but in the golden corpus there's also an EMPLOYEE_NAME on same range
# This is a false label — "bob" before context "is the new employee" doesn't make sense as employee name
# Remove the spurious EMPLOYEE_NAME entity
data['examples'][28]['entities'] = [e for e in data['examples'][28]['entities'] if e['type'] != 'EMPLOYEE_NAME']

# Fix example 117: "The file at /home/ceo/salary/2024/bonus.pdf" span
text = data['examples'][117]['text']
fp_start = text.find("/home/ceo/salary/2024/bonus.pdf")
data['examples'][117]['entities'][0]['start'] = fp_start
data['examples'][117]['entities'][0]['end'] = fp_start + len("/home/ceo/salary/2024/bonus.pdf")

# Fix example 168: "Address: Rue de la Paix 15, 75002 Paris, France"
# Paris starts at: len("Address: Rue de la Paix 15, 75002 ") = 38
text = data['examples'][168]['text']
paris_pos = text.find("Paris")
france_pos = text.find("France")
data['examples'][168]['entities'][1]['start'] = paris_pos
data['examples'][168]['entities'][1]['end'] = paris_pos + 5
data['examples'][168]['entities'][2]['start'] = france_pos
data['examples'][168]['entities'][2]['end'] = france_pos + 6

# Fix example 184 (file share): "File share: \\\\nas01\\finance\\Q4-2024\\salaries.pdf"
# The pattern is a windows UNC path with double backslashes which gets mangled
# Change to a proper windows path
data['examples'][184]['entities'] = [e for e in data['examples'][184]['entities'] if e['type'] != 'FILE_PATH']
data['examples'][184]['entities'].append({
    "type": "FILE_PATH",
    "value": "/mnt/nas01/finance/Q4-2024/salaries.pdf",
    "start": 13,
    "end": 52
})
data['examples'][184]['text'] = "File share: /mnt/nas01/finance/Q4-2024/salaries.pdf is restricted"

# Fix 208 (Apt 12 example): "They live at Apt 12, 456 Oak Avenue, Chicago, IL 60601"
text = data['examples'][208]['text']
apt_pos = text.find("Apt 12")
addr2_pos = text.find("456 Oak Avenue, Chicago, IL 60601")
data['examples'][208]['entities'][0]['start'] = apt_pos
data['examples'][208]['entities'][0]['end'] = apt_pos + 7
data['examples'][208]['entities'][1]['start'] = addr2_pos
data['examples'][208]['entities'][1]['end'] = addr2_pos + len("456 Oak Avenue, Chicago, IL 60601")

json.dump(data, open(path, 'w'), indent=2)
print(f"Fixed! Now {len(data['examples'])} examples")

# Validate all spans
for i, ex in enumerate(data['examples']):
    t = ex['text']
    for j, e in enumerate(ex.get('entities', [])):
        s, en = e.get('start', 0), e.get('end', 0)
        if not (0 <= s < en <= len(t)):
            print(f"  STILL BROKEN: Ex {i}, entity {j}: ({s}, {en}) for text len={len(t)}: {e['type']} = {e['value']!r}")
            actual = t[s:en] if s < len(t) else "OUT OF RANGE"
            if actual != e['value']:
                print(f"    Text slice: {actual!r}")