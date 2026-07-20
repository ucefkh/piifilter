"""Check normalization of CandidateSpan."""
import sys
sys.path.insert(0, 'plugins/detector-regex/src')
sys.path.insert(0, 'core/src')
import asyncio
from piifilter_detector_regex.detector import RegexDetector

text = 'SSN last-4: 6789. Full: XXX-XX-6789'
detector = RegexDetector()
asyncio.run(detector.initialize())
detected = asyncio.run(detector.detect(text))

for d in detected:
    print(f"Direct: type={d.entity_type.value}, raw_score={d.raw_score}, text={d.text}")
    # Check attributes
    print(f"  has 'confidence': {hasattr(d, 'confidence')}")
    print(f"  has 'score': {hasattr(d, 'score')}")
    print(f"  has 'raw_score': {hasattr(d, 'raw_score')}")
    # Manual normalize
    norm = {
        "type": d.entity_type.value,
        "value": d.text,
        "start": d.start,
        "end": d.end,
        "score": getattr(d, 'confidence', getattr(d, 'score', 1.0)),
    }
    print(f"  Normalized score: {norm['score']}")  # Falls back to 1.0!