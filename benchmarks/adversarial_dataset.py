#!/usr/bin/env python3
"""Adversarial Dataset Generator — creates obfuscated/evaded PII examples.

Generates PII examples using techniques that try to bypass regex-based
detection: homoglyphs, zero-width characters, base64, rot13, URL encoding,
token splitting, HTML/markdown injection, and more.

Usage:
    uv run python benchmarks/adversarial_dataset.py          # print examples only
    uv run python benchmarks/adversarial_dataset.py --save   # append to pii_dataset.json
    uv run python benchmarks/adversarial_dataset.py --save --output benchmarks/data/pii_dataset.json
"""

from __future__ import annotations

import argparse
import base64
import json
import re
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "benchmarks" / "data"
DEFAULT_DATASET = DATA_DIR / "pii_dataset.json"


# ── Obfuscation helpers ──────────────────────────────────────────────────────


def homoglyph_email(local: str, domain: str, tld: str = "com") -> str:
    """Replace ASCII 'o' with Cyrillic 'о' (U+043E) in local part."""
    cyrillic_o = "\u043E"  # Cyrillic small letter о
    obfuscated = local.replace("o", cyrillic_o).replace("O", cyrillic_o)
    return f"{obfuscated}@{domain}.{tld}"


def homoglyph_url(domain: str, tld: str = "com") -> str:
    """Replace 'a' with Cyrillic 'а' (U+0430) in domain name."""
    cyrillic_a = "\u0430"  # Cyrillic small letter а
    obfuscated = domain.replace("a", cyrillic_a)
    return f"https://{obfuscated}.{tld}"


def zero_width_insert(s: str, zwsp: bool = False) -> str:
    """Insert zero-width characters after each character."""
    if zwsp:
        zwc = "\u200B"  # zero-width space
    else:
        zwc = "\u200D"  # zero-width joiner
    return zwc.join(s)


def base64_encode(s: str) -> str:
    """Base64-encode a string."""
    return base64.b64encode(s.encode()).decode()


def rot13(s: str) -> str:
    """Apply ROT13 to ASCII letters."""
    result = []
    for c in s:
        if "a" <= c <= "z":
            result.append(chr((ord(c) - ord("a") + 13) % 26 + ord("a")))
        elif "A" <= c <= "Z":
            result.append(chr((ord(c) - ord("A") + 13) % 26 + ord("A")))
        else:
            result.append(c)
    return "".join(result)


def url_encode(s: str) -> str:
    """URL-encode special chars in a string."""
    encoded = []
    for c in s:
        if c == "@":
            encoded.append("%40")
        elif c == ".":
            encoded.append(".")
        elif c == "+":
            encoded.append("%2B")
        else:
            encoded.append(c)
    return "".join(encoded)


