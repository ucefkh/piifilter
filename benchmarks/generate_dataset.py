#!/usr/bin/env python3
"""PII Dataset Generator — expands the labeled dataset to 2000+ examples
including adversarial variants for every entity type.

Adversarial variants cover:
  - EMAIL: [at]/[dot]/HTML entity/zero-width obfuscation
  - SSN: base64/segmented/spoken forms
  - PHONE: dashed/unicode-dash variants
  - CREDIT_CARD: space-separated/continuous/dot-separated variants
  - URL: encoded/deobfuscatable variants
  - IP: text/dot-separated variants
  - All other types get format obfuscation variants too

Usage:
    uv run python benchmarks/generate_dataset.py          # dry-run: print counts
    uv run python benchmarks/generate_dataset.py --save    # save to pii_dataset_v2.json (overwrite)
    uv run python benchmarks/generate_dataset.py --save --output benchmarks/data/my_dataset.json
"""

from __future__ import annotations

import argparse
import base64
import copy
import html
import json
import random
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "benchmarks" / "data"
DEFAULT_SOURCE = DATA_DIR / "pii_dataset.json"
DEFAULT_OUTPUT = DATA_DIR / "pii_dataset_v2.json"

random.seed(42)

# ═══════════════════════════════════════════════════════════════════════════════
#  PII value pools — diverse, realistic values for every entity type
# ═══════════════════════════════════════════════════════════════════════════════

FIRST_NAMES = [
    "Alice", "Bob", "Charlie", "Diana", "Edward", "Fiona", "George", "Hannah",
    "Ivan", "Julia", "Kevin", "Laura", "Michael", "Nina", "Oliver", "Patricia",
    "Quinn", "Rachel", "Samuel", "Tina", "Uma", "Victor", "Wendy", "Xavier",
    "Yara", "Zack", "Aaron", "Bella", "Carlos", "Deepa", "Erik", "Fatima",
    "Gopal", "Hiro", "Ingrid", "Jamal", "Kai", "Lena", "Ming", "Noa",
    "Omar", "Priya", "Ravi", "Sofia", "Tariq", "Usman", "Val", "Wei",
    "Xia", "Yuki", "Amir", "Beth", "Cheng", "Dalia", "Elif", "Felix",
    "Grace", "Hugo", "Isla", "Joon",
]

LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller",
    "Davis", "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez", "Wilson",
    "Anderson", "Thomas", "Taylor", "Moore", "Jackson", "Martin", "Lee",
    "Perez", "Thompson", "White", "Harris", "Sanchez", "Clark", "Ramirez",
    "Lewis", "Robinson", "Walker", "Young", "Allen", "King", "Wright",
    "Scott", "Torres", "Nguyen", "Hill", "Flores", "Green", "Adams",
    "Nelson", "Baker", "Hall", "Rivera", "Campbell", "Mitchell", "Carter",
    "Patel", "Rogers", "Coleman", "Morgan", "Cooper", "Reed", "Bailey",
]

COMPANIES = [
    "Acme Corp", "Globex Inc", "Initech", "Hooli", "Stark Industries",
    "Wayne Enterprises", "Cyberdyne Systems", "Umbrella Corp", "Soylent Corp",
    "Massive Dynamic", "Wonka Industries", "Oscorp", "LexCorp", "Tyrell Corp",
    "Weyland-Yutani", "Buy n Large", "Oceanic Airlines", "Dunder Mifflin",
    "Pied Piper", "Aviato", "Google", "Microsoft", "Amazon", "Meta",
    "Apple", "OpenAI", "Tesla", "SpaceX", "Netflix", "Spotify",
]

CITIES = [
    "New York", "London", "Tokyo", "Paris", "Berlin", "Sydney", "Mumbai",
    "Shanghai", "Dubai", "Singapore", "San Francisco", "Seattle", "Boston",
    "Austin", "Toronto", "Vancouver", "Amsterdam", "Barcelona", "Rome",
    "Chicago", "Los Angeles", "Miami", "Denver", "Portland", "Oslo",
    "Stockholm", "Copenhagen", "Zurich", "Dublin", "Melbourne",
]

COUNTRIES = [
    "USA", "Canada", "UK", "Germany", "France", "Japan", "Australia",
    "Brazil", "India", "China", "Singapore", "South Korea", "Netherlands",
    "Sweden", "Norway", "Switzerland", "Spain", "Italy", "Mexico", "Egypt",
    "Nigeria", "Kenya", "Argentina", "Chile", "New Zealand", "Ireland",
]

DOMAINS = [
    "example.com", "acme.com", "mail.company.io", "mail-server.co.jp",
    "bigpharma.com", "weeping-angels.com", "temp-services.co.uk",
    "torchwood.xyz", "company.org", "startup.io", "techcorp.dev",
    "mycompany.net", "enterprise.cloud", "data-service.ai",
]

EMAIL_LOCALS = [
    "alice", "bob", "charlie", "diana", "edward", "fiona", "george",
    "test", "user", "admin", "info", "contact", "support", "sales",
    "hello", "team", "dev", "ops", "noreply", "feedback",
]

STREET_NAMES = [
    "Maple Drive", "Oak Avenue", "Elm Street", "Pine Road", "Cedar Lane",
    "Birch Boulevard", "Willow Way", "Main Street", "Park Avenue", "Lake Drive",
    "River Road", "High Street", "Church Road", "Station Road", "Green Lane",
]

ZIP_CODES = ["10001", "94102", "60601", "90001", "02101", "98101", "77001",
             "85001", "33101", "80201", "20001", "48201", "55401", "19106"]

# ── format variation helpers ──────────────────────────────────────────────────


def fmt_email(local: str, domain: str) -> str:
    variants = [
        f"{local}@{domain}",
        f"{local}.{local[:3]}@{domain}",
        f"{local}_{domain.split('.')[0]}@{domain}",
        f"{local}+tag@{domain}",
    ]
    return random.choice(variants)


def fmt_phone(country: str, number: str) -> str:
    variants = [
        f"+{country}-{number[0:3]}-{number[3:6]}-{number[6:]}",
        f"({country}) {number[0:3]} {number[3:6]}-{number[6:]}",
        f"{number[0:3]}.{number[3:6]}.{number[6:]}",
        f"{number[0:3]}-{number[3:6]}-{number[6:]}",
        f"+{country}{number[0:3]}{number[3:6]}{number[6:]}",
    ]
    return random.choice(variants)


def fmt_ssn(area: str, group: str, serial: str) -> str:
    return random.choice([
        f"{area}-{group}-{serial}",
        f"{area}{group}{serial}",
        f"{area}.{group}.{serial}",
        f"{area} {group} {serial}",
    ])


def fmt_credit_card(digits: str) -> str:
    groups = [digits[i:i+4] for i in range(0, len(digits), 4)]
    return random.choice([
        "-".join(groups),
        " ".join(groups),
        "".join(groups),
        "  ".join(groups),
    ])


def fmt_ip(octets: list[str]) -> str:
    return random.choice([
        ".".join(octets),
        ". ".join(octets),
    ])


