#!/usr/bin/env python3
"""Generate a fresh adversarial PII dataset using LLM (OpenAI-compatible API).

Uses a random seed and new obfuscation strategies (morse code, l33tspeak, emoji
substitution, XML escaping, double encoding, case-shifted) to create an
independent test set — avoiding overfit to the training data patterns.

Output: benchmarks/data/adversarial_v3.json (200+ examples)
"""

from __future__ import annotations

import json
import os
import random
import sys
import re
import time
from pathlib import Path
from typing import Any

from openai import OpenAI

# ── Config ──────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "benchmarks" / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

RANDOM_SEED = random.randint(0, 999999)
random.seed(RANDOM_SEED)

API_BASE_URL = "http://100.114.42.73:8000/v1"
API_KEY = os.environ.get("NEBIUS_API_KEY_DEEPSEEK", "")
MODEL = "/model"

# All 26 entity types
ALL_ENTITY_TYPES = [
    "PERSON", "EMAIL", "PHONE", "ADDRESS", "CITY", "COUNTRY",
    "COMPANY", "BANK_ACCOUNT", "IBAN", "CREDIT_CARD", "PASSPORT",
    "SOCIAL_SECURITY", "JWT", "API_KEY", "SSH_KEY", "DATABASE_URL",
    "PRIVATE_URL", "PROJECT_NAME", "CUSTOMER_NAME", "EMPLOYEE_NAME",
    "GPS", "DOMAIN", "IP_ADDRESS", "FILE_PATH", "DATE", "URL",
]

# NEW obfuscation strategies — deliberately DIFFERENT from the training set
OBFUSCATION_STRATEGIES = [
    "l33tspeak (replace letters with numbers/symbols: e -> 3, a -> 4, o -> 0, i -> 1, s -> 5, t -> 7)",
    "emoji substitution (replace key chars with emoji: @ -> 📧, . -> 🌐, - -> ➖, / -> ➗)",
    "morse code (encode the PII in morse code using dots and dashes with spaces)",
    "XML escaping (use &lt; &gt; &amp; &apos; &quot; XML entities to mask delimiters)",
    "double encoding (URL-encode, then encode the percent signs again: %25 instead of %)",
    "case-shifted (reverse-case all letters: uppercase becomes lowercase and vice versa)",
    "reversed words (reverse the order of words in the string, not character-reverse)",
    "hexadecimal encoding (encode each character as \\xNN hex escapes)",
    "pig-latin style (move first letter to end and add 'ay' before inserting delimiter)",
    "punctuation-stuffed (insert extra punctuation like .. ,, ;; between every character)",
    "fractional characters (use Unicode superscript/subscript digits: ¹²³⁴⁵⁶⁷⁸⁹⁰)",
    "binary encoding (encode PII as binary 8-bit sequences separated by spaces)",
    "circular-shifted (rotate characters by N positions within each segment)",
    "leet-speak extended (use more extreme symbols: @ -> @|, . -> |_|, a -> /-\\, etc.)",
    "unicode fractions (replace digits with vulgar fractions where possible: 1/2, 3/4)",
    "camelCase split (insert capital letters mid-word to break patterns)",
    "zero-width joiner interleaving (insert ZWJ \\u200D between every two characters)",
    "syllabic split (split PII into syllables separated by hyphens or spaces)",
]

# Map entity types to example patterns for the LLM prompts
ENTITY_PROMPT_MAP = {
    "PERSON": "a person's full name",
    "EMAIL": "an email address",
    "PHONE": "a phone number with country code",
    "ADDRESS": "a street address including number and street name",
    "CITY": "a city name",
    "COUNTRY": "a country name",
    "COMPANY": "a company name",
    "BANK_ACCOUNT": "a bank account number (format varies by country)",
    "IBAN": "an IBAN (International Bank Account Number)",
    "CREDIT_CARD": "a credit card number (16 digits, valid Luhn format)",
    "PASSPORT": "a passport number",
    "SOCIAL_SECURITY": "a US Social Security Number (###-##-####)",
    "JWT": "a JWT token (three base64 segments separated by dots)",
    "API_KEY": "an API key (alphanumeric, 32+ chars, may include hyphens)",
    "SSH_KEY": "an SSH private key fingerprint or public key string",
    "DATABASE_URL": "a database connection URL (postgres://user:pass@host:port/db)",
    "PRIVATE_URL": "a private/internal URL (http://192.168.x.x or https://internal.company)",
    "PROJECT_NAME": "a project name (e.g., 'Project Phoenix' or 'DataLake-Migration')",
    "CUSTOMER_NAME": "a customer name (business or individual)",
    "EMPLOYEE_NAME": "an employee name or username",
    "GPS": "GPS coordinates (latitude, longitude)",
    "DOMAIN": "a domain name (e.g., example.com or sub.domain.co.uk)",
    "IP_ADDRESS": "an IPv4 or IPv6 address",
    "FILE_PATH": "a file system path (Unix /var/log/ or Windows C:\\\\Users\\\\)",
    "DATE": "a date in various formats (YYYY-MM-DD, MM/DD/YYYY, etc.)",
    "URL": "a full URL including protocol (https://example.com/path)",
}


