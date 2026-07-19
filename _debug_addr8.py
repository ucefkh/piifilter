import re

text = "My street is 123 Main Street, not 123 Main St."
p170 = re.compile(r"\b\d{1,5}\s+(?:[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})\s+(?:St(?:reet)?|Ave(?:nue)?|Dr(?:ive)?|Rd|Road|Blvd|Boulevard|Ln|Lane|Way|Ct|Court|Pl|Place|Cir(?:cle)?|Pkwy|Parkway)\b")
p174 = re.compile(r"\b\d{1,3}\s+(?:[A-Z][a-z]+)\s+(?:Street|Road|Lane|Drive|Way|Close|Gardens|Hill|Square|Mews|Court|Avenue)\b")

for name, p in [('line170', p170), ('line174', p174)]:
    for m in p.finditer(text):
        print(f'{name}: "{m.group()}" start={m.start()} end={m.end()}')