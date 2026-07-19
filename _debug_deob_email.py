#!/usr/bin/env python3
"""Debug deobfuscator + new email pattern."""
import sys, re, os
os.chdir("/home/ucefkh/projects/privacy-proxy-ai")
sys.path.insert(0, "core/src")
sys.path.insert(0, "plugins/detector-regex/src")
from piifilter.shared.deobfuscator import Deobfuscator

deob = Deobfuscator()
pattern = re.compile(r"\b[\w.+*-]+@[\w-]+\.[\w.-]+\b", re.UNICODE)
# Read patterns from file
from piifilter_detector_regex.patterns import PATTERN_DEFS
email_patterns = [(name, re.compile(p, re.UNICODE), s) for name, p, s in PATTERN_DEFS if name == "EMAIL"]
print(f"Loaded {len(email_patterns)} EMAIL patterns")

tests = [
    # Star obfuscation
    ("j**n@example.com", "j**n@example.com"),
    ("s***t@company.com", "s***t@company.com"),
    ("e**********n@bigpharma.com", "e**********n@bigpharma.com"),
    ("d***a@temp-services.co.uk", "d***a@temp-services.co.uk"),
    ("t***k@techcorp.dev", "t***k@techcorp.dev"),
    ("h***z@startup.io", "h***z@startup.io"),
    ("m***a@co.jp", "m***a@co.jp"),
    ("f***e@mail-server.co.jp", "f***e@mail-server.co.jp"),
    ("a*******e@temp-services.co.uk", "a*******e@temp-services.co.uk"),
    ("b********s@company.org", "b********s@company.org"),
    ("j**********r@startup.io", "j**********r@startup.io"),
    ("s**********r@startup.io", "s**********r@startup.io"),
    ("t*********s@example.com", "t*********s@example.com"),
    ("j***n@example.com", "j***n@example.com"),
    # HTML entity with spaces
    ("john &#64; example.com", "john@example.com"),
    ("jack &#x40;torchwood.xyz", "jack@torchwood.xyz"),
    ("ahmed &#64; example.sa", "ahmed@example.sa"),
    ("nina.anderson &#64; techcorp.dev", "nina.anderson@techcorp.dev"),
    ("alice &#64; acme.com", "alice@acme.com"),
    ("rachel.lee &#64; weeping-angels.com", "rachel.lee@weeping-angels.com"),
    ("sofia.cooper &#x40;mail.company.io", "sofia.cooper@mail.company.io"),
    # HTML entity dots only (no @ in text - these should still fail)
    ("rachel.lee &#046; weeping-angels &#46; com", "rachel.lee@weeping-angels.com"),
    ("john &#046; example &#46; com", "john@example.com"),
    ("alice &#046; acme &#46; com", "alice@acme.com"),
    # BOM zero-width
    ("jamal.white\ufeff@temp-services\ufeff.co.uk", "jamal.white@temp-services.co.uk"),
]

print(f"{'RESULT':>6} | RAW")
print("=" * 100)
for raw, expected in tests:
    cleaned, log = deob(raw)
    
    # Try all EMAIL patterns
    matched_any = False
    matches = []
    for name, p, score in email_patterns:
        for m in p.finditer(cleaned):
            matches.append(m.group())
            if m.group() == expected:
                matched_any = True
    
    status = "OK" if matched_any else "MISS"
    print(f"[{status:>4}] | raw: {raw[:60]:<60}")
    if status == "MISS":
        print(f"      | cleaned: {cleaned!r}")
        print(f"      | matches: {matches}")

print("\n\n=== Detailed: star pattern check ===")
star_test = "j**n@example.com"
cleaned, _ = deob(star_test)
for name, p, score in email_patterns:
    print(f"Pattern: {p.pattern}")
    matches = list(p.finditer(cleaned))
    for m in matches:
        print(f"  Match [{m.start()}:{m.end()}]: {m.group()!r}")