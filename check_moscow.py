#!/usr/bin/env python3
"""Check Moscow offset."""
import sys
sys.path.insert(0, 'core/src')
sys.path.insert(0, 'plugins/detector-regex/src')
from piifilter.shared.deobfuscator import Deobfuscator
deob = Deobfuscator()

text = "GPS: lat: 55.7558, lng: 37.6173 (Moscow) and lat: 59.9343, lng: 30.3351 (SPB)"
print(f"Original [{len(text)}]: idx of Moscow = {text.index('Moscow')}")
cleaned, log, gps = deob(text)
print(f"Cleaned [{len(cleaned)}]: {repr(cleaned)}")
if 'Moscow' in cleaned:
    print(f"  idx of Moscow = {cleaned.index('Moscow')}")

stripped = Deobfuscator._strip_inner_separators(cleaned)
if 'Moscow' in stripped:
    print(f"Stripped idx of Moscow = {stripped.index('Moscow')}")