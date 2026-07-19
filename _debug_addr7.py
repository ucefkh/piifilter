import re

# Pattern from line 170
p170 = re.compile(r"\b\d{1,5}\s+(?:[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})\s+(?:St(?:reet)?|Ave(?:nue)?|Dr(?:ive)?|Rd|Road|Blvd|Boulevard|Ln|Lane|Way|Ct|Court|Pl|Place|Cir(?:cle)?|Pkwy|Parkway)\b")
# Pattern from line 174
p174 = re.compile(r"\b\d{1,3}\s+(?:[A-Z][a-z]+)\s+(?:Street|Road|Lane|Drive|Way|Close|Gardens|Hill|Square|Mews|Court|Avenue)\b")

tests = [
    "350 Fifth Avenue",
    "10 Downing Street",
    "123 Maple Drive",
    "123 Main Street",
    "42 Wallaby Way",
    "123 Main St",
]

for t in tests:
    m170 = p170.search(t)
    m174 = p174.search(t)
    print(f'{t:30s} → line170: {bool(m170)} line174: {bool(m174)}')