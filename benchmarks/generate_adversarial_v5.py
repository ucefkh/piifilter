#!/usr/bin/env python3
"""Generate adversarial PII dataset v5 — DeepSeek API, DIFFERENT seed, 10 new strategies.

Strategies: tape-encoding, ASCII art, braille characters, subscript/superscript,
CSV injection, HTML entity decimal, backtick wrapping, doubled chars, reduction cipher,
half-width katakana.

Output: benchmarks/data/adversarial_v5.json (200+ examples)
"""

from __future__ import annotations

import json
import os
import random
import sys
import time
from pathlib import Path
from typing import Any

from openai import OpenAI

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "benchmarks" / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Deliberately DIFFERENT seed from v4 (which uses random.randint independently)
RANDOM_SEED = random.randint(0, 999999)
while RANDOM_SEED < 500000:
    RANDOM_SEED = random.randint(0, 999999)
random.seed(RANDOM_SEED)

API_BASE_URL = "http://100.114.42.73:8000/v1"
API_KEY = os.environ.get("NEBIUS_API_KEY_DEEPSEEK", "")
MODEL = "/model"

ALL_ENTITY_TYPES = [
    "PERSON", "EMAIL", "PHONE", "ADDRESS", "CITY", "COUNTRY",
    "COMPANY", "BANK_ACCOUNT", "IBAN", "CREDIT_CARD", "PASSPORT",
    "SOCIAL_SECURITY", "JWT", "API_KEY", "SSH_KEY", "DATABASE_URL",
    "PRIVATE_URL", "PROJECT_NAME", "CUSTOMER_NAME", "EMPLOYEE_NAME",
    "GPS", "DOMAIN", "IP_ADDRESS", "FILE_PATH", "DATE", "URL",
]

# COMPLETELY DIFFERENT strategies from v4
OBFUSCATION_STRATEGIES = [
    "tape-encoding (represent PII as a sequence of magnetic stripe / paper tape codes using █ ▓ ▒ ░ █ characters)",
    "ASCII art (render each character as a small ASCII art block using █ and spaces)",
    "braille characters (replace digits/letters with lookalike braille patterns U+2800-U+28FF)",
    "subscript/superscript (use Unicode subscript/supercript digits: ₀₁₂₃₄₅₆₇₈₉ and other small characters)",
    "CSV injection (embed PII inside =HYPERLINK() formulas or CSV injection payloads like @SUM)",
    "HTML entity decimal (encode every character as &#NNN; decimal HTML entities)",
    "backtick wrapping (wrap PII in backticks like `email` or markdown inline code markers)",
    "doubled characters (double every character: jjoohhnn@@eexxaammppllee..ccoomm)",
    "reduction cipher (replace each letter with the preceding letter in alphabet: b→a, c→b, etc.)",
    "half-width katakana (use half-width katakana Unicode chars ｱｲｳｴｵ to represent text)",
]

ENTITY_PROMPT_MAP = {
    "PERSON": "a person's full name",
    "EMAIL": "an email address",
    "PHONE": "a phone number with country code",
    "ADDRESS": "a street address including number and street name",
    "CITY": "a city name",
    "COUNTRY": "a country name",
    "COMPANY": "a company name",
    "BANK_ACCOUNT": "a bank account number",
    "IBAN": "an IBAN",
    "CREDIT_CARD": "a credit card number (16 digits, valid Luhn format)",
    "PASSPORT": "a passport number",
    "SOCIAL_SECURITY": "a US SSN (###-##-####)",
    "JWT": "a JWT token",
    "API_KEY": "an API key (alphanumeric, 32+ chars)",
    "SSH_KEY": "an SSH key fingerprint or public key string",
    "DATABASE_URL": "a database connection URL",
    "PRIVATE_URL": "a private/internal URL",
    "PROJECT_NAME": "a project name",
    "CUSTOMER_NAME": "a customer name",
    "EMPLOYEE_NAME": "an employee name or username",
    "GPS": "GPS coordinates (latitude, longitude)",
    "DOMAIN": "a domain name",
    "IP_ADDRESS": "an IPv4 or IPv6 address",
    "FILE_PATH": "a file system path",
    "DATE": "a date in various formats",
    "URL": "a full URL including protocol",
}


def make_client() -> OpenAI:
    return OpenAI(api_key=API_KEY, base_url=API_BASE_URL)


def call_llm(system: str, prompt: str) -> str:
    """Call LLM and return response text. Retries on failure."""
    client = make_client()
    for attempt in range(3):
        try:
            resp = client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.95,
                max_tokens=2000,
                seed=RANDOM_SEED,
            )
            return resp.choices[0].message.content or ""
        except Exception as e:
            if attempt < 2:
                time.sleep(2 ** attempt)
            else:
                print(f"  [WARN] LLM call failed after 3 retries: {e}", file=sys.stderr)
                return ""


def parse_json(text: str) -> list[dict[str, Any]]:
    """Extract JSON array from LLM response."""
    import re as _re
    text = _re.sub(r"```(?:json)?\s*", "", text).strip()
    start = text.find("[")
    if start == -1:
        return []
    end = text.rfind("]")
    if end <= start:
        return []
    text = text[start:end + 1]
    try:
        data = json.loads(text)
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []


