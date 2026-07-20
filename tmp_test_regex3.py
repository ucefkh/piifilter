"""Verify the actual output character by character."""
import re

text = '+1-555-123-4567'
result = re.sub(r'(\d)[^\w\n]+(?=\d)', r'\1', text)

print(f"Input:  {text!r}        len={len(text)}")
print(f"Output: {result!r}       len={len(result)}")
print(f"Chars: ", [c for c in result])

# Why does this break phone detection?
# The phone pattern `\+1-\d{3}-\d{3}-\d{4}` won't match `+15551234567` anymore!
# But the question is: what phone patterns ARE being used here?

# The URL-encoded phone was %2B1-555-123-4567
# After URL decode: +1-555-123-4567 (on text_for_gps, pre-strip)
# After strip: +15551234567 (on stripped text)

# The pre-strip phone patterns should catch it as:
# International with + and unicode dashes: \+1-\d{3}-\d{3}-\d{4}
# Let's check:
text_gps = '+1-555-123-4567'
phone_pat = re.compile(r"(?:^|\s)\+\d{1,3}[–—−\-\. ]\d{2,4}[–—−\-\. ]\d{3,4}[–—−\-\. ]\d{4}\b")
m = phone_pat.search(text_gps)
print(f"\nPre-strip pattern match on {text_gps!r}: {m}")
if m:
    print(f"  Match: {m.group(0)!r} at {m.start()}-{m.end()}")

# Hmm, the problem is the pre-strip pattern has (?:^|\s) but +1-555... doesn't start with space or ^
# Let me check +1-555-123-4567 in the context
full = 'URL-encoded phone: +1-555-123-4567'
m2 = phone_pat.search(full)
print(f"\nPre-strip pattern match on full: {m2}")
if m2:
    print(f"  Match: {m2.group(0)!r} at {m2.start()}-{m2.end()}")