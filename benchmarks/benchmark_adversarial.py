#!/usr/bin/env python3
"""Adversarial Obfuscation Benchmark — full RegexDetector pipeline vs raw regex.

Measures the full system's obfuscation resistance by running each adversarial
example through:

  1. Full pipeline: RegexDetector.detect() — deobfuscator + regex patterns + Luhn
  2. Raw regex (no deobfuscation) — for before/after comparison

Generates 120+ adversarial examples across 16 evasion categories and reports
detection rates per category.

Usage:
    uv run python -m benchmarks.benchmark_adversarial
    uv run python benchmarks/benchmark_adversarial.py

Output:
    - benchmarks/adversarial-results.json  (full results)
    - STDOUT summary table with before/after comparison
"""

from __future__ import annotations

import asyncio
import base64
import json
import re
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# ── Imports — full pipeline via RegexDetector ──────────────────────────
sys.path.insert(0, str(PROJECT_ROOT / "core" / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "plugins" / "detector-regex" / "src"))

from piifilter_detector_regex.detector import RegexDetector
from piifilter_detector_regex.patterns import PATTERN_DEFS
from piifilter.shared.models import EntityType, DetectedEntity
from piifilter.shared.deobfuscator import Deobfuscator


# ── Obfuscation technique helpers ──────────────────────────────────────────

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


def compile_patterns() -> list[tuple[EntityType, re.Pattern[str], float]]:
    """Compile PATTERN_DEFS into (EntityType, Pattern, score) tuples, same as RegexDetector."""
    compiled: list[tuple[EntityType, re.Pattern[str], float]] = []
    for type_name, raw_pattern, score in PATTERN_DEFS:
        entity_type = _resolve_entity_type(type_name)
        pattern = re.compile(raw_pattern, re.UNICODE)
        compiled.append((entity_type, pattern, score))
    return compiled


def luhn_valid(digits: str) -> bool:
    """Luhn check for credit card validation."""
    nums = [int(d) for d in digits if d.isdigit()]
    if len(nums) < 13:
        return False
    for i in range(len(nums) - 2, -1, -2):
        nums[i] *= 2
        if nums[i] > 9:
            nums[i] -= 9
    return sum(nums) % 10 == 0


def detect_raw_regex(text: str, patterns: list[tuple[EntityType, re.Pattern[str], float]]) -> list[dict[str, Any]]:
    """Run patterns against text WITHOUT deobfuscation — baseline comparison.
    
    This shows what raw regex would catch without any preprocessing,
    measuring the incremental value of the deobfuscation pipeline.
    """
    entities: list[dict[str, Any]] = []
    seen_intervals: list[tuple[int, int]] = []

    for entity_type, pattern, score in patterns:
        for match in pattern.finditer(text):
            start, end = match.start(), match.end()
            if start == end:
                continue
            if any(s <= start and end <= e for s, e in seen_intervals):
                continue
            if entity_type == EntityType.CREDIT_CARD:
                digits = "".join(c for c in match.group() if c.isdigit())
                if len(digits) >= 13 and not luhn_valid(digits):
                    continue
            entities.append({
                "type": entity_type.value,
                "value": match.group(),
                "start": start,
                "end": end,
                "score": score,
            })
            seen_intervals.append((start, end))

    entities.sort(key=lambda e: e["start"])
    return entities


def detect_full_pipeline(text: str, patterns: list[tuple[EntityType, re.Pattern[str], float]]) -> list[dict[str, Any]]:
    """Run patterns against text WITH full deobfuscation — the actual pipeline.
    
    This mirrors what RegexDetector.detect() does internally:
    deobfuscator → regex patterns → Luhn validation.
    """
    deob = Deobfuscator()
    text, _log, _text_for_gps = deob(text)

    entities: list[dict[str, Any]] = []
    seen_intervals: list[tuple[int, int]] = []

    for entity_type, pattern, score in patterns:
        for match in pattern.finditer(text):
            start, end = match.start(), match.end()
            if start == end:
                continue
            if any(s <= start and end <= e for s, e in seen_intervals):
                continue
            if entity_type == EntityType.CREDIT_CARD:
                digits = "".join(c for c in match.group() if c.isdigit())
                if len(digits) >= 13 and not luhn_valid(digits):
                    continue
            entities.append({
                "type": entity_type.value,
                "value": match.group(),
                "start": start,
                "end": end,
                "score": score,
            })
            seen_intervals.append((start, end))

    entities.sort(key=lambda e: e["start"])
    return entities