def generate_batch(entity_type: str, strategy: str, count: int = 20) -> list[dict[str, Any]]:
    """Generate `count` adversarial examples for one entity type + strategy."""
    entity_desc = ENTITY_PROMPT_MAP.get(entity_type, entity_type)
    system_msg = (
        "You are a security researcher generating adversarial PII test data. "
        "Output ONLY a valid JSON array. No markdown, no commentary. "
        "Each object MUST have these exact keys: type, strategy, pii_value, ground_truth, text. "
        "The 'text' field MUST be a natural sentence containing the obfuscated PII. "
        "The 'ground_truth' field MUST be the clean PII value. "
        "Generate REALISTIC examples. Use DIFFERENT names/values than: John Smith, "
        "Alice Johnson, Acme Corp, example.com, 123-45-6789."
    )
    prompt = (
        f"Generate {count} examples of type {entity_type} ({entity_desc}) "
        f"using this obfuscation strategy: **{strategy}**. "
        f"Seed influence: {RANDOM_SEED}. "
        f"Output format:\n"
        f'[{{"type": "{entity_type}", "strategy": "short-name", '
        f'"pii_value": "obfuscated_PII_here", '
        f'"ground_truth": "the_clean_PII_value", '
        f'"text": "Natural sentence containing the obfuscated PII..."}}]\n\n'
        f"All {count} examples must be distinct."
    )
    result = call_llm(system_msg, prompt)
    examples = parse_json(result)
    validated = []
    for ex in examples:
        if not isinstance(ex, dict):
            continue
        ex.setdefault("type", entity_type)
        ex.setdefault("strategy", "custom")
        ex.setdefault("pii_value", "")
        ex.setdefault("ground_truth", "")
        ex.setdefault("text", "")
        ex["seed"] = RANDOM_SEED
        if ex["pii_value"] and ex["text"] and ex["ground_truth"]:
            validated.append(ex)
    return validated


def main() -> None:
    print(f"╔═══ Adversarial PII Generator v5 ═══╗")
    print(f"  Random seed:  {RANDOM_SEED}")
    print(f"  API:          DeepSeek (port 30000)")
    print(f"  Strategies:   {len(OBFUSCATION_STRATEGIES)} new strategies")
    print(f"╚════════════════════════════════════╝\n")

    random.shuffle(ALL_ENTITY_TYPES)
    shuffled_strats = OBFUSCATION_STRATEGIES[:]
    random.shuffle(shuffled_strats)

    all_examples: list[dict[str, Any]] = []
    seen_pii: set[str] = set()

    batches: list[tuple[str, str, int]] = []
    for i, et in enumerate(ALL_ENTITY_TYPES):
        strat = shuffled_strats[i % len(shuffled_strats)]
        batches.append((et, strat, 8))
        if i % 3 == 1:
            s2 = shuffled_strats[(i + 5) % len(shuffled_strats)]
            batches.append((et, s2, 6))

    print(f"  Batches: {len(batches)}, target: 200+ examples\n")

    total_generated = 0
    for idx, (entity_type, strategy, count) in enumerate(batches):
        print(f"  [{idx + 1}/{len(batches)}] {entity_type} ← {strategy.split('(')[0].strip()} ({count}x) ... ", end="", flush=True)
        examples = generate_batch(entity_type, strategy, count)
        fresh = []
        for ex in examples:
            pii_lower = ex["pii_value"].lower().strip()
            gt_lower = ex["ground_truth"].lower().strip()
            if pii_lower in seen_pii or gt_lower in seen_pii:
                continue
            seen_pii.add(pii_lower)
            seen_pii.add(gt_lower)
            fresh.append(ex)
        all_examples.extend(fresh)
        total_generated += len(fresh)
        print(f"{len(fresh)} fresh ({total_generated} total)")
        time.sleep(0.5)

    print()

    if total_generated < 200:
        needed = 200 - total_generated
        print(f"  Supplementing with {needed} more examples...")
        extra_batches: list[tuple[str, str, int]] = []
        for i in range(0, needed, 10):
            et = ALL_ENTITY_TYPES[i % len(ALL_ENTITY_TYPES)]
            strat = shuffled_strats[(i + idx) % len(shuffled_strats)]
            extra_batches.append((et, strat, 10))
        for idx2, (entity_type, strategy, count) in enumerate(extra_batches):
            print(f"  [sup {idx2 + 1}/{len(extra_batches)}] {entity_type} ← ... ", end="", flush=True)
            examples = generate_batch(entity_type, strategy, count)
            fresh = []
            for ex in examples:
                pii_lower = ex["pii_value"].lower().strip()
                gt_lower = ex["ground_truth"].lower().strip()
                if pii_lower in seen_pii or gt_lower in seen_pii:
                    continue
                seen_pii.add(pii_lower)
                seen_pii.add(gt_lower)
                fresh.append(ex)
            all_examples.extend(fresh)
            print(f"{len(fresh)} fresh")
            time.sleep(0.5)

    output = {
        "version": "5.0.0",
        "description": (
            f"Adversarial PII dataset v5 — DeepSeek, seed {RANDOM_SEED}, "
            f"{len(ALL_ENTITY_TYPES)} entity types, 10 different strategies from v4."
        ),
        "seed": RANDOM_SEED,
        "model": MODEL,
        "api_base": API_BASE_URL,
        "total_examples": len(all_examples),
        "entity_types": ALL_ENTITY_TYPES,
        "obfuscation_strategies": [s.split("(")[0].strip() for s in OBFUSCATION_STRATEGIES],
        "examples": all_examples,
    }
    output_path = DATA_DIR / "adversarial_v5.json"
    output_path.write_text(json.dumps(output, indent=2, ensure_ascii=False))
    print(f"\n💾 Saved {len(all_examples)} examples to {output_path}")
    print(f"   Seed: {RANDOM_SEED}")


if __name__ == "__main__":
    main()