def make_client() -> OpenAI:
    return OpenAI(api_key=API_KEY, base_url=API_BASE_URL)


def call_llm(system: str, prompt: str, temperature: float = 0.95) -> str:
    """Call the LLM and return response text. Retries on failure."""
    client = make_client()
    for attempt in range(3):
        try:
            resp = client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                temperature=temperature,
                max_tokens=2000,
            )
            return resp.choices[0].message.content or ""
        except Exception as e:
            if attempt < 2:
                time.sleep(2 ** attempt)
            else:
                print(f"  [WARN] LLM call failed after 3 retries: {e}", file=sys.stderr)
                return ""


def parse_json_from_llm(text: str) -> list[dict[str, Any]]:
    """Extract JSON array from LLM response (handles code fences)."""
    # Strip markdown code fences
    text = re.sub(r"```(?:json)?\s*", "", text)
    text = text.strip()
    # Find the outermost JSON array
    start = text.find("[")
    if start == -1:
        return []
    end = text.rfind("]")
    if end == -1 or end <= start:
        return []
    text = text[start : end + 1]
    try:
        data = json.loads(text)
        if isinstance(data, list):
            return data
        return []
    except json.JSONDecodeError:
        return []


def generate_batch(
    entity_type: str,
    strategy: str,
    count: int = 20,
) -> list[dict[str, Any]]:
    """Generate `count` adversarial PII examples of a single entity type using a strategy."""
    entity_desc = ENTITY_PROMPT_MAP.get(entity_type, entity_type)
    system_msg = (
        "You are a security researcher generating adversarial PII test data. "
        "Output ONLY a valid JSON array. No markdown, no commentary. "
        "Each object MUST have these exact keys: type, strategy, pii_value, ground_truth, text. "
        "The 'text' field MUST be a natural sentence containing the obfuscated PII "
        "where the PII appears in its obfuscated form. The 'ground_truth' field MUST "
        "be the deobfuscated (clean, real) version of the PII. "
        "The 'type' must be exactly the entity type string. 'strategy' is a short name. "
        "Generate REALISTIC examples that look like they came from real data."
    )

    prompt = (
        f"Generate {count} examples of type {entity_type} ({entity_desc}) "
        f"using this obfuscation strategy: **{strategy}**.\n\n"
        f"Use random seed influences: {RANDOM_SEED} (do NOT output the seed).\n\n"
        f"Output format:\n"
        f'[{{"type": "{entity_type}", "strategy": "short-name", '
        f'"pii_value": "obfuscated_PII_here", '
        f'"ground_truth": "the_clean_PII_value", '
        f'"text": "Natural sentence containing the obfuscated PII..."}}]\n\n'
        f"IMPORTANT:\n"
        f"- The pii_value must appear IN the text field as-is\n"
        f"- Use DIFFERENT names/values than: John Smith, Alice Johnson, Acme Corp, example.com, 123-45-6789\n"
        f"- Be creative with the obfuscation — make it truly adversarial\n"
        f"- All {count} examples should be distinct"
    )

    result = call_llm(system_msg, prompt, temperature=0.95 + (RANDOM_SEED % 5) * 0.01)
    examples = parse_json_from_llm(result)

    # Validate and tag each example
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


def load_existing_pii() -> set[str]:
    """Load existing training/adversarial PII values to avoid duplicates."""
    existing = set()
    # Load dataset v2
    v2_path = PROJECT_ROOT / "benchmarks" / "data" / "pii_dataset_v2.json"
    if v2_path.exists():
        try:
            data = json.loads(v2_path.read_text())
            for ex in data.get("examples", []):
                for ent in ex.get("entities", []):
                    existing.add(ent.get("value", "").lower().strip())
        except Exception:
            pass

    # Load dataset v1
    v1_path = PROJECT_ROOT / "benchmarks" / "data" / "pii_dataset.json"
    if v1_path.exists():
        try:
            data = json.loads(v1_path.read_text())
            for ex in data.get("examples", []):
                for ent in ex.get("entities", []):
                    existing.add(ent.get("value", "").lower().strip())
        except Exception:
            pass

    return existing


