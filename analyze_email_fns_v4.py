"""Show actual EMAIL FNs with full context."""
import json
import sys
import re
from pathlib import Path

sys.path.insert(0, str(Path("core/src").resolve()))
sys.path.insert(0, str(Path("plugins/detector-regex/src").resolve()))

from piifilter_detector_regex.patterns import PATTERN_DEFS
from piifilter.shared.deobfuscator import Deobfuscator

deob = Deobfuscator()

# Build pattern
email_pattern = None
for type_name, raw_pattern, score in PATTERN_DEFS:
    if type_name == "EMAIL":
        email_pattern = re.compile(raw_pattern, re.UNICODE)
        print(f"Current EMAIL pattern: {raw_pattern}")
        break

# Load dataset
dataset_path = Path("benchmarks/data/pii_dataset_v2.json")
data = json.loads(dataset_path.read_text())

# Collect FNs
email_fns = []
for ex in data["examples"]:
    text = ex["text"]
    cleaned, log = deob(text)
    
    for ent in ex["entities"]:
        if ent["type"] != "EMAIL":
            continue
        
        val = ent["value"]
        start = ent["start"]
        end = ent["end"]
        
        # Does the pattern find something that overlaps this entity?
        found = False
        for m in email_pattern.finditer(cleaned):
            mstart, mend = m.start(), m.end()
            overlap = min(end, mend) - max(start, mstart)
            smallest = min(end - start, mend - mstart)
            if smallest > 0 and (overlap / smallest) >= 0.5:
                found = True
                break
        
        if not found:
            # Show the text around this entity
            ctx_start = max(0, start - 30)
            ctx_end = min(len(text), end + 50)
            clean_ctx_start = max(0, start - 10)
            clean_ctx_end = min(len(cleaned), end + 30)
            
            print(f"\n{'='*100}")
            print(f"FN VALUE:  {repr(val)}")
            print(f"CONTEXT:   {repr(text[ctx_start:ctx_end])}")
            print(f"CLEANED:   {repr(cleaned[clean_ctx_start:clean_ctx_end])}")
            print(f"LOG:       {log}")
            
            # What does the pattern find in this region?
            print(f"MATCHES in cleaned text nearby:")
            region_start = max(0, start - 5)
            region_end = min(len(cleaned), end + 5)
            region = cleaned[region_start:region_end]
            for m in email_pattern.finditer(cleaned):
                print(f"  [{m.start()}:{m.end()}] '{m.group()}'")
            
            # Test: would a better regex catch it?
            # Try various improved patterns
            patterns_to_test = {
                "original": r'\b[\w.+-]+@[\w-]+\.[\w.-]+\b',
                "wider": r'\b[\w.+\-]+@[\w\-]+(?:\.[\w\-]+)+\b',
                "quoted": r'\b[\w.+\-]+@[\w\-]+(?:\.[\w\-]+)+\.?[a-zA-Z]{2,}\b',
                "no_word_boundary": r"(?<=\s|^|[<(\\\['])[\w.+\-]+@[\w\-]+(?:\.[\w\-]+)+\.?[a-zA-Z]{2,}(?=\s|$|[>)\]\\,;:!.?])",
            }
            print(f"\n  PATTERN TESTS:")
            for name, pat in patterns_to_test.items():
                test_re = re.compile(pat, re.UNICODE)
                m = test_re.search(cleaned)
                if m:
                    print(f"    {name}: FOUND '{m.group()}' at [{m.start()}:{m.end()}]")
                else:
                    print(f"    {name}: NOT FOUND")

print(f"\n\nTotal EMAIL FNs: {len(email_fns)}")