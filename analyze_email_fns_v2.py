"""Analyze EMAIL FNs properly — apply deobfuscator first, like the real detector does."""
import json
import sys
import re
from pathlib import Path

sys.path.insert(0, str(Path("core/src").resolve()))
sys.path.insert(0, str(Path("plugins/detector-regex/src").resolve()))

from piifilter.shared.deobfuscator import Deobfuscator
deob = Deobfuscator()

# Load the dataset
dataset_path = Path("benchmarks/data/pii_dataset_v2.json")
data = json.loads(dataset_path.read_text())

# Current pattern
current_pattern = re.compile(r'\b[\w.+-]+@[\w-]+\.[\w.-]+\b', re.UNICODE)

# Collect all EMAIL entities with their example texts
email_fns = []
email_tps = []
total = 0

for ex in data["examples"]:
    text = ex["text"]
    # Apply deobfuscation like the real detector
    cleaned, deob_log = deob(text)
    
    for ent in ex["entities"]:
        if ent["type"] != "EMAIL":
            continue
        total += 1
        value = ent["value"]
        
        # Check if the pattern finds this entity in the deobfuscated text
        # We need to check if the entity's value (or its deobfuscated form) is matched
        # The best approach: run the pattern on the cleaned text and check if it covers the entity span
        
        # But entity spans are in original text, not cleaned text. Let me check if
        # the pattern matches the value itself, since that's what should be found
        # in the deobfuscated text.
        
        # Actually the easiest check: does the pattern find this value anywhere in the cleaned text?
        # Let's check by looking for the pattern matching the email value
        
        found = False
        for m in current_pattern.finditer(cleaned):
            mval = m.group()
            # Check if the matched value contains or equals the email value
            # This is approximate but will catch most cases
            if value.lower() in mval.lower() or mval.lower() in value.lower():
                # Check reasonable overlap
                common_chars = sum(1 for c in value.lower().strip(' .@') if c in mval.lower())
                if common_chars >= max(3, len(value) // 2):
                    found = True
                    break
        
        if found:
            email_tps.append(value)
        else:
            email_fns.append({"text": text, "cleaned": cleaned, "value": value})

print(f"Total EMAIL entities: {total}")
print(f"True Positives (matched after deobf): {len(email_tps)}")
print(f"False Negatives (still missed): {len(email_fns)}")
print(f"\nEffective EMAIL recall: {len(email_tps) / total:.4f}")

# Now categorize the real FNs by what feature of the email causes the miss
real_fns = []  # These are emails the pattern genuinely misses
for fn in email_fns:
    v = fn["value"]
    c = fn["cleaned"]
    
    # Try to find email in cleaned text
    for m in current_pattern.finditer(c):
        pass  # We already know it wasn't found

    real_fns.append(fn)

print(f"\n{'='*80}")
print(f"GENUINE EMAIL FNs (missed by pattern even after deobfuscation): {len(real_fns)}")
print(f"{'='*80}")

# Categorize
cat = {"long_tld": [], "plus_tag": [], "subdomain_multi_tld": [], "quoted_bracketed": [], "no_dot": [], "other": []}

for fn in real_fns[:50]:  # First 50
    v = fn["value"]
    c = fn["cleaned"]
    
    # Show the text context
    print(f"\n  VALUE:      {v}")
    print(f"  CLEANED:    {c[:200]}")
    
    # Try the pattern on the raw value to see what it matches
    m = current_pattern.search(c)
    if m:
        print(f"  MATCH:      '{m.group()}' at [{m.start()}:{m.end()}]")
    else:
        print(f"  PATTERN:    NO MATCH on cleaned text")
    
    # What's in the cleaned text that might be the email?
    # Find the email value parts in cleaned text
    parts = v.replace("[at]", "@").replace("[dot]", ".").split("@")
    if len(parts) == 2:
        local, domain = parts
        domain_parts = domain.split(".")
        tld = domain_parts[-1] if domain_parts else ""
        
        issues = []
        if "+" in local:
            issues.append("PLUS_TAG")
        if len(tld) > 4:
            issues.append(f"LONG_TLD('{tld}')")
        if len(domain_parts) > 2:
            issues.append(f"MULTI_DOMAIN({len(domain_parts)} parts)")
        
        if issues:
            print(f"  ISSUES:     {', '.join(issues)}")
            for iss in issues:
                if "PLUS" in iss:
                    cat["plus_tag"].append(fn)
                elif "LONG" in iss:
                    cat["long_tld"].append(fn)
                elif "MULTI" in iss:
                    cat["subdomain_multi_tld"].append(fn)
        else:
            # Check for zero-width chars in the email after deobf
            zw_count = sum(1 for c in c if ord(c) in range(0x200B, 0x200F+1) or ord(c) in range(0xFE00, 0xFE0F+1) or ord(c) == 0x2060 or ord(c) == 0x2061 or ord(c) == 0x2062 or ord(c) == 0x2063 or ord(c) == 0x2064 or ord(c) == 0x180E or ord(c) == 0x00AD)
            if zw_count > 0:
                print(f"  ISSUES:     zero-width chars in text ({zw_count} found)")
                cat["other"].append(fn)
            else:
                # Does local part contain dots that the pattern handles?
                print(f"  ISSUES:     unknown — local='{local}', domain='{domain}'")
                cat["other"].append(fn)
    else:
        print(f"  ISSUES:     not a standard email format (no @ found after deobf)")
        cat["other"].append(fn)

print(f"\n\n{'='*80}")
print("CATEGORIZATION SUMMARY:")
print(f"{'='*80}")
for c, items in cat.items():
    print(f"  {c}: {len(items)}")