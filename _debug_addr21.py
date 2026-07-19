import re

text = "The address is at 42 Wallaby Way, Sydney (famous from Finding Nemo)"

# Pattern from the file (after edit) - both patterns
p_kw = re.compile(r"(?:address:\s*|at\s+|is\s+at\s+|office\s+is\s+at\s+|Home\s+address:\s+|home\s+address:\s+|Visit\s+us\s+at\s+|HQ\s+is\s+at\s+)(\b\d{1,5}\s+(?:[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})\s+(?:St(?:reet)?|Ave(?:nue)?|Dr(?:ive)?|Rd|Road|Blvd|Boulevard|Ln|Lane|Way|Ct|Court|Pl|Place|Cir(?:cle)?|Pkwy|Parkway))(?![,.]?\s*(?:\w+\s+){0,5}\([^)]*(?:famous|from\s+(?:movie|show|film|Finding|the\s+[A-Z])))\b")

p_standalone = re.compile(r"\b\d{1,5}\s+(?:[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})\s+(?:St(?:reet)?|Ave(?:nue)?|Dr(?:ive)?|Rd|Road|Blvd|Boulevard|Ln|Lane|Way|Ct|Court|Pl|Place|Cir(?:cle)?|Pkwy|Parkway)(?![,.]?\s*(?:\w+\s+){0,5}\([^)]*(?:famous|from\s+(?:movie|show|film|Finding|the\s+[A-Z])))\b")

print("Keyword-prefixed:")
for m in p_kw.finditer(text):
    print(f'  "{m.group()}" at {m.start()}-{m.end()}')

print("Standalone:")
for m in p_standalone.finditer(text):
    print(f'  "{m.group()}" at {m.start()}-{m.end()}')