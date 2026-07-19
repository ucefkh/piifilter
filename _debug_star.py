#!/usr/bin/env python3
"""Debug specific star-obfuscation edge cases."""
import re
pattern = re.compile(r"\b[\w.+-*]+@[\w-]+\.[\w.-]+\b", re.UNICODE)
pattern2 = re.compile(r"[\w.+-*]+@[\w-]+\.[\w.-]+", re.UNICODE)

cases = [
    "j**n@example.com",
    "s***t@company.com",
    "e**********n@bigpharma.com",
    "d***a@temp-services.co.uk",
    "t***k@techcorp.dev",
    "h***z@startup.io",
    "m***a@co.jp",
    "f***e@mail-server.co.jp",
    "a*******e@temp-services.co.uk",
    "b********s@company.org",
    "j**********r@startup.io",
    "s**********r@startup.io",
    "t*********s@example.com",
    "j***n@example.com",
    "j**n@example.com",  # double star
]

print(f"{'Pattern':<35} {'Result':<40}")
print("=" * 80)
for case in cases:
    m = pattern.search(case)
    result = m.group() if m else "NO MATCH"
    print(f"{case:<35} {result:<40}")
    
print()
print("Without \\b:")
for case in cases:
    m = pattern2.search(case)
    result = m.group() if m else "NO MATCH"
    print(f"{case:<35} {result:<40}")