def main() -> None:
    print(f"╔═══ Fresh Adversarial PII Generator v3 ═══╗")
    print(f"  Random seed:  {RANDOM_SEED}")
    print(f"  Entity types: {len(ALL_ENTITY_TYPES)}")
    print(f"  Strategies:   {len(OBFUSCATION_STRATEGIES)}")
    print(f"╚══════════════════════════════════════════╝")
    print()

    # Load existing PII to skip duplicates
    existing_pii = load_existing_pii()
    print(f"  Loaded {len(existing_pii)} existing PII values to avoid duplication")
    print()

    # Prepare batch generation plan: spread strategies across entity types
    random.shuffle(ALL_ENTITY_TYPES)
    random.shuffle(OBFUSCATION_STRATEGIES)

    all_examples: list[dict[str, Any]] = []
    seen_pii: set[str] = set()

    target_total = 200
    batches: list[tuple[str, str, int]] = []

    # Assign strategies to entity types — each entity gets 1-2 strategies
    strategy_idx = 0
    for entity_type in ALL_ENTITY_TYPES:
        # Each entity type gets at least one strategy
        s1 = OBFUSCATION_STRATEGIES[strategy_idx % len(OBFUSCATION_STRATEGIES)]
        batches.append((entity_type, s1, 8))
        strategy_idx += 1

        # Some get a second strategy
        if strategy_idx % 2 == 0 and strategy_idx < len(OBFUSCATION_STRATEGIES):
            s2 = OBFUSCATION_STRATEGIES[strategy_idx % len(OBFUSCATION_STRATEGIES)]
            batches.append((entity_type, s2, 6))
            strategy_idx += 1

    print(f"  Total batches to generate: {len(batches)}")
    print(f"  Target examples: {target_total}+")
    print()

    # Generate each batch
    total_generated = 0
    total_attempted = 0
    for idx, (entity_type, strategy, count) in enumerate(batches):
        print(f"  [{idx+1}/{len(batches)}] {entity_type} ← {strategy.split('(')[0].strip()} ({count}x) ... ",
              end="", flush=True)

        examples = generate_batch(entity_type, strategy, count)
        total_attempted += count

        # Deduplicate against training set and already-seen
        fresh = []
        for ex in examples:
            pii_lower = ex["pii_value"].lower().strip()
            gt_lower = ex["ground_truth"].lower().strip()
            if pii_lower in existing_pii or gt_lower in existing_pii:
                continue
            if pii_lower in seen_pii:
                continue
            seen_pii.add(pii_lower)
            seen_pii.add(gt_lower)
            fresh.append(ex)

        all_examples.extend(fresh)
        total_generated += len(fresh)
        print(f"{len(fresh)} fresh")

        # Small delay between batches to avoid rate limiting
        time.sleep(0.3)

    print()
    print(f"  Total generated: {total_generated} fresh examples "
          f"(from {total_attempted} attempted)")
    print()

    # If we need more, supplement with remaining strategies
    if total_generated < target_total:
        needed = target_total - total_generated
        print(f"  Need {needed} more examples — supplementing with fallback strategies")
        extra_batches: list[tuple[str, str, int]] = []
        for i in range(0, needed, 10):
            et = ALL_ENTITY_TYPES[i % len(ALL_ENTITY_TYPES)]
            strat = OBFUSCATION_STRATEGIES[(i + idx) % len(OBFUSCATION_STRATEGIES)]
            extra_batches.append((et, strat, 10))

        for idx2, (entity_type, strategy, count) in enumerate(extra_batches):
            print(f"  [supplement {idx2+1}/{len(extra_batches)}] {entity_type} ← {strategy.split('(')[0].strip()} ... ",
                  end="", flush=True)
            examples = generate_batch(entity_type, strategy, count)
            fresh = []
            for ex in examples:
                pii_lower = ex["pii_value"].lower().strip()
                gt_lower = ex["ground_truth"].lower().strip()
                if pii_lower in existing_pii or gt_lower in existing_pii:
                    continue
                if pii_lower in seen_pii:
                    continue
                seen_pii.add(pii_lower)
                fresh.append(ex)
            all_examples.extend(fresh)
            print(f"{len(fresh)} fresh")
            time.sleep(0.3)

    # ── Save ────────────────────────────────────────────────────────────────
    output = {
        "version": "3.0.0",
        "description": (
            f"Fresh adversarial PII dataset v3 — generated with seed {RANDOM_SEED} "
            f"using {len(ALL_ENTITY_TYPES)} entity types and {len(OBFUSCATION_STRATEGIES)} "
            f"new obfuscation strategies. Independent from training data."
        ),
        "seed": RANDOM_SEED,
        "model": MODEL,
        "total_examples": len(all_examples),
        "entity_types": ALL_ENTITY_TYPES,
        "obfuscation_strategies": [s.split("(")[0].strip() for s in OBFUSCATION_STRATEGIES],
        "examples": all_examples,
    }

    output_path = DATA_DIR / "adversarial_v3.json"
    output_path.write_text(json.dumps(output, indent=2, ensure_ascii=False))
    print()
    print(f"💾 Saved {len(all_examples)} examples to {output_path}")
    print(f"   Random seed used: {RANDOM_SEED}")


if __name__ == "__main__":
    main()