async def detect_via_regexdetector(text: str, detector: RegexDetector) -> list[dict[str, Any]]:
    """Run text through the actual RegexDetector async pipeline."""
    return await detector.detect(text)


# ── Adversarial examples ───────────────────────────────────────────────────

AdversarialExample = tuple[str, str, str]
# (category_name, display_label, text)


def build_adversarial_examples() -> list[AdversarialExample]:
    """Generate 120+ adversarial examples across 16 evasion categories."""
    examples: list[AdversarialExample] = []

    # ── 1. Homoglyph emails ────────────────────────────────────────────
    cyrillic_o = "\u043E"  # Cyrillic small letter о
    cyrillic_a = "\u0430"  # Cyrillic small letter а
    cyrillic_e = "\u0435"  # Cyrillic small letter е
    cyrillic_i = "\u0456"  # Cyrillic small letter і (Ukrainian)

    examples.append(("homoglyph", "Cyrillic о in local", f"Contact: j{cyrillic_o}hn@example.com"))
    examples.append(("homoglyph", "Cyrillic а in local", f"Email: m{cyrillic_a}rta@domain.com"))
    examples.append(("homoglyph", "Cyrillic а in domain", f"Email: test@ex{cyrillic_a}mple.com"))
    examples.append(("homoglyph", "Cyrillic е in local", f"Email: t{cyrillic_e}st@example.com"))
    examples.append(("homoglyph", "All Cyrillic vowels", f"Email: j{cyrillic_o}hn.sm{cyrillic_i}th@ex{cyrillic_a}mple.com"))
    examples.append(("homoglyph", "Cyrillic in TLD", f"Email: admin@mydomain.c{cyrillic_o}m"))
    examples.append(("homoglyph", "Mixed Cyrillic local+domain", f"Email: {cyrillic_a}dmin@{cyrillic_a}cme.c{cyrillic_o}m"))

    # ── 2. Zero-width char insertion ────────────────────────────────────
    zwsp = "\u200B"  # zero-width space
    zwj = "\u200D"   # zero-width joiner
    zwnj = "\u200C"  # zero-width non-joiner

    examples.append(("zero-width", "ZWSP in local", f"Email: j{zwsp}ohn@example.com"))
    examples.append(("zero-width", "ZWSP at @ border", f"Email: bob{zwsp}@{zwsp}example.com"))
    examples.append(("zero-width", "ZWJ in domain", f"Email: user@exa{zwj}mple.com"))
    examples.append(("zero-width", "ZWNJ in local", f"Email: al{zwnj}ice@acme.com"))
    examples.append(("zero-width", "Multiple ZWSP throughout", f"Email: t{zwsp}e{zwsp}s{zwsp}t{zwsp}@{zwsp}t{zwsp}e{zwsp}s{zwsp}t{zwsp}.{zwsp}c{zwsp}o{zwsp}m"))
    examples.append(("zero-width", "ZWJ in SSN", f"SSN: 12{zwj}3-45-6789"))
    examples.append(("zero-width", "ZWNJ in phone", f"Phone: +1-555-12{zwnj}3-4567"))
    examples.append(("zero-width", "ZWSP in IP", f"IP: 192{zwsp}.168{zwsp}.1{zwsp}.1"))

    # ── 3. "[at]" / "[dot]" / obscured formats ──────────────────────────
    examples.append(("bracket-obscured", 'email [at]', "john[at]gmail[dot]com"))
    examples.append(("bracket-obscured", 'email (at) (dot)', "john(at)gmail(dot)com"))
    examples.append(("bracket-obscured", 'email {at} {dot}', "john{at}gmail{dot}com"))
    examples.append(("bracket-obscured", 'email AT DOT', "john AT gmail DOT com"))
    examples.append(("bracket-obscured", 'email [@] [.]', "john[@]gmail[.]com"))
    examples.append(("bracket-obscured", 'email <at> <dot>', "john<at>gmail<dot>com"))
    examples.append(("bracket-obscured", 'email [ät] [döt]', "john[ät]example[döt]com"))
    examples.append(("bracket-obscured", 'email at&t-style', "john AT gmail DOT com (with spaces)"))
    examples.append(("bracket-obscured", 'email dot dash', "john-dot-example-dash-com"))

    # ── 4. SSN spoken out ───────────────────────────────────────────────
    examples.append(("ssn-spoken", 'SSN spoken (hyphens)', "one two three dash four five dash six seven eight nine"))
    examples.append(("ssn-spoken", 'SSN spoken (no hyphens)', "one two three four five six seven eight nine"))
    examples.append(("ssn-spoken", 'SSN spoken with "and"', "one-two-three and four-five and six-seven-eight-nine"))
    examples.append(("ssn-spoken", 'SSN as words', "SSN is one twenty three forty five sixty seven eighty nine"))
    examples.append(("ssn-spoken", 'SSN grouped words', "123 is hyphen 45 is hyphen 6789"))

    # ── 5. SSN segmented (spaces, not hyphens) ─────────────────────────
    examples.append(("ssn-segmented", 'SSN with spaces', "SSN: 123 45 6789"))
    examples.append(("ssn-segmented", 'SSN with NBSP', "SSN: 123\u00A045\u00A06789"))
    examples.append(("ssn-segmented", 'SSN with tabs', "SSN: 123\t45\t6789"))
    examples.append(("ssn-segmented", 'SSN with multiple spaces', "SSN: 123   45   6789"))
    examples.append(("ssn-segmented", 'SSN with underscores', "SSN: 123_45_6789"))
    examples.append(("ssn-segmented", 'SSN with mixed spaces', "SSN:  123  45  6789 "))
    examples.append(("ssn-segmented", 'SSN with thin spaces', "SSN: 123\u200945\u20096789"))

    # ── 6. IP as text ───────────────────────────────────────────────────
    examples.append(("ip-text", 'IP spoken simple', "one ninety two dot one sixty eight dot one dot one"))
    examples.append(("ip-text", 'IP spoken with "point"', "one nine two point one six eight point one point one"))
    examples.append(("ip-text", 'IP spoken full', "one hundred ninety two point one hundred sixty eight point zero point one"))
    examples.append(("ip-text", 'IP verbally', "the IP is one ninety two dot one sixty eight dot one dot one"))
    examples.append(("ip-text", 'IPv6 spoken (abbreviated)', "two thousand one colon colon"))

    # ── 7. Credit card with spaces ───────────────────────────────────────
    examples.append(("cc-spaces", 'CC with spaces 4-4-4-4', "CC: 4111 1111 1111 1111"))
    examples.append(("cc-spaces", 'CC with spaces and label', "credit card number: 4111 1111 1111 1111"))
    examples.append(("cc-spaces", 'CC with dots', "CC: 4111.1111.1111.1111"))
    examples.append(("cc-spaces", 'CC with underscores', "CC: 4111_1111_1111_1111"))
    examples.append(("cc-spaces", 'CC with mixed separators', "CC: 4111 1111-1111 1111"))
    examples.append(("cc-spaces", 'CC continuous (no sep)', "CC: 4111111111111111"))
    examples.append(("cc-spaces", 'AMEX with spaces', "CC: 3782 822463 10005"))
    examples.append(("cc-spaces", 'CC spaces and keyword CC#', "cc #: 4111 1111 1111 1111"))
    examples.append(("cc-spaces", 'CC with thin spaces', "Credit card: 4111\u20091111\u20091111\u20091111"))

    # ── 8. Encoded PII — base64 ─────────────────────────────────────────
    examples.append(("encoded", 'base64 email', f"base64: {base64.b64encode(b'john@example.com').decode()}"))
    examples.append(("encoded", 'base64 SSN', f"Encoded: {base64.b64encode(b'123-45-6789').decode()}"))
    examples.append(("encoded", 'base64 phone', f"Encoded: {base64.b64encode(b'+1-555-123-4567').decode()}"))
    examples.append(("encoded", 'base64 IP', f"Encoded IP: {base64.b64encode(b'192.168.1.1').decode()}"))
    examples.append(("encoded", 'base64 credit card', f"Encoded CC: {base64.b64encode(b'4111-1111-1111-1111').decode()}"))
    examples.append(("encoded", 'base64 full address', f"base64 addr: {base64.b64encode(b'john@example.com 123-45-6789').decode()}"))

    # ── 9. Encoded PII — rot13 ─────────────────────────────────────────
    def rot13(s: str) -> str:
        result = []
        for c in s:
            if "a" <= c <= "z":
                result.append(chr((ord(c) - ord("a") + 13) % 26 + ord("a")))
            elif "A" <= c <= "Z":
                result.append(chr((ord(c) - ord("A") + 13) % 26 + ord("A")))
            else:
                result.append(c)
        return "".join(result)

    examples.append(("encoded", 'rot13 email', f"rot13: {rot13('john@example.com')}"))
    examples.append(("encoded", 'rot13 SSN', f"rot13 SSN: {rot13('123-45-6789')}"))
    examples.append(("encoded", 'rot13 credit card', f"rot13 CC: {rot13('4111-1111-1111-1111')}"))
    examples.append(("encoded", 'rot13 phone', f"rot13 phone: {rot13('+1-555-123-4567')}"))
    examples.append(("encoded", 'rot13 IP', f"rot13 IP: {rot13('192.168.1.1')}"))

    # ── 10. HTML entities ───────────────────────────────────────────────
    examples.append(("html-entities", 'email &#64; &#46;', "john&#64;example&#46;com"))
    examples.append(("html-entities", 'all chars as entities', "&#106;&#111;&#104;&#110;&#64;&#101;&#120;&#97;&#109;&#112;&#108;&#101;&#46;&#99;&#111;&#109;"))
    examples.append(("html-entities", 'hex entities email', "john&#x40;example&#x2E;com"))
    examples.append(("html-entities", 'SSN as entities', "&#49;&#50;&#51;&#45;&#52;&#53;&#45;&#54;&#55;&#56;&#57;"))
    examples.append(("html-entities", 'IP as entities', "&#49;&#57;&#50;&#46;&#49;&#54;&#56;&#46;&#49;&#46;&#49;"))
    examples.append(("html-entities", 'phone as entities', "&#43;&#49;&#45;&#53;&#53;&#53;&#45;&#49;&#50;&#51;&#45;&#52;&#53;&#54;&#55;"))

    # ── 11. Split across tokens ─────────────────────────────────────────
    examples.append(("token-split", 'email split +', '"john" + "@" + "example" + "." + "com"'))
    examples.append(("token-split", 'email split concat', '"john" . "@" . "example.com"'))
    examples.append(("token-split", 'IP split +', '"192" + "." + "168" + "." + "1" + "." + "1"'))
    examples.append(("token-split", 'SSN split +', '"123" + "-" + "45" + "-" + "6789"'))
    examples.append(("token-split", 'phone split +', '"+1" + "-" + "555" + "-" + "123" + "-" + "4567"'))
    examples.append(("token-split", 'email code comment', "// email = 'john' + '@' + 'example.com'"))
    examples.append(("token-split", 'email f-string like', "f'{john}@{example}.{com}'"))
    examples.append(("token-split", 'email with pipes', "john | @ | example | . | com"))
    examples.append(("token-split", 'email with / concatenation', "john/\\@/example/./com"))

    # ── 12. URL encoding ────────────────────────────────────────────────
    examples.append(("url-encoded", 'email %40', "john%40example.com"))
    examples.append(("url-encoded", 'email full encoded domain', "john%40example%2Ecom"))
    examples.append(("url-encoded", 'phone %2B', "%2B1-555-123-4567"))
    examples.append(("url-encoded", 'double URL encoding', "john%2540example.com"))
    examples.append(("url-encoded", 'IP with %2E', "192%2E168%2E1%2E1"))

    # ── 13. Unicode control characters / bidi ───────────────────────────
    examples.append(("unicode-tricks", 'bidi LTR override around email', "\u202Esupport@company.com\u202C"))
    examples.append(("unicode-tricks", 'en-dash SSN', "123\u201345\u20136789"))
    examples.append(("unicode-tricks", 'em-dash SSN', "123\u201445\u20146789"))
    examples.append(("unicode-tricks", 'full-width email', "full-width: \uff41\uff4c\uff49\uff43\uff45\uff20\uff41\uff43\uff4d\uff45\uff0e\uff43\uff4f\uff4d"))
    examples.append(("unicode-tricks", 'email with soft hyphen', "john\u00AD@example\u00AD.com"))
    examples.append(("unicode-tricks", 'phone with en-dashes', "+1\u2013555\u2013123\u20134567"))
    examples.append(("unicode-tricks", 'SSN with figure spaces', "123\u200745\u20076789"))
    examples.append(("unicode-tricks", 'SSN with punctuation space', "123\u200845\u20086789"))
    examples.append(("unicode-tricks", 'half-width Roman email', "john\uFF20example\uFF0Ecom"))

    # ── 14. Comments / injection markers ────────────────────────────────
    examples.append(("comments", 'HTML comment in email', "john<!-- comment -->@example.com"))
    examples.append(("comments", 'HTML comment in SSN', "123<!-- -->-45<!-- -->-6789"))
    examples.append(("comments", 'CSS comment in email', "john/* comment */@example.com"))
    examples.append(("comments", 'JS comment in phone', "+1-555-/* */123-4567"))
    examples.append(("comments", 'backtick email', "`alice@acme.com`"))
    examples.append(("comments", 'markdown link mailto:', "[contact](mailto:alice@acme.com)"))
    examples.append(("comments", 'HTML <code> tag', "<code>alice@acme.com</code>"))
    examples.append(("comments", 'JSON escaped \\u0040', "john\\u0040example\\u002Ecom"))
    examples.append(("comments", 'CSS escaped quoted', "'. alice@acme.com'"))
    examples.append(("comments", 'square bracket quoted', "[john@example.com]"))
    examples.append(("comments", 'angle bracket email in text', "<john@example.com>"))
    examples.append(("comments", 'parentheses wrapped email', "(john@example.com)"))

    # ── 15. Reversed / mirrored ─────────────────────────────────────────
    examples.append(("reversed", 'email reversed', "moc.elpmaxe@nhoj"))
    examples.append(("reversed", 'IP reversed', "1.1.168.192"))
    examples.append(("reversed", 'phone reversed', "7654-321-555-1+"))
    examples.append(("reversed", 'SSN reversed', "9876-54-321"))

    # ── 16. Mixed case tricks ───────────────────────────────────────────
    examples.append(("mixed-case", 'email mixed case', "John.Example@Gmail.Com"))
    examples.append(("mixed-case", 'email all caps', "JOHN@EXAMPLE.COM"))
    examples.append(("mixed-case", 'IP with octal-like', "0300.0250.0001.0001"))
    examples.append(("mixed-case", 'SSN with letters inserted', "123-XX-6789"))
    examples.append(("mixed-case", 'email with +tag', "john+spam@example.com"))
    examples.append(("mixed-case", 'email with dots in local', "john.doe.smith@example.com"))

    # ── 17. Whitespace tricks ───────────────────────────────────────────
    examples.append(("whitespace-tricks", 'SSN with leading zeros', "SSN: 000-00-0000"))
    examples.append(("whitespace-tricks", 'SSN with weird spacing around label', "S S N : 123-45-6789"))
    examples.append(("whitespace-tricks", 'email with leading spaces', "  john@example.com"))
    examples.append(("whitespace-tricks", 'phone with irregular spacing', "+1 555   123   4567"))
    examples.append(("whitespace-tricks", 'IP with leading zeros', "192.168.001.001"))

    return examples


