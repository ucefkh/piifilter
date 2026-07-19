"""Debug the benchmark's actual import path resolution."""
import sys
from pathlib import Path
from pprint import pprint

PROJECT_ROOT = Path(__file__).resolve().parent.parent

print(f"PROJECT_ROOT: {PROJECT_ROOT}")
path_to_insert = str(PROJECT_ROOT / "plugins" / "detector-regex" / "src")
print(f"Insert path: {path_to_insert}")
print(f"Exists: {Path(path_to_insert).exists()}")
print(f"Contents: {list(Path(path_to_insert).iterdir()) if Path(path_to_insert).exists() else 'N/A'}")
print(f"piifilter_detector_regex dir: {(Path(path_to_insert) / 'piifilter_detector_regex').exists()}")

sys.path.insert(0, path_to_insert)

# Check what we actually get
import importlib
try:
    mod = importlib.import_module("piifilter_detector_regex.patterns")
    print(f"Loaded from: {mod.__file__}")
    print(f"Pattern count: {len(mod.PATTERN_DEFS)}")
except Exception as e:
    print(f"Import error: {e}")
    import traceback
    traceback.print_exc()

# Now also need core
sys.path.insert(0, str(PROJECT_ROOT / "core" / "src"))
from piifilter.shared.models import EntityType
print(f"EntityType OK: {EntityType}")

# Now compile exactly as the benchmark does
import re
from piifilter_detector_regex.patterns import PATTERN_DEFS

_LEGACY_MAP: dict[str, str] = {"SOCIAL_SECURITY": "ssn"}
_FALLBACK_MAP: dict[str, str] = {
        "jwt": "token",
        "domain": "url",
        "database_url": "url",
        "private_url": "url",
        "file_path": "url",
        "ssh_key": "api_key",
        "iban": "bank_account",
        "date": "unknown",
        "gps": "unknown",
    }
_DIRECT_MAP = {
        "PERSON", "EMAIL", "PHONE", "ADDRESS", "CITY", "COUNTRY",
        "COMPANY", "BANK_ACCOUNT", "IBAN", "CREDIT_CARD", "PASSPORT",
        "SOCIAL_SECURITY", "JWT", "API_KEY", "SSH_KEY", "DATABASE_URL",
        "PRIVATE_URL", "PROJECT_NAME", "CUSTOMER_NAME", "EMPLOYEE_NAME",
        "GPS", "DOMAIN", "IP_ADDRESS", "FILE_PATH",
    }

def _resolve_entity_type(name: str) -> EntityType:
    if name in _DIRECT_MAP:
        return EntityType(name)
    lookup = _LEGACY_MAP.get(name, name.lower())
    try:
        return EntityType(lookup)
    except ValueError:
        return EntityType("PERSON")

for i, (type_name, raw_pattern, score) in enumerate(PATTERN_DEFS):
    try:
        entity_type = _resolve_entity_type(type_name)
        pattern = re.compile(raw_pattern, re.UNICODE)
    except Exception as e:
        print(f"FAIL at [{i}] {type_name}: {e}")
        print(f"  pattern preview: {raw_pattern[:100]!r}")
        break
else:
    print("All patterns compiled OK!")