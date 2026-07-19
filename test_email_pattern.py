"""Test the current EMAIL pattern against edge cases."""
import re

current = re.compile(r'\b[\w.+*-]+@[\w-]+\.[\w.-]+\b', re.UNICODE)

# Test cases that the pattern should handle
test_emails = [
    ("user@example.com", True),
    ("user+tag@example.com", True),  # + tag
    ("user.name@example.com", True),  # dot in local
    ("user@sub.example.com", True),  # subdomain
    ("user@example.co.uk", True),  # multi-part TLD
    ("user@example.corporate", True),  # long TLD
    ("user@example.travel", True),  # long TLD
    ("user@example.museum", True),  # long TLD
    ("a@b.cd", True),  # minimal email
    ("user-name@example.org", True),  # hyphen
    ("user_name@example.org", True),  # underscore
    ("a.b+c@example.co.nz", True),  # combined
    ("user@example.company", True),  # new gTLD
    ("user@my-host.example.com", True),  # hyphen in domain
]

print("Testing current pattern against edge cases:")
print(f"Pattern: {current.pattern}")
print()
for email, expected in test_emails:
    result = bool(current.search(email))
    status = "PASS" if result == expected else "FAIL"
    print(f"  [{status}] {email:45s} -> {result} (expected {expected})")

# Now let me think about what's actually causing the 27 FNs
# The benchmark's held-out split is stratified but random. 
# With 35 total EMAIL FNs in the full set, 20% held-out would get ~7 on average.
# But the report says 27 FNs in held-out. That means the FN count is per-entity-instance, not per-unique-pattern.
# Wait - the held-out is stratified by rarest entity type, so it could oversample EMAIL-heavy examples.
# Actually looking at the counts: 193 EMAIL entities in test set, 27 FNs → recall 0.860.
# 166 TP + 27 FN = 193. With 538 total EMAIL entities in dataset, 20% = ~108 expected in test.
# But we got 193 - meaning the stratified split over-sampled EMAIL examples.

# Let me count how many of the 35 FNs would be caught if we improved the pattern
# For the HTML redirects (&#046; cases), there's nothing the pattern can do.
# The deobfuscator needs to handle &#046 differently.

# Let's see if we can improve the deobfuscator for &#046 -> @ in email context
print()
print("All 35 FNs require deobfuscator improvements, not pattern changes")
print("Current pattern already handles: + tags, long TLDs, subdomains")