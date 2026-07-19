import re, sys, json
sys.path.insert(0, 'core/src')
sys.path.insert(0, 'plugins/detector-regex/src')
from piifilter_detector_regex.patterns import PATTERN_DEFS

text = "JWT: eyJzdW...IyfQ"
print("Text:", repr(text))

# Test each JWT pattern
for type_name, raw_pattern, score in PATTERN_DEFS:
    if type_name != 'JWT':
        continue
    print(f"\nPattern: {raw_pattern}")
    try:
        compiled = re.compile(raw_pattern, re.UNICODE)
        for m in compiled.finditer(text):
            print(f"  Match: span={m.start()}-{m.end()} val='{m.group()}'")
        else:
            pass
    except Exception as e:
        print(f"  ERROR: {e}")

# Also check: does the new pattern I added work?
print("\n--- Manual test ---")
p = r"\beyJ[a-zA-Z0-9_-]+\.\.\.[a-zA-Z0-9_-]+\b"
print(f"Pattern: {p}")
compiled = re.compile(p, re.UNICODE)
for m in compiled.finditer(text):
    print(f"  Match: span={m.start()}-{m.end()} val='{m.group()}'")

# Now try the full thing
print("\n--- Check what patterns.py actually has ---")
with open('plugins/detector-regex/src/piifilter_detector_regex/patterns.py') as f:
    content = f.read()
# Find JWT section
for line in content.split('\n'):
    if 'JWT' in line and 'r"' in line:
        print(repr(line.strip()))