"""Test strip inner separators."""
import re
text = '+1-555-123-4567'
pat = re.compile(r'(\d)[^\w\n]+(?=\d)')

# Find all matches
for m in pat.finditer(text):
    print(f"Match: {m.start()}-{m.end()} value={m.group(0)!r} g1={m.group(1)!r}")

result = pat.sub(r'\1', text)
print(f"\nInput:  {text!r}")
print(f"Output: {result!r}")
print(f"Length: {len(text)} -> {len(result)}")

# Now see which chars changed
for i in range(len(text)):
    c = text[i]
    if i < len(result):
        r = result[i]
        if c != r:
            print(f"  pos {i}: '{c}' -> '{r}'")
    else:
        print(f"  pos {i}: '{c}' -> <deleted>")
if len(result) > len(text):
    for i in range(len(text), len(result)):
        print(f"  pos {i}: <added> '{result[i]}'")