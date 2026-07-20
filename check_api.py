#!/usr/bin/env python3
"""Check detector API."""
from piifilter_detector_regex.detector import RegexDetector
import inspect

d = RegexDetector()
methods = inspect.getmembers(d, predicate=inspect.ismethod)
for name, m in methods:
    if 'detect' in name.lower() or 'analyze' in name.lower() or 'process' in name.lower() or 'run' in name.lower():
        sig = inspect.signature(m)
        print(f'{name}{sig}')