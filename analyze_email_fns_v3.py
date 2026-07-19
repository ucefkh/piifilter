"""Properly analyze EMAIL FNs by running the actual regex detector on the held-out set."""
import json
import sys
import re
from pathlib import Path

sys.path.insert(0, str(Path("core/src").resolve()))
sys.path.insert(0, str(Path("plugins/detector-regex/src").resolve()))

from piifilter_detector_regex.patterns import PATTERN_DEFS
from piifilter.shared.deobfuscator import Deobfuscator
from piifilter.shared.models import EntityType

deob = Deobfuscator()

# Build patterns like the real detector does
patterns = []
for type_name, raw_pattern, score in PATTERN_DEFS:
    if type_name == "EMAIL":
        compiled = re.compile(raw_pattern, re.UNICODE)
        patterns.append((type_name, compiled, score))

# Load dataset
dataset_path = Path("benchmarks/data/pii_dataset_v2.json")
data = json.loads(dataset_path.read_text())

# Find all EMAIL entities and test if the pattern catches them
email_fns = []
for ex in data["examples"]:
    text = ex["text"]
    cleaned, _ = deob(text)
    
    for ent in ex["entities"]:
        if ent["type"] != "EMAIL":
            continue
        
        # Check if any pattern match in the cleaned text overlaps with the entity span
        val = ent["value"]
        start = ent["start"]
        end = ent["end"]
        
        found = False
        for type_name, pattern, score in patterns:
            for m in pattern.finditer(cleaned):
                mstart, mend = m.start(), m.end()
                # Check overlap with entity span
                overlap = min(end, mend) - max(start, mstart)
                if overlap > 0 and overlap >= 0.5 * min(end - start, mend - mstart):
                    found = True
                    break
            if found:
                break
        
        if not found:
            email_fns.append({
                "text": text,
                "cleaned": cleaned,
                "value": val,
                "start": start,
                "end": end,
            })

print(f"EMAIL FNs in FULL dataset: {len(email_fns)}")

# Now find what the issue is for each
cat = {"long_tld_only": [], "plus_tag": [], "subdomain+long_tld": [],
       "quoted": [], "zero_width": [], "deobf_issue": [], "pattern_issue": [],
       "token_split": [], "html_comment": [], "js_concat": [], "other": []}

for fn in email_fns:
    t = fn["text"]
    c = fn["cleaned"]
    
    # Check what patterns find in cleaned text near the entity position
    all_matches = []
    for type_name, pattern, score in patterns:
        for m in pattern.finditer(c):
            all_matches.append((type_name, m.group(), m.start(), m.end()))
    
    # See if the deobfuscated email is in the cleaned text
    # The entity value may still be obfuscated
    v = fn["value"]
    
    # Check cleaned text for any email-like string near entity position  
    cleaned_nearby = c[max(0, fn["start"]-20):min(len(c), fn["end"]+20)]
    
    # Check for common patterns in cleaned text
    issues = []
    if "[at]" in t.lower() or "[dot]" in t.lower():
        issues.append("deobf_issue")
    if "&#" in t or "&#x" in t:
        issues.append("deobf_issue")
    if "\\u00" in t:
        issues.append("deobf_issue")
    if "+" in v and "@" in v:
        parts = v.split("@")
        if "+" in parts[0]:
            issues.append("plus_tag")
    if v.count(".") >= 3:
        issues.append("subdomain+long_tld")
    if len(v.split(".")[-1] if "." in v else "") > 4:
        issues.append("long_tld_only")
    if '"' in v or "'" in v or '(' in v or ')' in v:
        issues.append("quoted")
    if any(ord(c) > 0x2000 for c in v):
        issues.append("zero_width")
    
    # Check the cleaned text
    if "<!--" in c[fn["start"]-10:fn["end"]+10]:
        issues.append("html_comment")
    if "' + '" in c[fn["start"]-10:fn["end"]+10] or '" + "' in c[fn["start"]-10:fn["end"]+10]:
        issues.append("js_concat")
    if "token" in t.lower() or "split" in t.lower():
        issues.append("token_split")
    
    # Count what's really wrong
    if not issues:
        # Debug: what's in the cleaned text at the entity position?
        actual_text = c[fn["start"]:fn["end"]]
        issues.append(f"other_clean='{actual_text}'")
    
    key = issues[0] if issues else "other"
    if key == "subdomain+long_tld" or key == "long_tld_only":
        cat["long_tld_only"].append(fn)
    elif key == "plus_tag":
        cat["plus_tag"].append(fn)
    elif key in cat:
        cat[key].append(fn)
    else:
        cat["other"].append(fn)

print("\n--- CATEGORIZATION ---")
for k, v in sorted(cat.items()):
    print(f"  {k}: {len(v)}")

# Show actual missed patterns in cleaned text
print("\n--- DETAILED FN EXAMPLES (from actual held-out set) ---")
# Actually let me just run the benchmark to get the real held-out FNs
print("\nLet me instead run the actual benchmark...")