"""Investigate CC/SSN recall gaps and test fixes."""
from __future__ import annotations

import re
import sys
sys.path.insert(0, "/home/ucefkh/projects/privacy-proxy-ai/plugins/detector-regex/src")
sys.path.insert(0, "/home/ucefkh/projects/privacy-proxy-ai/core/src")

from piifilter_detector_regex.detector import RegexDetector
from piifilter_detector_regex.patterns import PATTERN_DEFS
from piifilter.shared.validation import (
    _luhn_checksum, _strip_cc, CreditCardValidator, SsnValidator
)
from piifilter.shared.deobfuscator import Deobfuscator

d = RegexDetector()
print("=== Investigation: CC/SSN recall gaps ===")

# 1. Test the _run_luhn_on_numeric_runs on stripped text
# Check: does it find Luhn-valid digit runs that the regex pattern missed?
test_cc_texts = [
    "4111111111111111",           # Standard Visa
    "5500000000000004",           # MC
    "378282246310005",            # Amex 15-digit
    "6011111111111117",           # Discover
    "3530111333300000",           # JCB 16-digit
    "30569309025904",             # Diners 14-digit
    "4111 1111 1111 1111",       # With spaces
    "4111-1111-1111-1111",       # With dashes
    "4111.1111.1111.1111",       # With dots
    "4111  1111  1111  1111",    # Double-spaced
    "41 11 11 11 11 11 11 11",  # 2-digit paired
    "60 11 11 11 11 11 11 17",  # Discover with spaces
    "37 82 82 24 63 10 00 5",   # Amex 2-digit paired
]

print("\n--- Test 1: Luhn on stripped text ---")
for raw in test_cc_texts:
    stripped = re.sub(r"[^0-9]", "", raw)
    luhn_pass = _luhn_checksum(stripped) == 0
    length = len(stripped)
    print(f"  raw={raw!r:40s} → digits={stripped} len={length} luhn={luhn_pass}")

# 2. Greedy Luhn: try ALL substrings of length 13-19 within a broader digit range
print("\n--- Test 2: Greedy Luhn on wider digit runs ---")
def greedy_luhn(text: str) -> list[tuple[int, int, str]]:
    """Find all Luhn-valid substrings of length 13-19 in digit runs >= 13 chars."""
    results = []
    # Find all digit runs >= 13 chars
    for m in re.finditer(r"\d{13,}", text):
        digits = m.group()
        base_start = m.start()
        if len(digits) > 19:
            # Greedy: slide 13-19 char window
            for i in range(len(digits) - 12):
                for length in range(13, min(20, len(digits) - i + 1)):
                    sub = digits[i:i+length]
                    if len(sub) >= 13 and _luhn_checksum(sub) == 0:
                        results.append((base_start + i, base_start + i + length, sub))
                        break  # Longest valid prefix, then move on
        elif len(digits) >= 13:
            # Direct match
            if _luhn_checksum(digits) == 0:
                results.append((base_start, m.end(), digits))
    return results

# Test greedy on some edge cases
test_greedy = [
    "411111111111111183783",       # 18 digits with embedded valid CC
    "6011111111111117837",          # 17 digits
    "4000056655665556extra",        # Valid Luhn with suffix
    "extra4111111111111111suffix",  # Valid CC with prefix/suffix within 19
]

for t in test_greedy:
    hits = greedy_luhn(t)
    print(f"  text={t!r:50s} hits={hits}")

# 3. SSN validator relaxation: what edge cases are being missed?
print("\n--- Test 3: SSN validator edge cases ---")
ssn_validator = SsnValidator()
test_ssns = [
    ("123-45-6789", True),  # Standard valid
    ("987-65-4321", True),  # Standard valid
    ("000-12-3456", False), # Area 000 - invalid
    ("666-12-3456", False), # Area 666 - invalid
    ("900-12-3456", False), # Area 900 - invalid
    ("123-00-6789", False), # Group 00 - invalid
    ("123-45-0000", False), # Serial 0000 - invalid
    # Recently issued SSNs that might be valid
    ("899-01-2345", False), # Area 899 - currently treated as invalid (>=900 check)
]

print("  Current SSN validator behavior:")
for ssn, expected in test_ssns:
    digits = re.sub(r"[^0-9]", "", ssn)
    result = ssn_validator.validate(digits)
    status = "PASS" if result.status.value == "valid" else "FAIL"
    area = int(digits[:3])
    print(f"  {ssn:16s} area={area:3d} → {status} (score={result.score})")

# 4. Check what the multi-view detection actually does
print("\n--- Test 4: Multi-view detection analysis ---")
# The detector runs on stripped text. Let's see what happens with the deobfuscator.
deob = Deobfuscator()

test_obfuscation = [
    "4111-1111-1111-1111",                  # Dashes
    "4111 1111 1111 1111",                  # Spaces
    "4111.1111.1111.1111",                  # Dots
    "41 11 11 11 11 11 11 11",              # 2-digit paired
    "5500.0000.0000.0004",                  # MC with dots
    "3782.8224.6310.005",                   # Amex with dots
    "6011 1111 1111 1117",                  # Discover with space
    "123-45-6789",                           # Standard SSN
    "987-65-4321",                           # Standard SSN
    "123.45.6789",                           # SSN with dots
    "123 45 6789",                           # SSN with spaces
]

print("  Deobfuscator + strip chain:")
for raw in test_obfuscation:
    cleaned, log, text_for_gps = deob(raw)
    stripped = Deobfuscator._strip_inner_separators(cleaned)
    print(f"  raw={raw!r:40s} → cleaned={cleaned!r} → stripped={stripped!r}")

print("\n=== Investigation complete ===")