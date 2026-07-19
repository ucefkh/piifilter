"""Quick test to verify imports work and RegexDetector is usable."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "core" / "src"))
sys.path.insert(0, str(ROOT / "plugins" / "detector-regex" / "src"))

from piifilter_detector_regex.detector import RegexDetector
from piifilter.shared.deobfuscator import Deobfuscator
from piifilter.shared.models import EntityType, DetectedEntity

print("All imports OK")
print(f"RegexDetector: {RegexDetector}")
print(f"Deobfuscator: {Deobfuscator}")