# ── Run benchmark ───────────────────────────────────────────────────────────

def categorize(category: str) -> str:
    """Return human-friendly category name."""
    names = {
        "homoglyph": "Homoglyph emails",
        "zero-width": "Zero-width chars",
        "bracket-obscured": '[at]/[dot] formats',
        "ssn-spoken": "SSN spoken out",
        "ssn-segmented": "SSN segmented",
        "ip-text": "IP as text",
        "cc-spaces": "CC with spaces",
        "encoded": "Encoded (base64/rot13)",
        "html-entities": "HTML entities",
        "token-split": "Split across tokens",
        "url-encoded": "URL encoding",
        "unicode-tricks": "Unicode tricks",
        "comments": "Comments/injection",
        "reversed": "Reversed/mirrored",
        "mixed-case": "Mixed case tricks",
        "whitespace-tricks": "Whitespace tricks",
    }
    return names.get(category, category)


def run_benchmark() -> dict[str, Any]:
    """Run benchmark: test through full pipeline + raw regex, return results."""
    patterns = compile_patterns()
    all_examples = build_adversarial_examples()

    # Group by technique category
    categories: dict[str, list[AdversarialExample]] = {}
    for cat, label, text in all_examples:
        categories.setdefault(cat, []).append((cat, label, text))

    results: list[dict[str, Any]] = []
    category_summary: dict[str, dict[str, Any]] = {}

    for cat, label, text in all_examples:
        # Full pipeline (deobfuscator + regex + Luhn)
        full_detections = detect_full_pipeline(text, patterns)
        full_detected = len(full_detections) > 0

        # Raw regex only (no deobfuscation) — baseline
        raw_detections = detect_raw_regex(text, patterns)
        raw_detected = len(raw_detections) > 0

        results.append({
            "category": categorize(cat),
            "label": label,
            "text": repr(text)[1:-1] if any(ord(c) > 127 for c in text) else text,
            "full_pipeline_detected": full_detected,
            "full_detections": [
                {"type": d["type"], "value": d["value"], "score": d["score"]}
                for d in full_detections
            ],
            "raw_regex_detected": raw_detected,
            "raw_detections": [
                {"type": d["type"], "value": d["value"], "score": d["score"]}
                for d in raw_detections
            ],
        })

    # Build category summary
    for cat in categories:
        cat_examples = categories[cat]
        cat_name = categorize(cat)
        cat_results = [r for r in results if r["category"] == cat_name]
        total = len(cat_results)
        full_detected_count = sum(1 for r in cat_results if r["full_pipeline_detected"])
        raw_detected_count = sum(1 for r in cat_results if r["raw_regex_detected"])
        category_summary[cat_name] = {
            "total": total,
            "full_pipeline_detected": full_detected_count,
            "full_pipeline_rate": round(full_detected_count / total * 100, 1) if total > 0 else 0.0,
            "raw_regex_detected": raw_detected_count,
            "raw_regex_rate": round(raw_detected_count / total * 100, 1) if total > 0 else 0.0,
            "improvement": round((full_detected_count - raw_detected_count) / total * 100, 1) if total > 0 else 0.0,
            "missed_examples": [
                r["label"] for r in cat_results if not r["full_pipeline_detected"]
            ],
        }

    overall_total = len(results)
    overall_full = sum(1 for r in results if r["full_pipeline_detected"])
    overall_raw = sum(1 for r in results if r["raw_regex_detected"])

    return {
        "summary": {
            "overall": {
                "total_examples": overall_total,
                "full_pipeline_detected": overall_full,
                "full_pipeline_rate": round(overall_full / overall_total * 100, 1),
                "raw_regex_detected": overall_raw,
                "raw_regex_rate": round(overall_raw / overall_total * 100, 1),
                "deobfuscation_improvement": round((overall_full - overall_raw) / overall_total * 100, 1),
            },
            "by_category": category_summary,
        },
        "entries": results,
    }