def fmt_address(num: str, street: str, city: str, state: str, zip_code: str, country: str) -> str:
    variants = [
        f"{num} {street}, {city}, {state} {zip_code}, {country}",
        f"{num} {street}, {city}, {state} {zip_code}",
        f"{num} {street}, {city}, {country}",
        f"{street}, #{num}, {city}, {state} {zip_code}",
    ]
    return random.choice(variants)


# ═══════════════════════════════════════════════════════════════════════════════
#  ADVERSARIAL VARIANT GENERATORS
# ═══════════════════════════════════════════════════════════════════════════════

ZERO_WIDTH_CHARS = ["\u200b", "\u200c", "\u200d", "\ufeff"]  # zero-width space, ZWNJ, ZWJ, BOM


def adversarial_email_variants(value: str) -> list[str]:
    """Generate adversarial obfuscations of an email address."""
    variants = []

    # Handle emails that don't have '@' (already obfuscated)
    if "@" not in value:
        # Already an obfuscated email — generate other forms
        # Try to extract local-ish and domain-ish parts
        # Just return the value with some additional obfuscation
        variants.append(value.replace("%40", " [at] "))
        variants.append(value.replace("&#64;", " [at] "))
        variants.append(value.replace("\\\\u0040", "[at]"))
        variants.append(base64.b64encode(value.encode()).decode())
        return variants

    local, domain = value.split("@", 1)

    # [at] / [dot] variants
    variants.append(f"{local} [at] {domain}")
    variants.append(f"{local}[at]{domain}")
    variants.append(f"{local} @ {domain.replace('.', ' [dot] ')}")
    variants.append(f"{local}@{domain.replace('.', ' [dot] ')}")

    # HTML entity variants
    variants.append(f"{local} &#64; {domain}")
    variants.append(f"{local} &#x40;{domain}")
    variants.append(f"{local} &#046; {domain.replace('.', ' &#46; ')}")

    # Zero-width character insertion — insert ZW chars between chars of local part
    for _ in range(2):
        zw = random.choice(ZERO_WIDTH_CHARS)
        zw_local = zw.join(list(local))
        dot_idx = domain.find('.')
        if dot_idx > 0:
            zw_domain = domain[:dot_idx] + zw + domain[dot_idx:]
        else:
            zw_domain = domain
        variants.append(f"{zw_local}@{zw_domain}")

    # Partial redaction / obfuscation
    if len(local) > 3:
        variants.append(f"{local[0]}***{local[-1]}@{domain}")
        variants.append(f"{local[0]}{'*' * (len(local)-2)}{local[-1]}@{domain}")

    # Unicode homoglyph substitution
    homoglyph_map = {'a': 'α', 'e': 'е', 'o': 'ο', 'c': 'с', 'i': 'і', 'l': 'ӏ'}
    homoglyph_local = ''.join(homoglyph_map.get(c, c) for c in local)
    if homoglyph_local != local:
        variants.append(f"{homoglyph_local}@{domain}")

    return variants


def adversarial_ssn_variants(value: str) -> list[str]:
    """Generate adversarial obfuscations of an SSN."""
    digits = re.sub(r'[^0-9]', '', value)
    if len(digits) < 9:
        # Try to pad with zeros or just return what we can
        # Partial digits
        if len(digits) >= 4:
            last4 = digits[-4:]
            variants = [
                f"XXX-XX-{last4}",
                f"***-**-{last4}",
                base64.b64encode(digits.encode()).decode(),
                " ".join(list(digits)),
            ]
            return variants
        return [value]

    area = digits[:3]
    group = digits[3:5]
    serial = digits[5:]

    variants = []

    # Spoken form
    variants.append(f"{area} {group} {serial} (segmented)")
    variants.append(f"area {area} group {group} serial {serial}")
    variants.append(f"SSN {digits[0]}XX-XX-{digits[5:]}")

    # Base64-encoded
    variants.append(base64.b64encode(digits.encode()).decode())
    variants.append(base64.b64encode(f"{area}-{group}-{serial}".encode()).decode())

    # Hex encoded
    variants.append(digits.encode().hex())

    # Roman numerals (just for fun - the numeric value)
    variants.append(f"{int(area)}-{int(group)}-{int(serial)}")

    # Reversed
    variants.append(f"{serial}-{group}-{area}")

    # With spaces between every digit
    variants.append(" ".join(list(digits)))

    # Partial masked
    if len(digits) >= 4:
        variants.append(f"XXX-XX-{digits[5:]}")
        variants.append(f"***-**-{digits[5:]}")

    return variants


def adversarial_phone_variants(value: str) -> list[str]:
    """Generate adversarial obfuscations of a phone number."""
    digits = re.sub(r'[^0-9]', '', value)
    variants = []

    # Unicode dashes
    unicode_dashes = ["\u2013", "\u2014", "\u2212"]  # en-dash, em-dash, minus
    for dash in unicode_dashes:
        if "-" in value:
            variants.append(value.replace("-", dash))

    # All continuous
    variants.append(digits)

    # Space-separated in groups of 2
    variants.append(" ".join([digits[i:i+2] for i in range(0, len(digits), 2)]))

    # Fully dotted
    if "-" in value:
        variants.append(value.replace("-", "."))

    # Slug format
    variants.append(f"tel:{digits}")

    # International prefix variations
    variants.append(digits.replace("+", "00"))
    if "+" in value:
        variants.append(value.replace("+", ""))

    # Parentheses around area code variations
    if len(digits) >= 10:
        variants.append(f"({digits[0:3]}) {digits[3:6]}-{digits[6:]}")

    # Spaces instead of dashes
    if "-" in value:
        variants.append(value.replace("-", " "))
        variants.append(value.replace("-", "  "))

    return variants


def adversarial_credit_card_variants(value: str) -> list[str]:
    """Generate adversarial obfuscations of a credit card number."""
    digits = re.sub(r'[^0-9]', '', value)
    variants = []

    # Continuous
    variants.append(digits)

    # Dot-separated
    groups = [digits[i:i+4] for i in range(0, len(digits), 4)]
    variants.append(".".join(groups))
    variants.append(" . ".join(groups))

    # All spaces (single or multiple)
    variants.append(" ".join(groups))
    variants.append("  ".join(groups))

    # Mixed format
    if len(groups) >= 4:
        variants.append(f"{groups[0]} {groups[1]}-{groups[2]} {groups[3]}")

    # Partial mask
    if len(digits) >= 4:
        variants.append(f"XXXX-XXXX-XXXX-{digits[-4:]}")
        variants.append(f"****-****-****-{digits[-4:]}")
        variants.append(f"••••-••••-••••-{digits[-4:]}")

    # With prefix label in the string
    variants.append(f"Visa ending in {digits[-4:]}")
    variants.append(f"cc: {digits}")

    # With extra spaces between pairs
    pairs = [digits[i:i+2] for i in range(0, len(digits), 2)]
    variants.append(" ".join(pairs))

    return variants


