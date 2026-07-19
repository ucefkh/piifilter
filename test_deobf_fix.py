"""Test the deobfuscator fix for &#046; → @ in email obfuscation."""
import sys
import re
from pathlib import Path

sys.path.insert(0, str(Path("core/src").resolve()))
sys.path.insert(0, str(Path("plugins/detector-regex/src").resolve()))

from piifilter.shared.deobfuscator import Deobfuscator

deob = Deobfuscator()

# Test cases
test_cases = [
    # &#046; = period, used as @ in obfuscation
    ("Found: alice &#046; acme &#46; com", "Found: alice@acme.com"),
    ("Data: maria.garcia &#046; co &#46; jp", "Data: maria.garcia@co.jp"),
    ("Raw: support &#046; help &#46; io", "Raw: support@help.io"),
    ("Found: test.user+tag &#046; mail &#46; company &#46; io", "Found: test.user+tag@mail.company.io"),
    ("Obfuscated email: zhangwei &#046; example &#46; cn", "Obfuscated email: zhangwei@example.cn"),
    ("Obfuscated email: giorgos &#046; example &#46; gr", "Obfuscated email: giorgos@example.gr"),
    ("Obfuscated email: john &#046; doe &#46; com", "Obfuscated email: john@doe.com"),
    ("Data: test &#046; exаmple &#46; com", "Data: test@exаmple.com"),
    ("Found: john &#046; example &#46; com", "Found: john@example.com"),
    ("Hidden field: john &#046; example &#46; com", "Hidden field: john@example.com"),
    ("Hidden field: ravi.green &#046; company &#46; org", "Hidden field: ravi.green@company.org"),
    ("Obfuscated email: xia.wright &#046; mycompany &#46; net", "Obfuscated email: xia.wright@mycompany.net"),
    ("Found: ivan.williams &#046; acme &#46; com", "Found: ivan.williams@acme.com"),
    ("Encoded: rachel.lee &#046; weeping-angels &#46; com", "Encoded: rachel.lee@weeping-angels.com"),
    ("Encoded: uma.carter &#046; temp-services &#46; co &#46; uk", "Encoded: uma.carter@temp-services.co.uk"),
    ("Obfuscated email: nina.anderson &#046; techcorp &#46; dev", "Obfuscated email: nina.anderson@techcorp.dev"),
    ("Data: yara.smith &#046; data-service &#46; ai", "Data: yara.smith@data-service.ai"),
    ("Data: cheng.adams &#046; data-service &#46; ai", "Data: cheng.adams@data-service.ai"),
    ("Found: gopal.torres &#046; techcorp &#46; dev", "Found: gopal.torres@techcorp.dev"),
    ("Found: patricia.jones &#046; weeping-angels &#46; com", "Found: patricia.jones@weeping-angels.com"),
    
    # HTML comment case
    ("Hidden: john<!--comment-->@example.com", "Hidden: john@example.com"),
    
    # Normal email should not be affected
    ("Email: alice@acme.com", "Email: alice@acme.com"),
]

from piifilter_detector_regex.patterns import PATTERN_DEFS
email_pattern = None
for tn, rp, sc in PATTERN_DEFS:
    if tn == "EMAIL":
        email_pattern = re.compile(rp, re.UNICODE)
        print(f"EMAIL pattern: {rp}")
        break

print()
pass_count = 0
fail_count = 0

for raw_text, expected_text in test_cases:
    cleaned, log = deob(raw_text)
    
    expected_clean = expected_text
    clean_ok = cleaned == expected_clean
    
    # Check pattern match
    m = email_pattern.search(cleaned)
    has_email = m is not None
    should_have_email = "@" in expected_clean
    
    email_ok = has_email == should_have_email
    if has_email:
        email_ok = email_ok and m.group() in expected_clean
    
    all_ok = clean_ok and email_ok
    
    if all_ok:
        pass_count += 1
        status = "PASS"
    else:
        fail_count += 1
        status = "FAIL"
    
    print(f"[{status}] {raw_text[:60]}")
    print(f"       expected: {expected_clean[:60]}")
    print(f"       got:      {cleaned[:60]}")
    if m:
        print(f"       matched:  '{m.group()}'")
    else:
        print(f"       matched:  (none)")
    if not clean_ok:
        print(f"       !!! Cleaned text differs from expected")
    if not email_ok:
        print(f"       !!! Email detection incorrect")
    print()

print(f"\nPassed: {pass_count}/{len(test_cases)}")
print(f"Failed: {fail_count}/{len(test_cases)}")