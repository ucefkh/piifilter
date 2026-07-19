"""Verify that keyword-prefixed ADDRESS pattern still overlaps expected entities."""
import re

# Current pattern
cur_pat = re.compile(r"\b\d{1,5}\s+(?:[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})\s+(?:St(?:reet)?|Ave(?:nue)?|Dr(?:ive)?|Rd|Road|Blvd|Boulevard|Ln|Lane|Way|Ct|Court|Pl|Place|Cir(?:cle)?|Pkwy|Parkway)\b")

# Keyword-prefixed version — non-optional prefix, so match INCLUDES the keyword
# (?:address\s*:?\s*|at\s+|is\s+at\s+|\boffice\s+is\s+at\s+|\bhome\s+address\s*:\s*|\bmailing\s+address\s*:\s*|\bvisit\s+us\s+at\s+)
kw_pat = re.compile(r"(?:address\s*:?\s*|at\s+|is\s+at\s+|office\s+is\s+at\s+|home\s+address\s*:\s*|mailing\s+address\s*:\s*|visit\s+us\s+at\s+|HQ\s+is\s+at\s+)?\b(?P<number>\d{1,5})\s+(?:[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})\s+(?:St(?:reet)?|Ave(?:nue)?|Dr(?:ive)?|Rd|Road|Blvd|Boulevard|Ln|Lane|Way|Ct|Court|Pl|Place|Cir(?:cle)?|Pkwy|Parkway)\b")

tests = [
    ("Our office is at 350 Fifth Avenue, New York, NY 10118", (17, 33)),  # expected ADDRESS starts at 17
    ("Visit us at 10 Downing Street, London, SW1A 2AA", (12, 29)),
    ("Home address: 123 Maple Drive, Springfield, IL 62704", (14, 29)),
    ("My street is 123 Main Street, not 123 Main St.", None),  # FP — no expected
    ("The address is at 42 Wallaby Way, Sydney", None),  # FP — no expected
]

for text, expected_span in tests:
    m = kw_pat.search(text)
    if m:
        print(f'Match: "{m.group()}" start={m.start()} end={m.end()}')
        if expected_span:
            expected_start, expected_end = expected_span
            # Calculate overlap IoU
            intersection = max(0, min(m.end(), expected_end) - max(m.start(), expected_start))
            my_len = m.end() - m.start()
            expected_len = expected_end - expected_start
            smallest = min(my_len, expected_len)
            iou = intersection / smallest if smallest > 0 else 0
            print(f'  Expected: ({expected_start},{expected_end}) -> intersection={intersection}, smallest={smallest}, IoU={iou:.2f}')
            print(f'  Type match: ADDRESS == ADDRESS')
            if iou >= 0.5:
                print(f'  => TP ✓')
            else:
                print(f'  => Would be FN ✗')
        else:
            print(f'  No expected ADDRESS -> FP (but that\'s expected without keyword context)')
    else:
        print(f'No match for: "{text[:40]}..."')
        if expected_span:
            print(f'  But expected ADDRESS at {expected_span} -> Would be FN ✗')
        else:
            print(f'  Correctly not detected (FN gone) ✓')