"""Debug specific patterns against missed values."""
import re

test_cases = [
    "07700 900 123",
    "49 30 12345678",
    "44 20 7946 0958",  # works
]

patterns_to_test = [
    (0, r"\b07\d{2}\s+\d{3}\s+\d{3}\b", "UK mobile bare with space"),
    (1, r"\b\d{1,4}(?:\s+\d{2,4}){2,4}\b", "Variable-spaced"),
    (2, r"\b\d{2,4}[–—−\-.\\s]\d{2,4}[–—−\-.\\s]\d{2,4}[–—−\-.\\s]\d{2,4}\b", "Universal"),
]

for val in test_cases:
    print(f"\n=== \"{val}\" (len={len(val)}) ===")
    for idx, pat_str, desc in patterns_to_test:
        pat = re.compile(pat_str)
        m = pat.search(val)
        if m:
            print(f"  [{idx}] {desc}: MATCH='{m.group()}' [{m.start()}:{m.end()}]")
        else:
            print(f"  [{idx}] {desc}: NO MATCH")
    
    # Show char details
    print(f"  chars: {[c for c in val]}")
    print(f"  hex:   {[hex(ord(c)) for c in val]}")
    print(f"  spaces: {val.count(' ')} spaces at positions {[i for i,c in enumerate(val) if c==' ']}")