def adversarial_url_variants(value: str) -> list[str]:
    """Generate encoded/deobfuscatable URL variants."""
    variants = []

    # URL-encoded
    encoded = value.replace(":", "%3A").replace("/", "%2F").replace(".", "%2E")
    variants.append(encoded)

    # With encoding in path only
    if "?" in value:
        variants.append(value.replace("=", "%3D").replace("&", "%26"))

    # Hex-encoded localhost variant
    domain_match = re.search(r'https?://([^/]+)', value)
    if domain_match:
        domain = domain_match.group(1)
        # IP literal hex
        hex_ip = ".".join(f"0x{int(o):02x}" for o in domain.split(".") if o.isdigit())
        if not any(c.isalpha() for c in hex_ip) and "0x" in hex_ip:
            variants.append(value.replace(domain, hex_ip))

    # Decimal IP
    domain_match2 = re.search(r'https?://([^/]+)', value)
    if domain_match2:
        domain = domain_match2.group(1)
        octets = domain.split(".")
        if all(o.isdigit() for o in octets):
            dec_ip = sum(int(o) * (256 ** (3 - i)) for i, o in enumerate(octets))
            variants.append(value.replace(domain, str(dec_ip)))

    # Protocol variations
    if value.startswith("https://"):
        variants.append(value.replace("https://", "http://"))
        variants.append(value.replace("https://", "hxxps://"))
    elif value.startswith("http://"):
        variants.append(value.replace("http://", "hxxp://"))

    # Obfuscated (spaces around dots/slashes)
    spaced = re.sub(r'\.', ' . ', value)
    spaced = re.sub(r'//', ' // ', spaced)
    variants.append(spaced)

    return variants


def adversarial_ip_variants(value: str) -> list[str]:
    """Generate obfuscated IP address variants."""
    digits = re.sub(r'[^0-9.]', '', value)
    octets = digits.split(".")
    if len(octets) != 4:
        return [value]
    if not all(o.isdigit() for o in octets):
        return [value]

    variants = []

    # Dot-separated with spaces
    variants.append(" . ".join(octets))
    variants.append(".".join(octets) + " (IP)")

    # Spoken / text form
    variants.append(f"{octets[0]} dot {octets[1]} dot {octets[2]} dot {octets[3]}")
    variants.append(f"{octets[0]} point {octets[1]} point {octets[2]} point {octets[3]}")

    # Hex encoding per octet
    hex_octets = [f"0x{int(o):02x}" for o in octets]
    variants.append(".".join(hex_octets))

    # Decimal integer representation
    dec_val = sum(int(o) * (256 ** (3 - i)) for i, o in enumerate(octets))
    variants.append(str(dec_val))

    # Octal per octet
    oct_octets = [f"0{int(o):o}" for o in octets]
    variants.append(".".join(oct_octets))

    # CIDR notation variant
    variants.append(f"{digits}/24")
    variants.append(f"{digits}/16")

    # With spaces
    variants.append("  ".join(octets))
    variants.append(" ".join(octets))

    return variants


# Map entity types to their adversarial variant generators
ADVERSARIAL_GENERATORS: dict[str, Any] = {
    "EMAIL": adversarial_email_variants,
    "SOCIAL_SECURITY": adversarial_ssn_variants,
    "PHONE": adversarial_phone_variants,
    "CREDIT_CARD": adversarial_credit_card_variants,
    "URL": adversarial_url_variants,
    "IP_ADDRESS": adversarial_ip_variants,
}


def gen_adversarial_variants_for_type(
    ent_type: str, value: str, context: str, multiplier: int = 5
) -> list[tuple[str, str, str]]:
    """Generate adversarial variants for a single entity value.

    Returns list of (type, value, context) tuples.
    """
    gen_fn = ADVERSARIAL_GENERATORS.get(ent_type)
    if not gen_fn:
        return []

    adv_values = gen_fn(value)
    # Shuffle and take up to multiplier
    random.shuffle(adv_values)
    adv_values = adv_values[:multiplier]

    results: list[tuple[str, str, str]] = []
    for adv_val in adv_values:
        # Skip if it's identical to original
        if adv_val == value:
            continue
        # Generate a context that contains the adversarial value
        adv_contexts = [
            f"Obfuscated {ent_type.lower()}: {adv_val}",
            f"Found: {adv_val}",
            f"Data: {adv_val}",
            f"Hidden field: {adv_val}",
            f"Raw: {adv_val}",
            f"Encoded: {adv_val}",
        ]
        ctx = random.choice(adv_contexts)
        results.append((ent_type, adv_val, ctx))
    return results


# ═══════════════════════════════════════════════════════════════════════════════
#  Generation functions per entity type
# ═══════════════════════════════════════════════════════════════════════════════


def gen_emails(count: int) -> list[tuple[str, str, str]]:
    results: list[tuple[str, str, str]] = []
    for _ in range(count):
        local = random.choice(EMAIL_LOCALS)
        domain = random.choice(DOMAINS)
        local_v = f"{local}{random.randint(1,999)}"
        email = fmt_email(local_v, domain)
        ctx = random.choice([
            f"Email: {email}",
            f"Reach us at {email}",
            f"Contact: {email}",
            f"Send to {email}",
            f"My email is {email}",
            f"Please email {email}",
            f"registered: {email}",
            f"mailbox: {email}",
        ])
        results.append(("EMAIL", email, ctx))
    return results


def gen_phones(count: int) -> list[tuple[str, str, str]]:
    results: list[tuple[str, str, str]] = []
    for _ in range(count):
        c = random.choice(["1", "44", "81", "49", "33", "61", "91"])
        n = f"{random.randint(2,9)}{random.randint(100,999)}{random.randint(1000,9999)}"
        if len(n) < 10:
            n = n + str(random.randint(10,99))
        phone = fmt_phone(c, n)
        ctx = random.choice([
            f"Phone: {phone}",
            f"Call {phone}",
            f"Tel: {phone}",
            f"Reach me at {phone}",
            f"Contact number {phone}",
            f"Mobile: {phone}",
        ])
        results.append(("PHONE", phone, ctx))
    return results


def gen_ssns(count: int) -> list[tuple[str, str, str]]:
    results: list[tuple[str, str, str]] = []
    for _ in range(count):
        a = f"{random.randint(1,9)}{random.randint(0,9)}{random.randint(0,9)}"
        g = f"{random.randint(0,9)}{random.randint(0,9)}"
        s = f"{random.randint(0,9)}{random.randint(0,9)}{random.randint(0,9)}{random.randint(0,9)}"
        ssn = fmt_ssn(a, g, s)
        ctx = random.choice([
            f"SSN: {ssn}",
            f"Social Security: {ssn}",
            f"Ssn: {ssn}",
            f"Tax ID: {ssn}",
            f"My SSN is {ssn}",
        ])
        results.append(("SOCIAL_SECURITY", ssn, ctx))
    return results


