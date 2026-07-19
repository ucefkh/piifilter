#!/usr/bin/env python3
"""PII Dataset Generator — expands the labeled dataset to 1000+ examples.

Reads the existing benchmarks/data/pii_dataset.json and generates variations
for each example: different names, emails, numbers, format variations
(spaces, dots, dashes), and diverse examples for all entity types.

Usage:
    uv run python benchmarks/generate_dataset.py          # dry-run: print counts
    uv run python benchmarks/generate_dataset.py --save    # save to pii_dataset_v2.json
    uv run python benchmarks/generate_dataset.py --save --output benchmarks/data/my_dataset.json
"""

from __future__ import annotations

import argparse
import copy
import json
import random
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
#  Generation functions per entity type
# ═══════════════════════════════════════════════════════════════════════════════

def gen_emails(count: int) -> list[tuple[str, str, str]]:
    """Generate (value, text_context, label) for EMAIL entities."""
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
    # Use known test credit card numbers (Luhn-valid)
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
    # Private ranges for realistic IPs
    prefixes = [
        (10, list(range(0,256))),
        (172, [16, 31]),
        (192, [168]),
        (192, [0, 254]),
    ]
    for _ in range(count):
        if random.random() < 0.5:
            # Random public-ish IP
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
    # Include some IPv6
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
    # Extra random GPS
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

def make_example(text: str, entities: list[dict[str, Any]]) -> dict[str, Any]:
    return {"text": text, "entities": entities}


def find_span(text: str, value: str) -> tuple[int, int]:
    """Find the start/end of value within text.  Raises if not found."""
    idx = text.find(value)
    if idx == -1:
        # Try fuzzy: remove extra spaces
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
    """Generate variants of a given example by replacing PII values.

    For each entity in the example, generate `multiplier` new values.
    Then create one new example per combination set (using same replacement
    index across all entities so names/emails stay consistent within a variant).
    """
    entity_types_in_ex = [e["type"] for e in ex["entities"]]
    # Generate replacement pools for each entity type
    type_pools: dict[str, list[tuple[str, str, str]]] = {}
    for et in set(entity_types_in_ex):
        gen_fn = GENERATORS.get(et)
        if gen_fn:
            type_pools[et] = gen_fn(max(multiplier * 2, 5))
        else:
            type_pools[et] = [(et, e["value"], "") for e in ex["entities"] if e["type"] == et]

    variants: list[dict[str, Any]] = []
    for idx in range(multiplier):
        # Build replacements for each entity position
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
            # Build text: use the original surrounding context but replace the value
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
        # Append suffix
        text_parts.append(ex["text"][last_end:])
        new_text = "".join(text_parts)
        # Update start/end relative to new_text
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
#  Pure generation (non-variant) — produce standalone examples from scratch
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

# Target counts per entity type for the expanded dataset
# These ensure each type has at least ~35+ examples for statistical significance
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
    """Load existing examples from dataset."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    return raw.get("examples", [])


def count_entity_types(examples: list[dict[str, Any]]) -> Counter:
    c: Counter = Counter()
    for ex in examples:
        for e in ex["entities"]:
            c[e["type"]] += 1
    return c


def generate_pure_examples(existing_counts: Counter) -> list[dict[str, Any]]:
    """Generate standalone examples from scratch for types that need more."""
    new_examples: list[dict[str, Any]] = []
    entity_counts = Counter(existing_counts)

    for ent_type, target in sorted(TARGET_ENTITY_COUNTS.items()):
        needed = target - entity_counts.get(ent_type, 0)
        if needed <= 0:
            continue

        gen_fn = GENERATORS.get(ent_type)
        if not gen_fn:
            continue

        generated = gen_fn(needed * 3)  # generate extra to have variety
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
    """Generate compound examples containing multiple entity types."""
    examples: list[dict[str, Any]] = []

    # Person + email
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
        # Calculate spans
        for ent in entities:
            val = ent["value"]
            idx = context.find(val)
            if idx != -1:
                ent["start"] = idx
                ent["end"] = idx + len(val)
        examples.append(make_example(context, [e for e in entities if e["start"] > 0]))

    # Phone + address
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

    # SSN + DOB
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

    # IP + domain + server
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

    # Credit card + JWT
    for _ in range(count // 10):
        cc = random.choice(["4111111111111111", "5500000000000004", "378282246310005"])
        formatted = f"{cc[0:4]}-{cc[4:8]}-{cc[8:12]}-{cc[12:]}"
        jwt = f"eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.{'e30' + ''.join(random.choices('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789', k=30))}.{'SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c'}"
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
    """Generate targeted examples for types needing a specific count."""
    examples: list[dict[str, Any]] = []

    for ent_type, target in target_counts.items():
        gen_fn = GENERATORS.get(ent_type)
        if not gen_fn:
            continue
        # Generate directly to hit the target
        generated = gen_fn(target)
        for _type, val, ctx in generated:
            text = ctx
            entities = []
            try:
                start, end = find_span(text, val)
                entities.append({"type": ent_type, "value": val, "start": start, "end": end})
                # Add a secondary entity sometimes (person, company, city)
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
    """Generate the complete expanded dataset."""
    existing = load_existing(DEFAULT_SOURCE)
    existing_counts = count_entity_types(existing)

    print(f"Existing examples: {len(existing)}")
    print(f"Existing entities: {sum(existing_counts.values())}")
    print(f"Entity type distribution:")
    for t, c in sorted(existing_counts.items()):
        needed = TARGET_ENTITY_COUNTS.get(t, 0) - c
        print(f"  {t}: {c} (need {max(0, needed)} more)")
    print()

    # Generate new examples to fill gaps
    pure_new = generate_pure_examples(existing_counts)
    print(f"Generated {len(pure_new)} pure-type examples\n")

    # Generate mixed examples (multiple entity types together)
    mixed = generate_mixed_examples(300)
    print(f"Generated {len(mixed)} mixed-type examples\n")

    # Re-count after pure + mixed additions
    combined = existing + pure_new + mixed
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
            f"Expanded from original {len(existing)} examples to {len(combined)} for statistical significance."
        ),
        "version": "2.0.0",
        "examples": combined,
    }

    return dataset


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate expanded PII detection dataset (1000+ examples)"
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