def print_summary(data: dict[str, Any]) -> None:
    """Print a formatted summary table with before/after comparison."""
    summary = data["summary"]
    overall = summary["overall"]
    by_cat = summary["by_category"]

    print("=" * 90)
    print("  ADVERSARIAL OBFUSCATION BENCHMARK — Full Pipeline vs Raw Regex")
    print("=" * 90)
    print()
    print(f"  Total examples            : {overall['total_examples']}")
    print(f"  Full pipeline (deob+regex) : {overall['full_pipeline_detected']} ({overall['full_pipeline_rate']}%)")
    print(f"  Raw regex only            : {overall['raw_regex_detected']} ({overall['raw_regex_rate']}%)")
    print(f"  Deobfuscation improvement  : +{overall['deobfuscation_improvement']}%")
    print()

    # Main comparison table
    print(f"  {'Category':35s} {'Total':>5s} {'Full Pipe':>10s} {'Raw':>5s} {'Gain':>6s} {'Bar':>10s}")
    print(f"  {'─'*35} {'─'*5} {'─'*10} {'─'*5} {'─'*6} {'─'*10}")
    for cat_name in sorted(by_cat.keys()):
        c = by_cat[cat_name]
        full_pct = c["full_pipeline_rate"]
        raw_pct = c["raw_regex_rate"]
        bar = "█" * int(full_pct / 10) + "░" * (10 - int(full_pct / 10))
        gain = f"+{c['improvement']:.1f}%" if c["improvement"] > 0 else (" " if c["improvement"] == 0 else f"{c['improvement']:.1f}%")
        print(f"  {cat_name:35s} {c['total']:5d} {full_pct:>7.1f}%  {raw_pct:>4.1f}% {gain:>6s} {bar:>10s}")

    print()
    print(f"  {'OVERALL':35s} {overall['total_examples']:5d} {overall['full_pipeline_rate']:>7.1f}%  {overall['raw_regex_rate']:>4.1f}% +{overall['deobfuscation_improvement']:.1f}%")
    print()

    # ── Category-level gains table (which deobfuscation transforms helped most) ──
    print("  ── Category Deobfuscation Gains ──")
    print()
    gains = sorted(
        [(c["improvement"], cat_name, c) for cat_name, c in by_cat.items()],
        key=lambda x: -x[0],
    )
    for gain_pct, cat_name, c in gains:
        if gain_pct > 0:
            print(f"  ▲ +{gain_pct:.1f}%  {cat_name:35s}  (raw: {c['raw_regex_rate']:.1f}% → full: {c['full_pipeline_rate']:.1f}%)")
        elif gain_pct == 0 and c["full_pipeline_rate"] == 100 and c["raw_regex_rate"] == 100:
            print(f"  ✓ {cat_name:35s}  (already 100% on raw)")
        elif gain_pct == 0:
            print(f"  ● {cat_name:35s}  (no gain — still {c['full_pipeline_rate']:.1f}%)")
        else:
            print(f"  ▼ {gain_pct:.1f}%  {cat_name:35s}  (raw: {c['raw_regex_rate']:.1f}% → full: {c['full_pipeline_rate']:.1f}%)")

    print()
    print("  ── Remaining Misses (full pipeline) ──")
    print()
    has_misses = False
    for cat_name in sorted(by_cat.keys()):
        c = by_cat[cat_name]
        if c["full_pipeline_rate"] < 100.0:
            has_misses = True
            print(f"  ⚠ {cat_name}  ({c['full_pipeline_rate']:.1f}%)")
            for ex in c["missed_examples"]:
                print(f"      ✗ {ex}")
    if not has_misses:
        print("  ✓ All categories at 100%!")

    print()
    print("=" * 90)


def main() -> None:
    data = run_benchmark()

    output_path = PROJECT_ROOT / "benchmarks" / "adversarial-results.json"
    output_path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"Results saved to {output_path}\n")

    print_summary(data)


if __name__ == "__main__":
    main()