def gen_credit_cards(count: int) -> list[tuple[str, str, str]]:
    known_ccs = [
        "4111111111111111",  # Visa
        "5500000000000004",  # MasterCard
        "340000000000009",   # Amex (15 digits)
        "6011000000000004",  # Discover
        "30000000000004",    # Diners Club (14 digits)
        "3530111333300000",  # JCB
        "4000056655665556",  # Visa debit
        "5424000000000015",  # MasterCard
        "378282246310005",   # Amex
        "6011111111111117",  # Discover
        "30569309025904",    # Diners Club
        "3566002020360505",  # JCB
    ]
    results: list[tuple[str, str, str]] = []
    for _ in range(count):
        cc = random.choice(known_ccs)
        formatted = fmt_credit_card(cc)
        ctx = random.choice([
            f"Credit card: {formatted}",
            f"CC: {formatted}",
            f"Card: {formatted}",
            f"Payment: {formatted}",
            f"Card number {formatted}",
            f"Visa: {formatted}",
        ])
        results.append(("CREDIT_CARD", formatted, ctx))
    return results


def gen_ip_addresses(count: int) -> list[tuple[str, str, str]]:
    results: list[tuple[str, str, str]] = []
    prefixes = [
        (10, list(range(0,256))),
        (172, [16, 31]),
        (192, [168]),
        (192, [0, 254]),
    ]
    for _ in range(count):
        if random.random() < 0.5:
            o = [str(random.randint(1,254)) for _ in range(4)]
        else:
            prefix = random.choice(prefixes)
            if isinstance(prefix[1], list):
                o = [str(prefix[0]), str(random.choice(prefix[1])),
                     str(random.randint(0,255)), str(random.randint(1,254))]
            else:
                o = [str(prefix[0]), str(random.randint(0,255)),
                     str(random.randint(0,255)), str(random.randint(1,254))]
        ip = fmt_ip(o)
        ctx = random.choice([
            f"IP: {ip}",
            f"Server at {ip}",
            f"Address {ip}",
            f"Host {ip}",
            f"Connect to {ip}",
        ])
        results.append(("IP_ADDRESS", ip, ctx))
    for _ in range(count // 4):
        ipv6 = f"2001:{random.choice(['db8','0db8'])}:{random.randint(1000,9999):04x}:" \
               f"0000:0000:{random.choice(['8a2e','0000'])}:" \
               f"{random.randint(1000,9999):04x}:{random.randint(1000,9999):04x}"
        ctx = f"IPv6: {ipv6}"
        results.append(("IP_ADDRESS", ipv6, ctx))
    return results


def gen_addresses(count: int) -> list[tuple[str, str, str]]:
    results: list[tuple[str, str, str]] = []
    for _ in range(count):
        num = str(random.randint(1, 9999))
        street = random.choice(STREET_NAMES)
        city = random.choice(CITIES)
        state = random.choice(["NY", "CA", "IL", "TX", "MA", "WA", "CO", "FL", "OR", "AZ"])
        zip_c = random.choice(ZIP_CODES)
        country = random.choice(["USA", "Canada", "UK"])
        addr = fmt_address(num, street, city, state, zip_c, country)
        ctx = random.choice([
            f"Address: {addr}",
            f"Office at {addr}",
            f"Shipping: {addr}",
            f"Location: {addr}",
            f"Our address is {addr}",
        ])
        results.append(("ADDRESS", addr, ctx))
    return results


def gen_persons(count: int) -> list[tuple[str, str, str]]:
    results: list[tuple[str, str, str]] = []
    for _ in range(count):
        first = random.choice(FIRST_NAMES)
        last = random.choice(LAST_NAMES)
        name = f"{first} {last}"
        title = random.choice(["Mr.", "Ms.", "Dr.", "Prof.", ""])
        full = f"{title} {name}" if title and random.random() < 0.3 else name
        ctx = random.choice([
            f"Person: {full}",
            f"Contact person: {full}",
            f"Hello, I'm {full}",
            f"Signed, {full}",
            f"{full} approved the request",
            f"Employee {full}",
            f"Manager: {full}",
        ])
        results.append(("PERSON", full, ctx))
    return results


def gen_companies(count: int) -> list[tuple[str, str, str]]:
    results: list[tuple[str, str, str]] = []
    for _ in range(count):
        company = random.choice(COMPANIES)
        ctx = random.choice([
            f"Company: {company}",
            f"I work at {company}",
            f"{company} is the vendor",
            f"Invoice from {company}",
            f"{company} Inc.",
            f"Signed by {company}",
        ])
        results.append(("COMPANY", company, ctx))
    return results


def gen_cities(count: int) -> list[tuple[str, str, str]]:
    results: list[tuple[str, str, str]] = []
    for _ in range(count):
        city = random.choice(CITIES)
        ctx = random.choice([
            f"City: {city}",
            f"I live in {city}",
            f"Based in {city}",
            f"Our {city} office",
            f"{city} headquarters",
            f"Visiting {city}",
        ])
        results.append(("CITY", city, ctx))
    return results


def gen_countries(count: int) -> list[tuple[str, str, str]]:
    results: list[tuple[str, str, str]] = []
    for _ in range(count):
        country = random.choice(COUNTRIES)
        ctx = random.choice([
            f"Country: {country}",
            f"Based in {country}",
            f"Shipping to {country}",
            f"HQ in {country}",
            f"From {country}",
        ])
        results.append(("COUNTRY", country, ctx))
    return results


def gen_urls(count: int) -> list[tuple[str, str, str]]:
    results: list[tuple[str, str, str]] = []
    for _ in range(count):
        domain = random.choice(DOMAINS)
        path = random.choice(["/dashboard", "/api/v1/users", "/settings",
                              "/profile", "/admin", "/login", "/download",
                              "/assets/img/logo.png", "/docs/api-reference"])
        url = f"https://www.{domain}{path}"
        ctx = random.choice([
            f"URL: {url}",
            f"Visit {url}",
            f"Open {url}",
            f"Link: {url}",
            f"Go to {url}",
        ])
        results.append(("URL", url, ctx))
    return results


def gen_file_paths(count: int) -> list[tuple[str, str, str]]:
    results: list[tuple[str, str, str]] = []
    paths = [
        "/var/log/nginx/access.log",
        "/etc/ssh/sshd_config",
        "/opt/application/config/production/settings.json",
        "/home/user/data/db.sqlite",
        "/tmp/cache/data/temp.log",
        "/usr/local/bin/deploy.sh",
        "/etc/nginx/sites-enabled/default",
        "/var/www/html/index.html",
        "/opt/app/config.yaml",
        "/home/user/projects/src/main.py",
        "/data/backups/db-2024-01-01.sql.gz",
        "/etc/ssl/certs/server.crt",
        "/var/log/auth.log",
        "/usr/share/nginx/html/static/bundle.js",
        "/opt/application/logs/error.log",
    ]
    for _ in range(count):
        fp = random.choice(paths)
        ctx = random.choice([
            f"Path: {fp}",
            f"File: {fp}",
            f"Located at {fp}",
            f"Config: {fp}",
            f"Log file: {fp}",
        ])
        results.append(("FILE_PATH", fp, ctx))
    return results


def gen_api_keys(count: int) -> list[tuple[str, str, str]]:
    results: list[tuple[str, str, str]] = []
    for _ in range(count):
        prefix = random.choice(["sk-", "api_", "key_", "secret_", "pk_"])
        suffix = "".join(random.choices("abcdef0123456789", k=32))
        key = f"{prefix}{suffix}"
        ctx = random.choice([
            f"API key: {key}",
            f"Key: {key}",
            f"Token: {key}",
            f"Auth: {key}",
            f"secret: {key}",
        ])
        results.append(("API_KEY", key, ctx))
    return results


def gen_jwts(count: int) -> list[tuple[str, str, str]]:
    results: list[tuple[str, str, str]] = []
    for _ in range(count):
        header = "eyJ" + "".join(random.choices("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_", k=20))
        payload = "eyJ" + "".join(random.choices("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_", k=40))
        sig = "".join(random.choices("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_", k=43))
        jwt = f"{header}.{payload}.{sig}"
        ctx = random.choice([
            f"JWT: {jwt}",
            f"Token: {jwt}",
            f"Bearer {jwt}",
            f"Auth token: {jwt}",
            f"jwt={jwt}",
        ])
        results.append(("JWT", jwt, ctx))
    return results


def gen_gps(count: int) -> list[tuple[str, str, str]]:
    results: list[tuple[str, str, str]] = []
    locations = [
        (40.7128, -74.0060, "New York"),
        (51.5074, -0.1278, "London"),
        (35.6762, 139.6503, "Tokyo"),
        (48.8566, 2.3522, "Paris"),
        (52.5200, 13.4050, "Berlin"),
        (-33.8688, 151.2093, "Sydney"),
        (19.0760, 72.8777, "Mumbai"),
        (31.2304, 121.4737, "Shanghai"),
        (25.2048, 55.2708, "Dubai"),
        (37.7749, -122.4194, "San Francisco"),
    ]
    for lat, lng, name in locations:
        ctx = random.choice([
            f"Coordinates: {lat}, {lng} ({name})",
            f"Lat: {lat}, Lng: {lng}",
            f"GPS: {lat} N, {lng} W",
            f"Location: {lat}, {lng}",
        ])
        results.append(("GPS", str(lat), ctx))
        results.append(("GPS", str(lng), ctx))
    for _ in range(count - len(locations) * 2 if count > len(locations) * 2 else 0):
        lat = round(random.uniform(-90, 90), 4)
        lng = round(random.uniform(-180, 180), 4)
        results.append(("GPS", str(lat), f"GPS: {lat}, {lng}"))
        results.append(("GPS", str(lng), f"GPS: {lat}, {lng}"))
    return results[:count]


def gen_ibans(count: int) -> list[tuple[str, str, str]]:
    results: list[tuple[str, str, str]] = []
    ibans = [
        ("DE89 3704 0044 0532 0130 00", "German"),
        ("GB29 NWBK 6016 1331 9268 19", "UK"),
        ("FR76 3000 6000 0112 3456 7890 189", "French"),
        ("CH93 0076 2011 6238 5295 7", "Swiss"),
        ("NL91 ABNA 0417 1643 00", "Dutch"),
        ("ES79 2100 0813 6101 2345 6789", "Spanish"),
        ("IT60 X054 2811 1010 0000 0123 456", "Italian"),
        ("SE35 5000 0000 0549 1000 0003", "Swedish"),
        ("NO93 8601 1117 947", "Norwegian"),
        ("DK50 0040 0440 1162 43", "Danish"),
    ]
    for _ in range(count):
        iban, _ = random.choice(ibans)
        ctx = random.choice([
            f"IBAN: {iban}",
            f"Bank IBAN: {iban}",
            f"IBAN number {iban}",
            f"International: {iban}",
        ])
        results.append(("IBAN", iban, ctx))
    return results


def gen_passports(count: int) -> list[tuple[str, str, str]]:
    results: list[tuple[str, str, str]] = []
    prefixes = "ABCDEFGHXYZ"
    for _ in range(count):
        pf = random.choice(prefixes) + random.choice(prefixes)
        num = "".join(random.choices("0123456789", k=7))
        passport = f"{pf}{num}"
        ctx = random.choice([
            f"Passport: {passport}",
            f"Passport number {passport}",
            f"ID: {passport}",
            f"Travel doc: {passport}",
        ])
        results.append(("PASSPORT", passport, ctx))
    return results


def gen_dates(count: int) -> list[tuple[str, str, str]]:
    results: list[tuple[str, str, str]] = []
    for _ in range(count):
        y = random.randint(1980, 2030)
        m = random.randint(1, 12)
        d = random.randint(1, 28)
        fmt = random.choice([
            f"{y:04d}-{m:02d}-{d:02d}",
            f"{m:02d}/{d:02d}/{y:04d}",
            f"{d:02d}/{m:02d}/{y:04d}",
            f"{y}-{m}-{d}",
        ])
        ctx = random.choice([
            f"Date: {fmt}",
            f"Expires: {fmt}",
            f"Born: {fmt}",
            f"Valid until {fmt}",
            f"Updated: {fmt}",
        ])
        results.append(("DATE", fmt, ctx))
    return results


def gen_domains(count: int) -> list[tuple[str, str, str]]:
    results: list[tuple[str, str, str]] = []
    for _ in range(count):
        sub = random.choice(["www", "mail", "api", "admin", "dev", "staging", "test", "app", "docs"])
        domain = random.choice(["example", "acme", "company", "myapp", "testapp", "internal", "corp", "private"])
        tld = random.choice(["com", "org", "net", "io", "dev", "app", "cloud", "internal", "local", "co.uk", "ai"])
        full = f"{sub}.{domain}.{tld}"
        ctx = random.choice([
            f"Domain: {full}",
            f"Visit {full}",
            f"Site: {full}",
            f"Access {full}",
        ])
        results.append(("DOMAIN", full, ctx))
    return results


def gen_private_urls(count: int) -> list[tuple[str, str, str]]:
    results: list[tuple[str, str, str]] = []
    for _ in range(count):
        host = random.choice([
            "localhost:3000", "127.0.0.1:8080", "localhost:8000",
            "127.0.0.1:5000", "localhost:4000", "internal:80",
            "10.0.0.1:443", "192.168.1.1:3000",
        ])
        path = random.choice(["/dashboard", "/admin", "/api", "/health",
                              "/config", "/status", "/debug"])
        url = f"http://{host}{path}"
        ctx = random.choice([
            f"Private: {url}",
            f"Dev server: {url}",
            f"Local: {url}",
            f"Internal: {url}",
        ])
        results.append(("PRIVATE_URL", url, ctx))
    return results


def gen_ssh_keys(count: int) -> list[tuple[str, str, str]]:
    results: list[tuple[str, str, str]] = []
    key_headers = [
        "-----BEGIN RSA PRIVATE KEY-----",
        "-----BEGIN DSA PRIVATE KEY-----",
        "-----BEGIN EC PRIVATE KEY-----",
        "-----BEGIN OPENSSH PRIVATE KEY-----",
        "-----BEGIN PGP PRIVATE KEY BLOCK-----",
    ]
    for _ in range(count):
        header = random.choice(key_headers)
        ctx = random.choice([
            f"SSH key: {header}",
            f"Private key {header}",
            f"Key: {header}",
            f"Cert: {header}",
        ])
        results.append(("SSH_KEY", header, ctx))
    return results


def gen_database_urls(count: int) -> list[tuple[str, str, str]]:
    results: list[tuple[str, str, str]] = []
    for _ in range(count):
        scheme = random.choice(["postgresql", "mysql", "mongodb", "redis", "sqlite"])
        user = random.choice(["admin", "app_user", "dev_user", "readonly", "deploy"])
        host = random.choice(["db.internal", "db-prod.internal", "mysql-dev.internal",
                               "localhost", "postgres.internal", "redis-cluster.internal"])
        port_map = {"postgresql": "5432", "mysql": "3306", "mongodb": "27017",
                    "redis": "6379", "sqlite": ""}
        db = random.choice(["analytics", "staging", "production", "app_db", "cache",
                            "main", "users", "billing"])
        if scheme == "sqlite":
            url = f"{scheme}:///data/db/{db}.db"
        else:
            url = f"{scheme}://{user}:****@{host}:{port_map[scheme]}/{db}"
        ctx = random.choice([
            f"DB: {url}",
            f"Database: {url}",
            f"Connection: {url}",
            f"DSN: {url}",
        ])
        results.append(("DATABASE_URL", url, ctx))
    return results


def gen_bank_accounts(count: int) -> list[tuple[str, str, str]]:
    results: list[tuple[str, str, str]] = []
    for _ in range(count):
        num = "".join(random.choices("0123456789", k=random.choice([10, 12, 16, 18, 20])))
        ctx = random.choice([
            f"Bank: {num}",
            f"Account: {num}",
            f"A/c: {num}",
            f"Bank account {num}",
        ])
        results.append(("BANK_ACCOUNT", num, ctx))
    return results


def gen_customer_names(count: int) -> list[tuple[str, str, str]]:
    results: list[tuple[str, str, str]] = []
    for _ in range(count):
        first = random.choice(FIRST_NAMES)
        last = random.choice(LAST_NAMES)
        name = f"{first} {last}"
        ctx = random.choice([
            f"Customer: {name}",
            f"Client: {name}",
            f"Customer name: {name}",
            f"User {name} ordered",
        ])
        results.append(("CUSTOMER_NAME", name, ctx))
    return results


def gen_employee_names(count: int) -> list[tuple[str, str, str]]:
    results: list[tuple[str, str, str]] = []
    for _ in range(count):
        first = random.choice(FIRST_NAMES)
        last = random.choice(LAST_NAMES)
        name = f"{first} {last}"
        ctx = random.choice([
            f"Employee: {name}",
            f"Staff: {name}",
            f"Employee name: {name}",
            f"Team member {name}",
        ])
        results.append(("EMPLOYEE_NAME", name, ctx))
    return results


def gen_project_names(count: int) -> list[tuple[str, str, str]]:
    results: list[tuple[str, str, str]] = []
    projects = [
        "Project Nebula", "Project Orion", "Project Pandorica", "Project Bad Wolf",
        "Project Phoenix", "Project Aurora", "Project Titan", "Project Atlas",
        "Project Helios", "Project Nova", "Project Eclipse", "Project Infinity",
        "Project Quantum", "Project Velocity", "Project Horizon",
        "Alpha Initiative", "Omega Protocol", "Blue Sky", "Moonlight",
    ]
    for _ in range(count):
        proj = random.choice(projects)
        ctx = random.choice([
            f"{proj} starts next quarter",
            f"Working on {proj}",
            f"{proj} is in development",
            f"{proj} milestone due",
            f"Team assigned to {proj}",
        ])
        results.append(("PROJECT_NAME", proj, ctx))
    return results


# ═══════════════════════════════════════════════════════════════════════════════
#  Example builder
# ═══════════════════════════════════════════════════════════════════════════════

GENERATORS: dict[str, Any] = {
    "EMAIL": gen_emails,
    "PHONE": gen_phones,
    "SOCIAL_SECURITY": gen_ssns,
    "CREDIT_CARD": gen_credit_cards,
    "IP_ADDRESS": gen_ip_addresses,
    "ADDRESS": gen_addresses,
    "PERSON": gen_persons,
    "COMPANY": gen_companies,
    "CITY": gen_cities,
    "COUNTRY": gen_countries,
    "URL": gen_urls,
    "FILE_PATH": gen_file_paths,
    "API_KEY": gen_api_keys,
    "JWT": gen_jwts,
    "GPS": gen_gps,
    "IBAN": gen_ibans,
    "PASSPORT": gen_passports,
    "DATE": gen_dates,
    "DOMAIN": gen_domains,
    "PRIVATE_URL": gen_private_urls,
    "SSH_KEY": gen_ssh_keys,
    "DATABASE_URL": gen_database_urls,
    "BANK_ACCOUNT": gen_bank_accounts,
    "CUSTOMER_NAME": gen_customer_names,
    "EMPLOYEE_NAME": gen_employee_names,
    "PROJECT_NAME": gen_project_names,
}

def make_example(text: str, entities: list[dict[str, Any]]) -> dict[str, Any]:
    return {"text": text, "entities": entities}


def find_span(text: str, value: str) -> tuple[int, int]:
    idx = text.find(value)
    if idx == -1:
        normalized = " ".join(value.split())
        idx = text.find(normalized)
        if idx == -1:
            raise ValueError(f"Could not find '{value}' in '{text}'")
        return idx, idx + len(normalized)
    return idx, idx + len(value)


def gen_variants_of_example(
    ex: dict[str, Any],
    multiplier: int = 1,
) -> list[dict[str, Any]]:
    entity_types_in_ex = [e["type"] for e in ex["entities"]]
    type_pools: dict[str, list[tuple[str, str, str]]] = {}
    for et in set(entity_types_in_ex):
        gen_fn = GENERATORS.get(et)
        if gen_fn:
            type_pools[et] = gen_fn(max(multiplier * 2, 5))
        else:
            type_pools[et] = [(et, e["value"], "") for e in ex["entities"] if e["type"] == et]

    variants: list[dict[str, Any]] = []
    for idx in range(multiplier):
        new_entities = []
        text_parts = []
        last_end = 0
        for e in ex["entities"]:
            et = e["type"]
            pool = type_pools.get(et, [])
            if pool and idx < len(pool):
                _, new_val, _ = pool[idx]
            else:
                _, new_val, _ = pool[0] if pool else (et, e["value"], "")
            orig_text = ex["text"]
            orig_start = e["start"]
            orig_end = e["end"]
            prefix = orig_text[last_end:orig_start]
            text_parts.append(prefix)
            text_parts.append(new_val)
            new_entities.append({
                "type": et,
                "value": new_val,
                "start": len("".join(text_parts)) - len(new_val),
                "end": len("".join(text_parts)),
            })
            last_end = orig_end
        text_parts.append(ex["text"][last_end:])
        new_text = "".join(text_parts)
        running_pos = 0
        for ent in new_entities:
            val = ent["value"]
            adj_start = new_text.find(val, running_pos)
            if adj_start == -1:
                adj_start = running_pos
            ent["start"] = adj_start
            ent["end"] = adj_start + len(val)
            running_pos = ent["end"]
        variants.append(make_example(new_text, new_entities))
    return variants


# ═══════════════════════════════════════════════════════════════════════════════
#  Adversarial example generation
# ═══════════════════════════════════════════════════════════════════════════════

def generate_adversarial_examples(
    existing: list[dict[str, Any]],
    adv_multiplier: int = 5,
) -> list[dict[str, Any]]:
    """Generate adversarial variants from existing examples.

    For each example containing an entity type that has an adversarial generator,
    create adversarial variants of that entity's value.
    """
    adversarial_examples: list[dict[str, Any]] = []

    # Track per-type count to ensure good distribution
    type_counts: Counter = Counter()

    for ex in existing:
        for entity in ex["entities"]:
            ent_type = entity["type"]
            if ent_type not in ADVERSARIAL_GENERATORS:
                continue

            orig_value = entity["value"]
            orig_context = ex["text"]

            adv_results = gen_adversarial_variants_for_type(
                ent_type, orig_value, orig_context, multiplier=adv_multiplier
            )

            for _type, adv_val, adv_ctx in adv_results:
                text = adv_ctx
                entities = []
                try:
                    start, end = find_span(text, adv_val)
                    entities.append({
                        "type": ent_type,
                        "value": adv_val,
                        "start": start,
                        "end": end,
                    })
                    adversarial_examples.append(make_example(text, entities))
                    type_counts[ent_type] += 1
                except ValueError:
                    continue

    print(f"Generated {len(adversarial_examples)} adversarial variants")
    for t, c in sorted(type_counts.items()):
        print(f"  {t}: {c}")
    print()
    return adversarial_examples


# ═══════════════════════════════════════════════════════════════════════════════
#  Pure generation (non-variant) — produce standalone examples from scratch
# ═══════════════════════════════════════════════════════════════════════════════

# Target counts per entity type — increased to ensure 2000+ with adversarial
TARGET_ENTITY_COUNTS: dict[str, int] = {
    "EMAIL": 100,
    "PHONE": 60,
    "SOCIAL_SECURITY": 50,
    "CREDIT_CARD": 50,
    "IP_ADDRESS": 60,
    "ADDRESS": 40,
    "PERSON": 80,
    "COMPANY": 40,
    "CITY": 50,
    "COUNTRY": 50,
    "URL": 40,
    "FILE_PATH": 40,
    "API_KEY": 50,
    "JWT": 40,
    "GPS": 50,
    "IBAN": 30,
    "PASSPORT": 30,
    "DATE": 30,
    "DOMAIN": 40,
    "PRIVATE_URL": 30,
    "SSH_KEY": 30,
    "DATABASE_URL": 40,
    "BANK_ACCOUNT": 30,
    "CUSTOMER_NAME": 30,
    "EMPLOYEE_NAME": 30,
    "PROJECT_NAME": 30,
}


def load_existing(path: Path) -> list[dict[str, Any]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return raw.get("examples", [])


def count_entity_types(examples: list[dict[str, Any]]) -> Counter:
    c: Counter = Counter()
    for ex in examples:
        for e in ex["entities"]:
            c[e["type"]] += 1
    return c


def generate_pure_examples(existing_counts: Counter) -> list[dict[str, Any]]:
    new_examples: list[dict[str, Any]] = []
    entity_counts = Counter(existing_counts)

    for ent_type, target in sorted(TARGET_ENTITY_COUNTS.items()):
        needed = target - entity_counts.get(ent_type, 0)
        if needed <= 0:
            continue

        gen_fn = GENERATORS.get(ent_type)
        if not gen_fn:
            continue

        generated = gen_fn(needed * 3)
        for _type, val, ctx in generated:
            if needed <= 0:
                break
            text = ctx
            entities = []
            try:
                start, end = find_span(text, val)
                entities.append({"type": ent_type, "value": val, "start": start, "end": end})
                new_examples.append(make_example(text, entities))
                entity_counts[ent_type] += 1
                needed -= 1
            except ValueError:
                continue

    return new_examples


def generate_mixed_examples(count: int) -> list[dict[str, Any]]:
    examples: list[dict[str, Any]] = []

    for _ in range(count // 4):
        first = random.choice(FIRST_NAMES)
        last = random.choice(LAST_NAMES)
        name = f"{first} {last}"
        local = f"{first.lower()}.{last.lower()}"
        domain = random.choice(DOMAINS)
        email = f"{local}@{domain}"
        company = random.choice(COMPANIES)
        context = random.choice([
            f"Hi, I'm {name} from {company}. Email: {email}",
            f"{name} ({email}) works at {company}",
            f"Contact {name} at {email} regarding {company}",
        ])
        entities = [
            {"type": "PERSON", "value": name, "start": 0, "end": 0},
            {"type": "COMPANY", "value": company, "start": 0, "end": 0},
            {"type": "EMAIL", "value": email, "start": 0, "end": 0},
        ]
        for ent in entities:
            val = ent["value"]
            idx = context.find(val)
            if idx != -1:
                ent["start"] = idx
                ent["end"] = idx + len(val)
        examples.append(make_example(context, [e for e in entities if e["start"] > 0]))

    for _ in range(count // 6):
        num = str(random.randint(1, 9999))
        street = random.choice(STREET_NAMES)
        city = random.choice(CITIES)
        state = random.choice(["NY", "CA", "TX", "WA", "IL"])
        zip_c = random.choice(ZIP_CODES)
        addr = f"{num} {street}, {city}, {state} {zip_c}"
        c_code = random.choice(["1", "44"])
        pn = f"{random.randint(200,999)}{random.randint(100,999)}{random.randint(1000,9999)}"
        phone = f"+{c_code}-{pn[0:3]}-{pn[3:6]}-{pn[6:]}"
        context = f"Ship to {addr}. Phone: {phone}"
        entities = []
        idx = context.find(addr)
        if idx != -1:
            entities.append({"type": "ADDRESS", "value": addr, "start": idx, "end": idx + len(addr)})
        idx = context.find(phone)
        if idx != -1:
            entities.append({"type": "PHONE", "value": phone, "start": idx, "end": idx + len(phone)})
        if entities:
            examples.append(make_example(context, entities))

    for _ in range(count // 8):
        a = f"{random.randint(1,9)}{random.randint(0,9)}{random.randint(0,9)}"
        g = f"{random.randint(0,9)}{random.randint(0,9)}"
        s = f"{random.randint(0,9)}{random.randint(0,9)}{random.randint(0,9)}{random.randint(0,9)}"
        ssn = f"{a}-{g}-{s}"
        dob = f"{random.randint(1,12):02d}/{random.randint(1,28):02d}/{random.randint(1960,2000)}"
        context = f"My SSN is {ssn} and DOB is {dob}"
        entities = []
        idx = context.find(ssn)
        if idx != -1:
            entities.append({"type": "SOCIAL_SECURITY", "value": ssn, "start": idx, "end": idx + len(ssn)})
        idx = context.find(dob)
        if idx != -1:
            entities.append({"type": "DATE", "value": dob, "start": idx, "end": idx + len(dob)})
        examples.append(make_example(context, entities))

    for _ in range(count // 8):
        ip = f"{random.randint(10,192)}.{random.randint(0,168)}.{random.randint(0,255)}.{random.randint(1,254)}"
        domain = f"server-{random.randint(1,99)}.{random.choice(['internal','corp','local'])}"
        context = f"Server {domain} at IP {ip}"
        entities = []
        idx = context.find(domain)
        if idx != -1:
            entities.append({"type": "DOMAIN", "value": domain, "start": idx, "end": idx + len(domain)})
        idx = context.find(ip)
        if idx != -1:
            entities.append({"type": "IP_ADDRESS", "value": ip, "start": idx, "end": idx + len(ip)})
        examples.append(make_example(context, entities))

    for _ in range(count // 10):
        cc = random.choice(["4111111111111111", "5500000000000004", "378282246310005"])
        formatted = f"{cc[0:4]}-{cc[4:8]}-{cc[8:12]}-{cc[12:]}"
        jwt = f"eyJ0eX...NiJ9.{'e30' + ''.join(random.choices('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789', k=30))}.{'SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c'}"
        context = f"CC: {formatted} Token: {jwt[:50]}..."
        entities = []
        idx = context.find(formatted)
        if idx != -1:
            entities.append({"type": "CREDIT_CARD", "value": formatted, "start": idx, "end": idx + len(formatted)})
        idx = context.find(jwt[:50])
        if idx != -1:
            entities.append({"type": "JWT", "value": jwt[:50], "start": idx, "end": idx + 50})
        examples.append(make_example(context, entities))

    return examples


def build_targeted_examples(target_counts: dict[str, int]) -> list[dict[str, Any]]:
    examples: list[dict[str, Any]] = []

    for ent_type, target in target_counts.items():
        gen_fn = GENERATORS.get(ent_type)
        if not gen_fn:
            continue
        generated = gen_fn(target)
        for _type, val, ctx in generated:
            text = ctx
            entities = []
            try:
                start, end = find_span(text, val)
                entities.append({"type": ent_type, "value": val, "start": start, "end": end})
                if ent_type in ("EMAIL", "PHONE", "PERSON", "COMPANY") and random.random() < 0.4:
                    extra_type = random.choice(["PERSON", "COMPANY", "CITY"])
                    if extra_type not in ("PERSON", ent_type):
                        extra_val = random.choice(FIRST_NAMES)
                        if extra_type == "COMPANY":
                            extra_val = random.choice(COMPANIES)
                        elif extra_type == "CITY":
                            extra_val = random.choice(CITIES)
                        if extra_val not in text:
                            text = f"{text} ({extra_type}: {extra_val})"
                        idx = text.find(extra_val, len(ctx))
                        if idx != -1:
                            entities.append({"type": extra_type, "value": extra_val, "start": idx, "end": idx + len(extra_val)})
                examples.append(make_example(text, entities))
            except ValueError:
                continue

    return examples


def generate_full_dataset() -> dict[str, Any]:
    existing = load_existing(DEFAULT_SOURCE)
    existing_counts = count_entity_types(existing)

    print(f"Existing examples: {len(existing)}")
    print(f"Existing entities: {sum(existing_counts.values())}")
    print(f"Entity type distribution:")
    for t, c in sorted(existing_counts.items()):
        needed = TARGET_ENTITY_COUNTS.get(t, 0) - c
        print(f"  {t}: {c} (need {max(0, needed)} more)")
    print()

    # Generate adversarial variants first (from existing examples)
    adversarial = generate_adversarial_examples(existing, adv_multiplier=5)
    adversarial_counts = count_entity_types(adversarial)

    # Generate new examples to fill gaps (including adversarial counts)
    combined_counts = existing_counts + adversarial_counts
    pure_new = generate_pure_examples(combined_counts)
    print(f"Generated {len(pure_new)} pure-type examples\n")

    mixed = generate_mixed_examples(300)
    print(f"Generated {len(mixed)} mixed-type examples\n")

    # Combine everything
    combined = existing + adversarial + pure_new + mixed
    current_counts = count_entity_types(combined)

    # Check which types are still under target
    still_needed: dict[str, int] = {}
    for t, target in TARGET_ENTITY_COUNTS.items():
        current = current_counts.get(t, 0)
        if current < target:
            still_needed[t] = target - current

    if still_needed:
        print(f"Still need {sum(still_needed.values())} more entities across {len(still_needed)} types:")
        for t, n in sorted(still_needed.items()):
            print(f"  {t}: need {n} more")
        targeted = build_targeted_examples(still_needed)
        print(f"Generated {len(targeted)} targeted examples\n")
        combined += targeted

    # Also generate additional adversarial examples from the new (non-adversarial) examples
    # to ensure we have plenty of adversarial variants
    non_adv = pure_new + mixed
    more_adversarial = generate_adversarial_examples(non_adv, adv_multiplier=3)
    if more_adversarial:
        print(f"Generated {len(more_adversarial)} additional adversarial variants from new examples\n")
        combined += more_adversarial

    # Final count
    final_counts = count_entity_types(combined)
    print(f"Final examples: {len(combined)}")
    print(f"Final entities: {sum(final_counts.values())}")
    print(f"Final entity type distribution:")
    for t, c in sorted(final_counts.items()):
        target = TARGET_ENTITY_COUNTS.get(t, 0)
        status = "✅" if c >= target else "⚠️"
        print(f"  {status} {t}: {c} (target: {target})")

    dataset = {
        "description": (
            f"PIIFilter Detection Recall Benchmark Dataset — "
            f"{len(combined)} labeled examples covering {len(TARGET_ENTITY_COUNTS)} entity types. "
            f"Expanded from original {len(existing)} examples to {len(combined)} for statistical significance. "
            f"Includes adversarial variants (obfuscated/encoded/zero-width) for EMAIL, PHONE, SSN, "
            f"CREDIT_CARD, URL, and IP_ADDRESS types."
        ),
        "version": "2.1.0",
        "examples": combined,
    }

    return dataset


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate expanded PII detection dataset (2000+ examples, with adversarial variants)"
    )
    parser.add_argument(
        "--save",
        action="store_true",
        help="Save the generated dataset to file",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=str(DEFAULT_OUTPUT),
        help=f"Output file path (default: {DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--source",
        type=str,
        default=str(DEFAULT_SOURCE),
        help=f"Source dataset file (default: {DEFAULT_SOURCE})",
    )
    args = parser.parse_args()

    dataset = generate_full_dataset()

    if args.save:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(dataset, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(f"\n✅ Dataset saved to {output_path}")
        print(f"   Total examples: {len(dataset['examples'])}")
        print(f"   Total entities: {sum(len(e['entities']) for e in dataset['examples'])}")
    else:
        print(f"\nDry-run complete. Use --save to write to {args.output}")


if __name__ == "__main__":
    main()