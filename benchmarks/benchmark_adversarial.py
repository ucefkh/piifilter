#!/usr/bin/env python3
"""Adversarial Obfuscation Benchmark — measure regex detector against evasive PII formats.

Generates 100+ adversarial examples across 14 evasion categories, runs each
through the regex detector directly (no benchmark harness), and reports the
percentage of each evasion type that is still detected.

Usage:
    .venv/bin/python benchmarks/benchmark_adversarial.py

Output:
    - benchmarks/adversarial-results.json  (full results)
    - STDOUT summary table
"""

from __future__ import annotations

import json
import re
import sys
import base64
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# ── Import regex detector patterns directly ────────────────────────────────
sys.path.insert(0, str(PROJECT_ROOT / "plugins" / "detector-regex" / "src"))
from piifilter_detector_regex.patterns import PATTERN_DEFS
from piifilter.shared.models import EntityType, DetectedEntity

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
        # Fall back to PERSON for types not in the EntityType enum (DATE, etc.)
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
    """Luhn check for credit card validation (mirrors RegexDetector._luhn_valid)."""
    nums = [int(d) for d in digits if d.isdigit()]
    if len(nums) < 13:
        return False
    for i in range(len(nums) - 2, -1, -2):
        nums[i] *= 2
        if nums[i] > 9:
            nums[i] -= 9
    return sum(nums) % 10 == 0


def detect_all(text: str, patterns: list[tuple[EntityType, re.Pattern[str], float]]) -> list[dict[str, Any]]:
    """Run all patterns against text with overlap dedup and Luhn validation."""
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


# ── Adversarial examples ───────────────────────────────────────────────────

AdversarialExample = tuple[str, str, str]
# (category_name, display_label, text)


def obliterate_email(s: str) -> str:
    """Basic email for building variants."""
    return s


def build_adversarial_examples() -> list[AdversarialExample]:
    """Generate 120+ adversarial examples across 14 evasion categories."""
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
    """Run benchmark: compile patterns, test all examples, return results."""
    patterns = compile_patterns()
    all_examples = build_adversarial_examples()

    # Group by technique category
    categories: dict[str, list[AdversarialExample]] = {}
    for cat, label, text in all_examples:
        categories.setdefault(cat, []).append((cat, label, text))

    results: list[dict[str, Any]] = []
    category_summary: dict[str, dict[str, Any]] = {}

    for cat, label, text in all_examples:
        detections = detect_all(text, patterns)
        detected_types = {d["type"] for d in detections}
        is_detected = len(detections) > 0

        results.append({
            "category": categorize(cat),
            "label": label,
            "text": repr(text)[1:-1] if any(ord(c) > 127 for c in text) else text,
            "detected": is_detected,
            "detections": [
                {"type": d["type"], "value": d["value"], "score": d["score"]}
                for d in detections
            ],
        })

    # Build category summary
    for cat in categories:
        cat_examples = categories[cat]
        cat_name = categorize(cat)
        cat_results = [r for r in results if r["category"] == cat_name]
        total = len(cat_results)
        detected_count = sum(1 for r in cat_results if r["detected"])
        category_summary[cat_name] = {
            "total": total,
            "detected": detected_count,
            "missed": total - detected_count,
            "detection_rate": round(detected_count / total * 100, 1) if total > 0 else 0.0,
            "missed_examples": [
                r["label"] for r in cat_results if not r["detected"]
            ],
        }

    overall_total = len(results)
    overall_detected = sum(1 for r in results if r["detected"])

    return {
        "summary": {
            "overall": {
                "total_examples": overall_total,
                "detected": overall_detected,
                "missed": overall_total - overall_detected,
                "detection_rate": round(overall_detected / overall_total * 100, 1),
            },
            "by_category": category_summary,
        },
        "entries": results,
    }


def print_summary(data: dict[str, Any]) -> None:
    """Print a formatted summary table."""
    summary = data["summary"]
    overall = summary["overall"]
    by_cat = summary["by_category"]

    print("=" * 78)
    print("  ADVERSARIAL OBFUSCATION BENCHMARK — Regex Detector")
    print("=" * 78)
    print()
    print(f"  Total examples : {overall['total_examples']}")
    print(f"  Detected       : {overall['detected']} ({overall['detection_rate']}%)")
    print(f"  Missed         : {overall['missed']} ({100 - overall['detection_rate']}%)")
    print()
    print(f"  {'Category':35s} {'Total':>6s} {'Detected':>9s} {'Missed':>7s} {'Rate':>8s}")
    print(f"  {'─'*35} {'─'*6} {'─'*9} {'─'*7} {'─'*8}")
    for cat_name in sorted(by_cat.keys()):
        c = by_cat[cat_name]
        bar = "█" * int(c["detection_rate"] / 10) + "░" * (10 - int(c["detection_rate"] / 10))
        print(f"  {cat_name:35s} {c['total']:6d} {c['detected']:9d} {c['missed']:7d} {c['detection_rate']:6.1f}%  {bar}")

    print()
    print("  ── Evasions that worked (0% detection) ──")
    print()
    for cat_name in sorted(by_cat.keys()):
        c = by_cat[cat_name]
        if c["detection_rate"] == 0.0:
            print(f"  ✗ {cat_name}")
            for ex in c["missed_examples"]:
                print(f"      • {ex}")

    print()
    print("  ── Evasions with partial success ──")
    print()
    for cat_name in sorted(by_cat.keys()):
        c = by_cat[cat_name]
        if c["detection_rate"] > 0.0 and c["detection_rate"] < 100.0:
            print(f"  ⚠ {cat_name}  ({c['detection_rate']:.1f}%)")
            for ex in c["missed_examples"]:
                print(f"      ✗ {ex}")

    print()
    print("  ── Fully detected evasions ──")
    print()
    for cat_name in sorted(by_cat.keys()):
        c = by_cat[cat_name]
        if c["detection_rate"] == 100.0:
            print(f"  ✓ {cat_name}")

    print()
    print("=" * 78)


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