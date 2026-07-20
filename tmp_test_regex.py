"""Test the strip_inner_separators behavior on phone strings."""
import re

text = '+1-555-123-4567'
print(f'Input: {text!r}')
result = re.sub(r'(\d)[^\w\n]+(?=\d)', r'\1', text)
print(f'Output: {result!r}')

for m in re.finditer(r'(\d)[^\w\n]+(?=\d)', text):
    print(f'  Match: pos={m.start()}-{m.end()} val={m.group(0)!r} group1={m.group(1)!r}')