def html_comment_obscure(s: str, insert_pos: int | None = None) -> str:
    """Insert an HTML comment inside a string to break regex matching."""
    if insert_pos is None or insert_pos >= len(s):
        insert_pos = max(1, len(s) // 2)
    return s[:insert_pos] + "<!-- comment -->" + s[insert_pos:]


def markdown_link_obscure(email: str) -> str:
    """Hide email inside a markdown link's URL."""
    return f"[hidden](mailto:{email})"


def html_entity_obscure(s: str) -> str:
    """Obfuscate with HTML entities (&#64; for @, &#46; for .)."""
    return s.replace("@", "&#64;").replace(".", "&#46;")


def snippet_literal(name: str) -> str:
    """Wrap in a code block or backtick literal."""
    return f"`{name}`"


def json_escaped(s: str) -> str:
    """Escape with JSON backslash sequences — \\u0040 for @."""
    result = []
    for c in s:
        if c == "@":
            result.append("\\u0040")
        elif c == ".":
            result.append("\\u002E")
        else:
            result.append(c)
    return "".join(result)


def css_escaped(s: str) -> str:
    """Wrap in CSS-like syntax that breaks simple regex."""
    return f"'. {s}'"


def reversed_string(s: str) -> str:
    """Reverse the string (e.g., 'moc.elpmaxe@nhoj' for 'john@example.com')."""
    return s[::-1]


def split_annotation(s: str, sep: str = " + ") -> str:
    """Show as 'john' + '@' + 'example' + '.' + 'com'."""
    parts: list[str] = []
    buf = ""
    for c in s:
        if c in ("@", "."):
            if buf:
                parts.append(f'"{buf}"')
                buf = ""
            parts.append(f'"{c}"')
        else:
            buf += c
    if buf:
        parts.append(f'"{buf}"')
    return sep.join(parts)


# ── Adversarial example builders ─────────────────────────────────────────────


def make_example(text: str, entities: list[dict[str, Any]]) -> dict[str, Any]:
    """Return a labeled example dict."""
    return {"text": text, "entities": entities}


def build_adversarial_examples() -> list[dict[str, Any]]:
    """Build 28 adversarial examples covering all obfuscation techniques."""
    examples: list[dict[str, Any]] = []

    # ── 1. Homoglyph email (Cyrillic 'о' in local part) ────────────────
    t = "Contact: jоhn@example.com (Cyrillic о instead of Latin o)"
    examples.append(make_example(
        text=t,
        entities=[{"type": "EMAIL", "value": "jоhn@example.com", "start": 9, "end": 24}],
    ))

    # ── 2. Homoglyph email (Cyrillic 'а' in domain) ────────────────────
    t = "Email: test@exаmple.com (Cyrillic а in domain)"
    examples.append(make_example(
        text=t,
        entities=[{"type": "EMAIL", "value": "test@exаmple.com", "start": 7, "end": 23}],
    ))

    # ── 3. Zero-width joiner insertion ──────────────────────────────────
    t = "Reach me at joh\u200dn@example.com (zero-width joiner)"
    examples.append(make_example(
        text=t,
        entities=[{"type": "EMAIL", "value": f"joh\u200dn@example.com", "start": 13, "end": 37}],
    ))

    # ── 4. Zero-width space insertion ───────────────────────────────────
    t = "Email: bob\u200b@\u200bexample.com (zero-width spaces)"
    examples.append(make_example(
        text=t,
        entities=[{"type": "EMAIL", "value": f"bob\u200b@\u200bexample.com", "start": 7, "end": 38}],
    ))

    # ── 5. Base64-encoded email ─────────────────────────────────────────
    t = "Base64: am9obkBleGFtcGxlLmNvbQ== decodes to john@example.com"
    examples.append(make_example(
        text=t,
        entities=[{"type": "EMAIL", "value": "john@example.com", "start": 41, "end": 57}],
    ))

    # ── 6. Base64-encoded SSN ───────────────────────────────────────────
    t = "Encoded SSN: MTIzLTQ1LTY3ODk= decodes to 123-45-6789"
    examples.append(make_example(
        text=t,
        entities=[{"type": "SOCIAL_SECURITY", "value": "123-45-6789", "start": 35, "end": 46}],
    ))

    # ── 7. ROT13-obfuscated email ───────────────────────────────────────
    t = "ROT13: wbua@rknzcyr.pbz (john@example.com)"
    examples.append(make_example(
        text=t,
        entities=[{"type": "EMAIL", "value": "wbua@rknzcyr.pbz", "start": 7, "end": 23}],
    ))

    # ── 8. ROT13-obfuscated credit card ─────────────────────────────────
    t = "ROT13 CC: 4VVV-VVVV-VVVV-VVGK (4111-1111-1111-1111)"
    examples.append(make_example(
        text=t,
        entities=[{"type": "CREDIT_CARD", "value": "4VVV-VVVV-VVVV-VVGK", "start": 9, "end": 28}],
    ))

    # ── 9. URL-encoded email ────────────────────────────────────────────
    t = "URL-encoded: john%40example.com"
    examples.append(make_example(
        text=t,
        entities=[{"type": "EMAIL", "value": "john%40example.com", "start": 14, "end": 31}],
    ))

    # ── 10. URL-encoded phone ────────────────────────────────────────────
    t = "URL-encoded phone: %2B1-555-123-4567"
    examples.append(make_example(
        text=t,
        entities=[{"type": "PHONE", "value": "%2B1-555-123-4567", "start": 19, "end": 36}],
    ))

    # ── 11. Token-split email (string concatenation) ────────────────────
    t = 'Token split: "john" + "@" + "example.com"'
    examples.append(make_example(
        text=t,
        entities=[{"type": "EMAIL", "value": "john@example.com", "start": 28, "end": 56}],
    ))

    # ── 12. Token-split IP address ─────────────────────────────────────
    t = 'IP split: "192" + "." + "168" + "." + "1" + "." + "1"'
    examples.append(make_example(
        text=t,
        entities=[{"type": "IP_ADDRESS", "value": "192.168.1.1", "start": 23, "end": 57}],
    ))

    # ── 13. HTML comment injected into email ──────────────────────────
    t = "Hidden: john<!--comment-->@example.com"
    examples.append(make_example(
        text=t,
        entities=[{"type": "EMAIL", "value": "john@example.com", "start": 8, "end": 42}],
    ))

    # ── 14. Markdown link wrapping email ──────────────────────────────
    t = "Send to [contact](mailto:alice@acme.com) for info"
    examples.append(make_example(
        text=t,
        entities=[{"type": "EMAIL", "value": "alice@acme.com", "start": 23, "end": 37}],
    ))

    # ── 15. HTML entity encoding on email ─────────────────────────────
    t = "HTML entities: john&#64;example&#46;com"
    examples.append(make_example(
        text=t,
        entities=[{"type": "EMAIL", "value": "john&#64;example&#46;com", "start": 15, "end": 38}],
    ))

    # ── 16. Backtick code-fenced PII ─────────────────────────────────
    t = "Code: `alice@acme.com` in backticks"
    examples.append(make_example(
        text=t,
        entities=[{"type": "EMAIL", "value": "alice@acme.com", "start": 7, "end": 21}],
    ))

    # ── 17. JSON-escaped unicode ──────────────────────────────────────
    t = "JSON escaped: john\\u0040example\\u002Ecom"
    examples.append(make_example(
        text=t,
        entities=[{"type": "EMAIL", "value": "john\\u0040example\\u002Ecom", "start": 15, "end": 41}],
    ))

    # ── 18. Reversed email string ─────────────────────────────────────
    t = "Reversed: moc.elpmaxe@nhoj (decodes to john@example.com)"
    examples.append(make_example(
        text=t,
        entities=[{"type": "EMAIL", "value": "john@example.com", "start": 41, "end": 57}],
    ))

    # ── 19. CSS-escaped / quoted PII ──────────────────────────────────
    t = "CSS: '. alice@acme.com' is a quoted email"
    examples.append(make_example(
        text=t,
        entities=[{"type": "EMAIL", "value": "alice@acme.com", "start": 7, "end": 22}],
    ))

    # ── 20. Homoglyph phone (Cyrillic digit-like chars) ───────────────
    t = "Phone: +1-555-123-4\u04e697 (Cyrillic Ҧ instead of 5)"
    examples.append(make_example(
        text=t,
        entities=[{"type": "PHONE", "value": "+1-555-123-4\u04e697", "start": 7, "end": 23}],
    ))

    # ── 21. Mixed case + whitespace variants ──────────────────────────
    t = "Ssn: 123-45-6789  (with irregular spacing)"
    examples.append(make_example(
        text=t,
        entities=[{"type": "SOCIAL_SECURITY", "value": "123-45-6789", "start": 5, "end": 16}],
    ))

    # ── 22. Full-width unicode email (ｆｕｌｌｗｉｄｔｈ) ──────────────
    t = "Full-width: ａｌｉｃｅ＠ａｃｍｅ．ｃｏｍ"
    examples.append(make_example(
        text=t,
        entities=[{"type": "EMAIL", "value": "ａｌｉｃｅ＠ａｃｍｅ．ｃｏｍ", "start": 12, "end": 34}],
    ))

    # ── 23. Email with trailing dot / special chars after TLD ──────────
    t = "Trailing dot: test@example.com. (period after domain)"
    examples.append(make_example(
        text=t,
        entities=[{"type": "EMAIL", "value": "test@example.com", "start": 15, "end": 31}],
    ))

    # ── 24. Bidi override / unicode control chars around email ────────
    t = "Bidi: \u202Esupport@company.com\u202C (with LTR override marks)"
    examples.append(make_example(
        text=t,
        entities=[{"type": "EMAIL", "value": "support@company.com", "start": 7, "end": 34}],
    ))

    # ── 25. HTML <code> tag wrapping PII ──────────────────────────────
    t = "HTML code: <code>alice@acme.com</code> in HTML snippet"
    examples.append(make_example(
        text=t,
        entities=[{"type": "EMAIL", "value": "alice@acme.com", "start": 13, "end": 27}],
    ))

    # ── 26. Phone with unicode dash equivalents ────────────────────────
    t = "Phone: +1\u2013555\u2013123\u20134567 (en-dashes instead of hyphens)"
    examples.append(make_example(
        text=t,
        entities=[{"type": "PHONE", "value": "+1\u2013555\u2013123\u20134567", "start": 7, "end": 25}],
    ))

    # ── 27. SSN with unicode spaces ────────────────────────────────────
    t = "SSN: 123\u00A045\u00A06789 (non-breaking spaces)"
    examples.append(make_example(
        text=t,
        entities=[{"type": "SOCIAL_SECURITY", "value": "123\u00A045\u00A06789", "start": 5, "end": 18}],
    ))

    # ── 28. Split annotation in code comment ──────────────────────────
    t = "// email = 'john' + '@' + 'example.com'"
    examples.append(make_example(
        text=t,
        entities=[{"type": "EMAIL", "value": "john@example.com", "start": 22, "end": 53}],
    ))

    return examples


# ── Save / append to dataset ─────────────────────────────────────────────────


def append_to_dataset(
    new_examples: list[dict[str, Any]],
    dataset_path: Path = DEFAULT_DATASET,
) -> dict[str, Any]:
    """Load existing dataset, append adversarial examples, save back."""
    raw = json.loads(dataset_path.read_text(encoding="utf-8"))
    count_before = len(raw["examples"])
    raw["examples"].extend(new_examples)
    raw["version"] = bump_version(raw.get("version", "1.0.0"))
    raw["description"] += (
        f" (adversarial subset: {count_before + 1}–{len(raw['examples'])}"
        f" — {len(new_examples)} obfuscated PII examples)"
    )
    dataset_path.write_text(
        json.dumps(raw, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"  Appended {len(new_examples)} adversarial examples to {dataset_path}")
    print(f"  Total examples: {count_before} → {len(raw['examples'])}")
    return raw


def bump_version(v: str) -> str:
    """Bump minor version: 1.1.0 → 1.2.0."""
    parts = v.split(".")
    if len(parts) == 3:
        parts[1] = str(int(parts[1]) + 1)
        parts[2] = "0"
    return ".".join(parts)


# ── CLI ──────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate adversarial PII detection examples"
    )
    parser.add_argument(
        "--save",
        action="store_true",
        help="Append examples to the dataset file",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=str(DEFAULT_DATASET),
        help=f"Dataset file path (default: {DEFAULT_DATASET})",
    )
    args = parser.parse_args()

    examples = build_adversarial_examples()

    if args.save:
        dataset_path = Path(args.output)
        dataset_path.parent.mkdir(parents=True, exist_ok=True)
        append_to_dataset(examples, dataset_path)
    else:
        print(f"Generated {len(examples)} adversarial examples:\n")
        for i, ex in enumerate(examples, 1):
            print(f"  #{i:2d}: {ex['text'][:90]}")
            for ent in ex["entities"]:
                print(f"        → {ent['type']}: \"{ent['value'][:50]}\" [{ent['start']}:{ent['end']}]")
            print()

    print(f"Total adversarial examples: {len(examples)}")


if __name__ == "__main__":
    main()