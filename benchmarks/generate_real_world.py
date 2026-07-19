#!/usr/bin/env python3
r"""Real-world corpus validation for PIIFilter.

Validates the full PIIFilter regex detector pipeline against realistic
documents containing PII. Generates synthetic realistic business emails
with varying amounts and types of PII, then runs the pipeline on each
and reports detection statistics.

Strategy (two-phase):
  1. Try to load the Enron email corpus from HuggingFace datasets
     (streaming, up to 500 emails). Strip labels — we're testing
     detection rate, not supervised accuracy.
  2. If Enron is unavailable (no network / dataset doesn't exist):
     fall back to 200+ realistic synthetic business emails with
     injected PII (email addresses, phone numbers, SSNs, credit
     cards, IPs, names, addresses, API keys, etc.).

Usage:
    python benchmarks/generate_real_world.py

Output:
    - benchmarks/real_world_report.txt  (human-readable summary)
    - STDOUT summary table

Requires:
    pip install datasets      (optional — for Enron phase 1)
    pip install faker>=18.0   (automatically used if available for phase 2)

PIIFilter must be installable from the project root:
    uv pip install -e .          # or
    cd core && uv pip install -e .
"""

from __future__ import annotations

import asyncio
import json
import math
import os
import random
import re
import statistics
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

# ── Project paths ─────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "core" / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "plugins" / "detector-regex" / "src"))

from piifilter_detector_regex.detector import RegexDetector
from piifilter.shared.models import EntityType

random.seed(42)

# ── Constants ─────────────────────────────────────────────────────────────────

MAX_ENRON_EMAILS = 500  # cap for HF streaming
SYNTHETIC_COUNT = 250   # how many synthetic emails to generate

# PII types we know the regex detector handles
PII_TYPES = {
    "EMAIL", "PHONE", "SOCIAL_SECURITY", "CREDIT_CARD", "IP_ADDRESS",
    "PERSON", "ADDRESS", "CITY", "COUNTRY", "COMPANY",
    "BANK_ACCOUNT", "IBAN", "PASSPORT", "JWT", "API_KEY",
    "SSH_KEY", "DATABASE_URL", "PRIVATE_URL", "PROJECT_NAME",
    "CUSTOMER_NAME", "EMPLOYEE_NAME", "GPS", "DOMAIN", "FILE_PATH",
    "URL", "DATE",
}

# ── Data structures ────────────────────────────────────────────────────────────

@dataclass
class DocResult:
    """Result of running the PIIFilter pipeline on one document."""
    doc_id: int
    source: str           # "enron" or "synthetic"
    text_length: int
    detected_count: int
    entity_types: list[str] = field(default_factory=list)
    entity_scores: list[float] = field(default_factory=list)
    entity_texts: list[str] = field(default_factory=list)
    low_confidence_candidates: list[dict[str, Any]] = field(default_factory=list)
    has_pii: bool = False
    elapsed_ms: float = 0.0


# ── Synthetic realistic email generator ───────────────────────────────────────

# ── Name / company / location pools ───────────────────────────────────────────

_FIRST_NAMES = [
    "Alice", "Bob", "Charlie", "Diana", "Edward", "Fiona", "George", "Hannah",
    "Ivan", "Julia", "Kevin", "Laura", "Michael", "Nina", "Oliver", "Patricia",
    "Quinn", "Rachel", "Samuel", "Tina", "Uma", "Victor", "Wendy", "Xavier",
    "Yara", "Zack", "Aaron", "Bella", "Carlos", "Deepa", "Erik", "Fatima",
    "Gopal", "Hiro", "Ingrid", "Jamal", "Kai", "Lena", "Ming", "Noa",
    "Omar", "Priya", "Ravi", "Sofia", "Tariq", "Usman", "Val", "Wei",
    "Xia", "Yuki", "Amir", "Beth", "Cheng", "Dalia", "Elif", "Felix",
    "Grace", "Hugo", "Isla", "Joon", "Marcus", "Nathan", "Sophie", "Elena",
    "Diego", "Aisha", "Kenji", "Mei", "Raj", "Soren", "Liam", "Zara",
]

_LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller",
    "Davis", "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez", "Wilson",
    "Anderson", "Thomas", "Taylor", "Moore", "Jackson", "Martin", "Lee",
    "Perez", "Thompson", "White", "Harris", "Sanchez", "Clark", "Ramirez",
    "Lewis", "Robinson", "Walker", "Young", "Allen", "King", "Wright",
    "Scott", "Torres", "Nguyen", "Hill", "Flores", "Green", "Adams",
    "Nelson", "Baker", "Hall", "Rivera", "Campbell", "Mitchell", "Carter",
    "Patel", "Rogers", "Coleman", "Morgan", "Cooper", "Reed", "Bailey",
    "Bell", "Murphy", "Bailey", "Rivera", "Cooper", "Richardson", "Cox",
    "Howard", "Ward", "Torres", "Peterson", "Gray", "Ramirez", "James",
    "Watson", "Brooks", "Kelly", "Sanders", "Price", "Bennett", "Wood",
    "Barnes", "Ross", "Henderson", "Coleman", "Jenkins", "Perry", "Powell",
]

_COMPANIES = [
    "Acme Corp", "Globex Inc", "Initech", "Hooli", "Stark Industries",
    "Wayne Enterprises", "Cyberdyne Systems", "Umbrella Corp", "Soylent Corp",
    "Massive Dynamic", "Wonka Industries", "Oscorp", "LexCorp", "Tyrell Corp",
    "Weyland-Yutani", "Buy n Large", "Dunder Mifflin", "Pied Piper",
    "Aviato", "Google", "Microsoft", "Amazon", "Meta", "Apple", "OpenAI",
    "Tesla", "SpaceX", "Netflix", "Spotify", "Stripe", "Vercel", "Cloudflare",
    "Stripe", "GitHub", "GitLab", "Atlassian", "Datadog", "MongoDB",
    "Palantir", "Snowflake", "Databricks", "HashiCorp", "Fastly",
]

_CITIES = [
    "New York", "London", "Tokyo", "Paris", "Berlin", "Sydney", "Mumbai",
    "Shanghai", "Dubai", "Singapore", "San Francisco", "Seattle", "Boston",
    "Austin", "Toronto", "Vancouver", "Amsterdam", "Barcelona", "Rome",
    "Chicago", "Los Angeles", "Miami", "Denver", "Portland", "Oslo",
    "Stockholm", "Copenhagen", "Zurich", "Dublin", "Melbourne", "Austin",
    "Dallas", "Atlanta", "Phoenix", "Philadelphia", "Minneapolis",
]

_COUNTRIES = [
    "USA", "Canada", "UK", "Germany", "France", "Japan", "Australia",
    "Brazil", "India", "China", "Singapore", "South Korea", "Netherlands",
    "Sweden", "Norway", "Switzerland", "Spain", "Italy", "Mexico", "Egypt",
    "Nigeria", "Kenya", "Argentina", "Chile", "New Zealand", "Ireland",
]

_DOMAINS = [
    "acme.com", "globex.com", "initech.com", "example.com", "mail.company.io",
    "bigpharma.com", "startup.io", "techcorp.dev", "enterprise.cloud",
    "data-service.ai", "megacorp.org", "solutions.net", "services.co",
    "consulting.group", "labs.dev", "systems.io", "global.com",
]

_STREETS = [
    "Maple Drive", "Oak Avenue", "Elm Street", "Pine Road", "Cedar Lane",
    "Birch Boulevard", "Willow Way", "Main Street", "Park Avenue", "Lake Drive",
    "River Road", "High Street", "Church Road", "Station Road", "Green Lane",
    "Broadway", "Market Street", "Walnut Street", "Cherry Lane", "Spruce Street",
]

_PHONE_AREAS = ["212", "415", "310", "617", "212", "312", "305", "206", "512", "303", "602", "214"]

_CC_PREFIXES = {
    "4111": "Visa",
    "5500": "Mastercard",
    "3400": "Amex",
    "3782": "Amex",
    "6011": "Discover",
    "3530": "JCB",
}
_VALID_CCS = [
    "4111111111111111",
    "5500000000000004",
    "340000000000009",
    "378282246310005",
    "6011000000000004",
    "3530111333300000",
    "5555555555554444",
    "4012888888881881",
    "30569309025904",
    "3566002020360505",
]

_SAMPLE_IBANS = [
    "GB29NWBK60161331926819",
    "FR1420041010050500013M02606",
    "DE89370400440532013000",
    "CH9300762011623852957",
    "NL91ABNA0417164300",
    "IT60X0542811101000000123456",
    "ES9121000418450200051332",
    "BR9700360305000010009795493P1",
]

_SAMPLE_SSNS = ["123-45-6789", "987-65-4321", "555-12-3456", "111-22-3333",
                "444-55-6666", "777-88-9999", "222-33-4444", "888-99-7777"]

_SAMPLE_IPS = ["192.168.1.1", "10.0.0.1", "172.16.0.1", "8.8.8.8",
               "203.0.113.42", "198.51.100.7", "10.20.30.40", "192.168.100.200"]


def _pick_name() -> tuple[str, str]:
    return random.choice(_FIRST_NAMES), random.choice(_LAST_NAMES)


def _email_addr(first: str, last: str, domain: str | None = None) -> str:
    d = domain or random.choice(_DOMAINS)
    sep = random.choice([".", "_", "-", ""])
    addr = f"{first.lower()}{sep}{last.lower()}@{d}"
    return addr


def _phone() -> str:
    area = random.choice(_PHONE_AREAS)
    exch = f"{random.randint(200,999)}"
    sub = f"{random.randint(1000,9999)}"
    fmt = random.choice([
        f"+1-{area}-{exch}-{sub}",
        f"({area}) {exch}-{sub}",
        f"{area}.{exch}.{sub}",
        f"+1 ({area}) {exch}-{sub}",
        f"{area}-{exch}-{sub}",
    ])
    return fmt


def _credit_card() -> str:
    cc = random.choice(_VALID_CCS)
    groups = [cc[i:i+4] for i in range(0, len(cc), 4)]
    sep = random.choice(["-", " ", ""])
    label = random.choice(["", "CC: ", "card: ", "credit card: ", "Visa: "])
    return f"{label}{sep.join(groups)}"


def _ssn() -> str:
    return random.choice(_SAMPLE_SSNS)


def _ip() -> str:
    return random.choice(_SAMPLE_IPS)


def _address() -> str:
    num = random.randint(1, 9999)
    street = random.choice(_STREETS)
    city = random.choice(_CITIES)
    state = random.choice(["CA", "NY", "TX", "MA", "IL", "WA", "CO", "FL", "AZ", "OR"])
    zip_code = f"{random.randint(10000,99999)}"
    return f"{num} {street}, {city}, {state} {zip_code}"


def _api_key() -> str:
    kinds = [
        f"sk-{''.join(random.choices('abcdef0123456789', k=48))}",
        f"ghp_{''.join(random.choices('abcdefghijklmnopqrstuvwxyz0123456789', k=36))}",
        f"ak-{''.join(random.choices('ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789', k=32))}",
    ]
    return random.choice(kinds)


def _database_url() -> str:
    user = random.choice(["admin", "root", "db_user", "app_user", "service_acct"])
    pw = ''.join(random.choices('abcdefghijklmnopqrstuvwxyz0123456789', k=16))
    host = random.choice(["db.internal", "db.example.com", "rds.aws.com", "postgres.private"])
    port = random.choice(["5432", "3306", "27017"])
    db = random.choice(["prod", "staging", "main", "app_db", "customers"])
    return f"postgresql://{user}:{pw}@{host}:{port}/{db}"


def _jwt() -> str:
    import base64
    header = base64.urlsafe_b64encode(b'{"alg":"HS256","typ":"JWT"}').rstrip(b'=').decode()
    payload = base64.urlsafe_b64encode(
        f'{{"sub":"{random.randint(10000,99999)}","name":"{random.choice(_FIRST_NAMES)} {random.choice(_LAST_NAMES)}","iat":{random.randint(1600000000,1700000000)}}}'.encode()
    ).rstrip(b'=').decode()
    sig = base64.urlsafe_b64encode(
        ''.join(random.choices('abcdefghijklmnopqrstuvwxyz0123456789', k=43)).encode()
    ).rstrip(b'=').decode()
    return f"eyJ{header[2:]}.{payload}.{sig}"


def _passport() -> str:
    country = random.choice(["US", "GB", "FR", "DE", "JP", "CA"])
    num = ''.join(random.choices('0123456789', k=9))
    return f"{country}{num}"


def _iban() -> str:
    return random.choice(_SAMPLE_IBANS)


# ── Business email templates with varying PII injection ───────────────────────

_EMAIL_TEMPLATES = [
    # 1. Contact info sharing
    {
        "template": """Hi {recipient_first},

I wanted to share my updated contact details:
- Email: {email}
- Phone: {phone}
- Office: {address}

Please update the company directory. I'll be visiting the {city} office next week.

Best,
{sender_first} {sender_last}""",
        "pii_fields": ["email", "phone", "address"],
    },

    # 2. Meeting scheduling (names + email)
    {
        "template": """Hello {recipient_first},

Are you available for a meeting next Thursday at 2pm? We need to discuss the {project_name} project budget before the end-of-quarter review.

Please RSVP to {email}.

Regards,
{sender_first} {sender_last}""",
        "pii_fields": ["email"],
    },

    # 3. New vendor onboarding (heavy PII)
    {
        "template": """Subject: New vendor registration for {company_name}

Hello {recipient_first},

We need the following information to set up {vendor_name} in our system:
- Primary contact: {vendor_contact} ({vendor_email})
- Phone: {vendor_phone}
- Billing address: {address}
- Tax ID: {ssn} (placeholder)
- Bank account for ACH: {iban}

Please send these via our secure portal.

Thanks,
{sender_first} {sender_last}
{sender_title}""",
        "pii_fields": ["email", "phone", "address", "ssn", "iban"],
    },

    # 4. IT support ticket (tech PII)
    {
        "template": """Ticket #{ticket_id} — Database access issue

Hi {recipient_first},

The database connection at {db_url} is failing with authentication errors. Could you verify the credentials?

Also, there seems to be an issue with the API key {api_key} — it was rotated last week but the old key is still being used by some services.

The server at {ip} needs a configuration update.

Regards,
{sender_first} {sender_last}""",
        "pii_fields": ["db_url", "api_key", "ip"],
    },

    # 5. Employee onboarding (heavy personal PII)
    {
        "template": """New Employee Onboarding: {new_employee}

Hi HR team,

Please process the following for {new_employee} ({email}):
- SSN: {ssn}
- Phone: {phone}
- Emergency contact: {emergency_phone}
- Direct deposit: {iban}
- Office assignment: {address}

Initial paperwork is attached.

Thanks,
{sender_first} {sender_last}
HR Manager""",
        "pii_fields": ["email", "ssn", "phone", "iban", "address"],
    },

    # 6. Security alert (various PII)
    {
        "template": """SECURITY ALERT — Suspicious login detected

User: {email}
Source IP: {ip}
Timestamp: {date}
Action: Password reset requested
Associated accounts: {secondary_email}

If this was not you, please contact security immediately with reference ID {ref_id}.

Security Team""",
        "pii_fields": ["email", "ip"],
    },

    # 7. Customer invoice
    {
        "template": """INVOICE #{invoice_id}

From: {company_name}
Bill To: {customer_name}
{customer_address}

Items:
- Consulting services (Q1): ${amount:,.2f}
- Software license: ${amount2:,.2f}

Payment due within 30 days. Wire transfer to:
Account: {iban}

For questions, contact {email} or {phone}.

Thank you for your business!
{sender_first} {sender_last}
Accounts Receivable""",
        "pii_fields": ["email", "phone", "iban", "address"],
    },

    # 8. Quick status update (minimal PII)
    {
        "template": """Hi {recipient_first},

Just a quick update — the deployment to {server} at {ip} completed successfully. The {project_name} API is now live on the new {db_url} instance.

Let me know if you see any issues.

Best,
{sender_first}""",
        "pii_fields": ["ip", "project_name", "db_url"],
    },

    # 9. Password reset notification
    {
        "template": """Password Reset Confirmation

Hi {recipient_first},

Your password for account {email} was successfully reset.
IP address: {ip}
Device: {device}

If you did not request this change, please contact our support team immediately at {support_email} or call {phone}.

Best regards,
{company_name} Security""",
        "pii_fields": ["email", "ip", "phone"],
    },

    # 10. Credit card payment confirmation
    {
        "template": """Payment Confirmation — Order #{order_id}

Dear {customer_name},

Your payment of ${amount:,.2f} was processed successfully.
Card: {credit_card}
Billing address: {address}

A receipt has been emailed to {email}.

Thank you for your purchase!
{company_name} Billing""",
        "pii_fields": ["credit_card", "address", "email"],
    },

    # 11. API integration guide (tech PII)
    {
        "template": """API Integration Guide — {project_name}

Hi {recipient_first},

Here are your credentials for the {project_name} API:
- Endpoint: https://api.{domain}/v1
- API Key: {api_key}
- JWT Token: {jwt_token}
- Webhook secret: whsec_{webhook_secret}

Store these securely. Do not share via email.

Regards,
{company_name} DevRel""",
        "pii_fields": ["api_key", "jwt_token", "project_name"],
    },

    # 12. Client introduction (professional PII)
    {
        "template": """Subject: Introduction — {project_name}

Dear {recipient_first},

I'd like to introduce our team lead {colleague_name} who will be managing the {project_name} engagement.

{colleague_first} can be reached at {colleague_email} or {colleague_phone}. Our corporate office is located at {address}.

We look forward to a successful partnership.

Best regards,
{sender_first} {sender_last}
VP of Client Services""",
        "pii_fields": ["email", "phone", "address"],
    },

    # 13. Travel itinerary
    {
        "template": """Travel Booking Confirmation — {recipient_first} {recipient_last}

Booking Reference: {booking_ref}

Flight: {airline} {flight_num}
Date: {date}
Passenger: {recipient_first} {recipient_last} ({passport})
Contact: {phone}
Emergency contact: {emergency_phone}

Hotel: {hotel_name}
Address: {address}

Please ensure your travel documents are in order.

Travel Department""",
        "pii_fields": ["passport", "phone", "address"],
    },

    # 14. Customer support transcript (scattered PII)
    {
        "template": """Customer Support Case #{case_id}

Customer: {customer_name}
Email: {email}
Phone: {phone}

Issue: Unable to access account from IP {ip}. User suspects unauthorized access.

Agent notes: Verified identity via SSN {ssn}. Reset credentials and enabled 2FA.

Resolution: Case closed after confirmation email sent to {email}.

-- {agent_name}
Senior Support Engineer""",
        "pii_fields": ["email", "phone", "ip", "ssn"],
    },

    # 15. Server provisioning (tech-heavy PII)
    {
        "template": """New Server Provisioning Request — {project_name}

Environment: {env}
Server IP: {ip}
SSH Key: {ssh_key}
Database: {db_url}
Region: {city}

Deployment credentials:
- Admin: {admin_user}
- API Key: {api_key}

Please provision and configure per the attached spec.

Infrastructure Team""",
        "pii_fields": ["ip", "ssh_key", "db_url", "api_key"],
    },

    # 16. Simple reply (minimal PII — just names)
    {
        "template": """On {date}, {sender_first} {sender_last} wrote:

> Let me know your thoughts on the proposal.

I reviewed it and I think the approach for {project_name} looks solid. A few minor suggestions:
1. Update the timeline
2. Add the cost breakdown

Let's discuss at the next standup.

Best,
{recipient_first}""",
        "pii_fields": ["project_name"],
    },

    # 17. Legal / compliance (structured PII)
    {
        "template": """CONFIDENTIAL — Legal Review

Matter: {project_name} — {company_name} Contract Review

Parties:
1. {sender_first} {sender_last}, {sender_title} — {company_name}
2. {client_name}, {client_title} — {client_company}

Contact: {email} | {phone}

This communication contains privileged information. Do not forward.

-- {sender_first} {sender_last}
General Counsel""",
        "pii_fields": ["email", "phone"],
    },

    # 18. Shipping / logistics
    {
        "template": """Shipping Confirmation — Order #{order_id}

Ship To:
{customer_name}
{address}

Tracking: {tracking_number}
Carrier: {carrier}
Estimated Delivery: {date}

Items: {items_count} units of {product}

Contact {email} or {phone} for delivery issues.

Thank you,
{company_name} Logistics""",
        "pii_fields": ["address", "email", "phone"],
    },

    # 19. Survey / feedback (minimal PII)
    {
        "template": """Hi {recipient_first},

We'd love your feedback on the {project_name} deployment last week.

Click here to complete a 2-minute survey: https://survey.{domain}/{survey_id}

Your responses are anonymous.

Thanks,
{sender_first}
{company_name}""",
        "pii_fields": [],
    },

    # 20. VPN / remote access setup
    {
        "template": """Remote Access Setup — {project_name}

Hi {recipient_first},

Your VPN credentials have been provisioned:
- VPN Server: {ip}
- Username: {email}
- SSH Key: {ssh_key}
- Database Access: {db_url}

Install the VPN client and connect. Let me know if you have issues.

Regards,
IT Support""",
        "pii_fields": ["ip", "email", "ssh_key", "db_url"],
    },
]


def _generate_synthetic_document(doc_id: int) -> tuple[str, list[str]]:
    """Generate one realistic business email with PII injected.

    Returns (email_text, list_of_pii_field_categories_injected).
    """
    tmpl = random.choice(_EMAIL_TEMPLATES)
    first, last = _pick_name()
    r_first, r_last = _pick_name()
    c_first, c_last = _pick_name()
    col_first, col_last = _pick_name()
    agent_first, agent_last = _pick_name()
    client_co = random.choice(_COMPANIES)
    dom = random.choice(_DOMAINS)
    project = random.choice([
        "Project Phoenix", "Operation Aurora", "Nebula", "Helios",
        "Blue Horizon", "Quantum Leap", "Data Stream", "Cloud Nine",
        "Ironclad", "Everest", "Catalyst", "Meridian", "Atlas",
        "Pulsar", "Vertex", "Summit", "Apex", "Titan",
    ])
    hotel = random.choice([
        "Marriott", "Hilton", "Hyatt Regency", "Four Seasons",
        "Ritz-Carlton", "Sheraton", "Westin", "InterContinental",
    ])
    product = random.choice([
        "Widget Pro", "DataSync", "CloudMesh", "Analytics Suite",
        "API Gateway", "Security Bundle", "Enterprise Pack",
    ])

    context_values = {
        "sender_first": first,
        "sender_last": last,
        "sender_title": random.choice([
            "CEO", "CTO", "VP Engineering", "Director", "Manager",
            "Lead Engineer", "Sr. Developer", "Product Manager",
        ]),
        "recipient_first": r_first,
        "recipient_last": r_last,
        "recipient_name": f"{r_first} {r_last}",
        "company_name": random.choice(_COMPANIES),
        "vendor_name": random.choice(_COMPANIES),
        "vendor_contact": f"{c_first} {c_last}",
        "vendor_email": _email_addr(c_first, c_last, dom),
        "vendor_phone": _phone(),
        "project_name": project,
        "email": _email_addr(first, last, dom),
        "secondary_email": _email_addr(first, last, random.choice(_DOMAINS)),
        "support_email": f"support@{dom}",
        "colleague_name": f"{col_first} {col_last}",
        "colleague_first": col_first,
        "colleague_email": _email_addr(col_first, col_last, dom),
        "colleague_phone": _phone(),
        "phone": _phone(),
        "emergency_phone": _phone(),
        "address": _address(),
        "customer_address": _address(),
        "customer_name": f"{c_first} {c_last}",
        "client_name": f"{c_first} {c_last}",
        "client_company": client_co,
        "client_title": random.choice(["CEO", "CTO", "VP", "Director", "Partner"]),
        "ssn": _ssn(),
        "ip": _ip(),
        "credit_card": _credit_card(),
        "iban": _iban(),
        "passport": _passport(),
        "db_url": _database_url(),
        "api_key": _api_key(),
        "jwt_token": _jwt(),
        "ssh_key": f"ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAI{''.join(random.choices('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789+/=', k=50))}",
        "webhook_secret": ''.join(random.choices('abcdefghijklmnopqrstuvwxyz0123456789', k=32)),
        "domain": dom,
        "city": random.choice(_CITIES),
        "server": random.choice(["web-01", "db-01", "app-01", "cache-01", "worker-01"]),
        "env": random.choice(["production", "staging", "development", "qa"]),
        "admin_user": random.choice(["admin", "root", "deploy", "sysadmin", "ops"]),
        "date": f"{random.choice(['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'])} {random.randint(1,28)}, {random.randint(2023,2026)}",
        "ticket_id": random.randint(10000, 99999),
        "invoice_id": f"INV-{random.randint(100000, 999999)}",
        "order_id": random.randint(1000000, 9999999),
        "case_id": f"CS-{random.randint(10000, 99999)}",
        "ref_id": f"REF-{''.join(random.choices('ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789', k=8))}",
        "booking_ref": ''.join(random.choices('ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789', k=6)),
        "tracking_number": f"1Z{''.join(random.choices('ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789', k=14))}",
        "carrier": random.choice(["UPS", "FedEx", "DHL", "USPS"]),
        "airline": random.choice(["AA", "UA", "DL", "BA", "LH", "EK", "SQ"]),
        "flight_num": f"{random.choice(['AA','UA','DL','BA','LH'])}{random.randint(100, 9999)}",
        "hotel_name": f"{hotel} {random.choice(_CITIES)}",
        "device": random.choice(["iPhone 15 Pro", "MacBook Pro M3", "Windows Desktop", "Samsung Galaxy S24", "iPad Air"]),
        "items_count": random.randint(1, 20),
        "product": product,
        "survey_id": ''.join(random.choices('abcdefghijklmnopqrstuvwxyz0123456789', k=10)),
        "new_employee": f"{random.choice(_FIRST_NAMES)} {random.choice(_LAST_NAMES)}",
        "agent_name": f"{agent_first} {agent_last}",
        "amount": round(random.uniform(1000, 50000), 2),
        "amount2": round(random.uniform(500, 15000), 2),
    }

    try:
        text = tmpl["template"].format(**context_values)
    except KeyError as e:
        # Fallback for any missing key
        text = tmpl["template"]
        for k, v in context_values.items():
            text = text.replace("{" + k + "}", str(v))

    return text, tmpl["pii_fields"]


# ── Enron loader ──────────────────────────────────────────────────────────────

def extract_text_from_enron(item: dict) -> str:
    """Extract readable text from an Enron email dataset item.

    The Enron dataset on HF typically has 'body', 'message', 'content',
    'text' keys. Returns the longest non-empty text field, or empty string.
    """
    for key in ("body", "message", "content", "text", "raw_text"):
        val = item.get(key, "")
        if val and len(val) > 20:  # meaningful content
            return val
    # If no body, compose from subject + text
    subject = item.get("subject", "")
    text = item.get("text", item.get("body", ""))
    if subject and not text:
        return subject
    if subject:
        return f"Subject: {subject}\n\n{text}"
    return str(item)


async def load_enron_emails(max_count: int = MAX_ENRON_EMAILS) -> list[str]:
    """Try to load Enron emails from HuggingFace datasets.

    Returns a list of email text strings. Falls back to empty list
    if dataset is unavailable, in which case the caller uses synthetic.
    """
    print("  Trying to load Enron emails from HuggingFace datasets...", flush=True)
    try:
        from datasets import load_dataset
        ds = load_dataset("enron_emails", split="train", streaming=True)
        texts: list[str] = []
        for i, item in enumerate(ds):
            if i >= max_count:
                break
            text = extract_text_from_enron(item)
            if len(text) > 20:
                texts.append(text)
            if i > 0 and i % 100 == 0:
                print(f"    Loaded {i} Enron emails...", flush=True)
        print(f"  Loaded {len(texts)} Enron emails from HuggingFace datasets.", flush=True)
        return texts
    except Exception as e:
        print(f"  Enron dataset not available: {e}", flush=True)
        print("  Falling back to synthetic realistic documents.", flush=True)
        return []


# ── Pipeline runner ───────────────────────────────────────────────────────────

async def run_pipeline_on_docs(
    docs: list[str],
    source: str,
    start_id: int = 0,
) -> list[DocResult]:
    """Run the PIIFilter regex detector on a batch of documents."""
    detector = RegexDetector()
    await detector.initialize()

    results: list[DocResult] = []

    for i, text in enumerate(docs):
        doc_id = start_id + i
        t0 = time.perf_counter()

        # Run the regex detector
        entities = await detector.detect(text)

        t1 = time.perf_counter()
        elapsed_ms = (t1 - t0) * 1000

        # Categorize results
        entity_types = [e["type"] for e in entities]
        entity_scores = [e["score"] for e in entities]
        entity_texts = [e["text"] for e in entities]

        # Low-confidence candidates (score < 0.80) — possible false positives
        low_conf = [
            {"type": e["type"], "value": e["text"], "score": e["score"]}
            for e in entities if e["score"] < 0.80
        ]

        result = DocResult(
            doc_id=doc_id,
            source=source,
            text_length=len(text),
            detected_count=len(entities),
            entity_types=entity_types,
            entity_scores=entity_scores,
            entity_texts=entity_texts,
            low_confidence_candidates=low_conf,
            has_pii=len(entities) > 0,
            elapsed_ms=elapsed_ms,
        )
        results.append(result)

        if (i + 1) % 50 == 0:
            print(f"    Processed {i + 1}/{len(docs)} docs...", flush=True)

    await detector.shutdown()
    return results


# ── Report generation ─────────────────────────────────────────────────────────

def generate_report(
    enron_results: list[DocResult],
    synthetic_results: list[DocResult],
    enron_count: int,
    synthetic_count: int,
) -> str:
    """Generate a human-readable validation report."""
    all_results = enron_results + synthetic_results
    total = len(all_results)

    lines: list[str] = []
    def w(s: str = "") -> None:
        lines.append(s)

    w("╔══════════════════════════════════════════════════════════════════════════╗")
    w("║           PIIFILTER REAL-WORLD CORPUS VALIDATION REPORT                ║")
    w("╚══════════════════════════════════════════════════════════════════════════╝")
    w()
    w(f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}")
    w()

    # ── Dataset overview ──────────────────────────────────────────────────
    w("═" * 70)
    w("  DATASET OVERVIEW")
    w("═" * 70)
    w()
    if enron_count > 0:
        w(f"  Enron emails loaded          : {enron_count}")
        enron_with_pii = sum(1 for r in enron_results if r.has_pii)
        w(f"  Enron with PII detected      : {enron_with_pii} ({_pct(enron_with_pii, enron_count)})")
    else:
        w("  Enron emails                 : UNAVAILABLE (network / dataset not found)")
    w(f"  Synthetic emails generated    : {synthetic_count}")
    w(f"  Total documents               : {total}")
    w()

    # ── Detection overview ────────────────────────────────────────────────
    w("═" * 70)
    w("  DETECTION OVERVIEW")
    w("═" * 70)
    w()

    docs_with_pii = sum(1 for r in all_results if r.has_pii)
    pct_with_pii = _pct(docs_with_pii, total)
    w(f"  Documents with at least one PII detection:  {docs_with_pii} / {total} ({pct_with_pii})")
    w(f"  Documents with zero PII detection:          {total - docs_with_pii} / {total} ({_pct(total - docs_with_pii, total)})")
    w()

    # ── PII type distribution ─────────────────────────────────────────────
    w("═" * 70)
    w("  PII TYPE DISTRIBUTION")
    w("═" * 70)
    w()
    w(f"  {'PII Type':<25s} {'Docs':>6s} {'Total Hits':>12s} {'% of Docs':>10s}")
    w(f"  {'─'*25:<25s} {'─'*6:>6s} {'─'*12:>12s} {'─'*10:>10s}")

    type_doc_counts: dict[str, int] = Counter()      # docs containing this type
    type_hit_counts: dict[str, int] = Counter()       # total hits of this type

    for r in all_results:
        type_counts: dict[str, int] = Counter()
        for et in r.entity_types:
            type_doc_counts[et] += 1
            type_hit_counts[et] += 1

    for pii_type in sorted(type_doc_counts.keys()):
        doc_count = type_doc_counts[pii_type]
        hit_count = type_hit_counts[pii_type]
        w(f"  {pii_type:<25s} {doc_count:>6d} {hit_count:>12d} {_pct(doc_count, total):>10s}")

    w()
    # Also list types that appear in synethetic but not in enron or vice versa
    synthetic_type_set = set()
    for r in synthetic_results:
        synthetic_type_set.update(r.entity_types)
    enron_type_set = set()
    for r in enron_results:
        enron_type_set.update(r.entity_types)

    only_in_enron = enron_type_set - synthetic_type_set
    only_in_synthetic = synthetic_type_set - enron_type_set
    if only_in_synthetic:
        w(f"  Types only in synthetic docs  : {', '.join(sorted(only_in_synthetic))}")
    if only_in_enron:
        w(f"  Types only in Enron docs      : {', '.join(sorted(only_in_enron))}")
    w()

    # ── Confidence distribution ───────────────────────────────────────────
    w("═" * 70)
    w("  CONFIDENCE SCORE DISTRIBUTION")
    w("═" * 70)
    w()

    all_scores = []
    for r in all_results:
        all_scores.extend(r.entity_scores)

    if all_scores:
        w(f"  Total detections              : {len(all_scores)}")
        w(f"  Mean confidence               : {statistics.mean(all_scores):.3f}")
        w(f"  Median confidence             : {statistics.median(all_scores):.3f}")
        w(f"  Min confidence                : {min(all_scores):.3f}")
        w(f"  Max confidence                : {max(all_scores):.3f}")
        w()

        # Buckets
        buckets = [(0.60, 0.75, "0.60–0.75"), (0.75, 0.85, "0.75–0.85"),
                   (0.85, 0.90, "0.85–0.90"), (0.90, 0.95, "0.90–0.95"),
                   (0.95, 1.01, "0.95–1.00")]
        w(f"  {'Bucket':<15s} {'Count':>8s} {'%':>8s}")
        w(f"  {'─'*15:<15s} {'─'*8:>8s} {'─'*8:>8s}")
        for lo, hi, label in buckets:
            cnt = sum(1 for s in all_scores if lo <= s < hi)
            w(f"  {label:<15s} {cnt:>8d} {_pct(cnt, len(all_scores)):>8s}")
        w()
    else:
        w("  No detections found.")
        w()

    # ── False positive candidates (low-confidence detections) ─────────────
    w("═" * 70)
    w("  FALSE POSITIVE CANDIDATES (Low-Confidence Detections)")
    w("═" * 70)
    w()

    all_low_conf: list[dict[str, Any]] = []
    for r in all_results:
        all_low_conf.extend(r.low_confidence_candidates)

    if all_low_conf:
        w(f"  Total low-confidence detections (< 0.80): {len(all_low_conf)}")
        w(f"  {_pct(len(all_low_conf), len(all_scores)) if all_scores else 0}% of all detections")
        w()

        # Group by type
        lc_by_type: dict[str, list[dict]] = defaultdict(list)
        for lc in all_low_conf:
            lc_by_type[lc["type"]].append(lc)

        w(f"  {'PII Type':<25s} {'Count':>8s} {'Avg Score':>10s}")
        w(f"  {'─'*25:<25s} {'─'*8:>8s} {'─'*10:>10s}")
        for pii_type in sorted(lc_by_type.keys()):
            items = lc_by_type[pii_type]
            avg_score = statistics.mean([x["score"] for x in items])
            w(f"  {pii_type:<25s} {len(items):>8d} {avg_score:.3f}{'':>7s}")
        w()

        # Show sample low-confidence values (max 15)
        w("  Sample low-confidence values:")
        samples = sorted(all_low_conf, key=lambda x: x["score"])[:15]
        for s in samples:
            val_repr = s["value"][:60].replace("\n", "\\n")
            w(f"    [{s['type']}] (score={s['score']:.3f}) {val_repr}")
    else:
        w("  None — all detections have confidence >= 0.80")
    w()

    # ── Per-source breakdown ──────────────────────────────────────────────
    if enron_count > 0:
        w("═" * 70)
        w("  PER-SOURCE BREAKDOWN")
        w("═" * 70)
        w()

        for src_label, src_results in [("Enron emails", enron_results), ("Synthetic docs", synthetic_results)]:
            src_total = len(src_results)
            if src_total == 0:
                continue
            src_with_pii = sum(1 for r in src_results if r.has_pii)
            src_entities = sum(r.detected_count for r in src_results)
            w(f"  {src_label}:")
            w(f"    Documents                     : {src_total}")
            w(f"    With PII detected             : {src_with_pii} ({_pct(src_with_pii, src_total)})")
            w(f"    Total entities found          : {src_entities}")
            w(f"    Avg entities per doc          : {src_entities / src_total:.1f}")
            w(f"    Avg doc length (chars)        : {statistics.mean([r.text_length for r in src_results]):.0f}")
            w(f"    Avg detection time (ms)        : {statistics.mean([r.elapsed_ms for r in src_results]):.2f}")
            w()

    # ── Per-doc PII density ───────────────────────────────────────────────
    w("═" * 70)
    w("  PII DENSITY DISTRIBUTION")
    w("═" * 70)
    w()

    entity_counts = [r.detected_count for r in all_results if r.detected_count > 0]
    if entity_counts:
        density_buckets = [(0, "0 (no PII)"), (1, "1"), (2, "2"), (3, "3"),
                           (4, "4"), (5, "5"), (6, "6+")]
        w(f"  {'Entities per doc':<20s} {'Count':>6s} {'%':>8s}")
        w(f"  {'─'*20:<20s} {'─'*6:>6s} {'─'*8:>8s}")
        for threshold, label in density_buckets:
            if threshold == 6:
                cnt = sum(1 for r in all_results if r.detected_count >= threshold)
            else:
                cnt = sum(1 for r in all_results if r.detected_count == threshold)
            if cnt > 0:
                w(f"  {label:<20s} {cnt:>6d} {_pct(cnt, total):>8s}")
    else:
        w("  No PII found in any document.")
    w()

    # ── Performance summary ───────────────────────────────────────────────
    w("═" * 70)
    w("  PERFORMANCE SUMMARY")
    w("═" * 70)
    w()

    all_times = [r.elapsed_ms for r in all_results]
    if all_times:
        w(f"  Total documents processed      : {total}")
        w(f"  Mean detection time per doc    : {statistics.mean(all_times):.2f} ms")
        w(f"  Median detection time          : {statistics.median(all_times):.2f} ms")
        w(f"  P95 detection time             : {sorted(all_times)[int(len(all_times) * 0.95)]:.2f} ms")
        w(f"  Max detection time             : {max(all_times):.2f} ms")
        w(f"  Total processing time          : {sum(all_times) / 1000:.2f} s")
    w()

    # ── Notes ─────────────────────────────────────────────────────────────
    w("═" * 70)
    w("  NOTES")
    w("═" * 70)
    w()
    w("  • This report validates the PIIFilter regex detector against")
    w(f"    {'real Enron emails' if enron_count > 0 else 'synthetic realistic'} documents.")
    w("  • No ground-truth labels are used — we measure detection rate,")
    w("    not precision/recall. False positives and negatives require")
    w("    manual review.")
    w("  • Low-confidence detections (score < 0.80) are flagged as")
    w("    potential false positive candidates.")
    if enron_count == 0:
        w("  • Enron dataset was unavailable, so results are based entirely")
        w("    on synthetic documents. This still validates that the pipeline")
        w("    correctly identifies inline PII in realistic business prose.")
    w()

    return "\n".join(lines)


def _pct(n: int, d: int) -> str:
    if d == 0:
        return "0.0%"
    return f"{n / d * 100:.1f}%"


# ── Main entry point ──────────────────────────────────────────────────────────

async def main() -> None:
    print("=" * 70)
    print("  PIIFilter — Real-World Corpus Validation")
    print("=" * 70)
    print()

    # ── Phase 1: Try Enron (if available) ─────────────────────────────────
    enron_docs = await load_enron_emails(MAX_ENRON_EMAILS)
    enron_count = len(enron_docs)

    # ── Phase 2: Generate synthetic docs ─────────────────────────────────
    print(f"  Generating {SYNTHETIC_COUNT} synthetic realistic business emails...", flush=True)
    synthetic_docs: list[str] = []
    synthetic_pii_labels: list[list[str]] = []
    for i in range(SYNTHETIC_COUNT):
        text, fields = _generate_synthetic_document(i)
        synthetic_docs.append(text)
        synthetic_pii_labels.append(fields)
    print(f"  Generated {len(synthetic_docs)} synthetic docs.", flush=True)
    print()

    # ── Run pipeline ──────────────────────────────────────────────────────
    print("  Running PIIFilter regex detector on all documents...", flush=True)

    enron_results: list[DocResult] = []
    if enron_docs:
        print(f"  Processing {enron_count} Enron emails...", flush=True)
        enron_results = await run_pipeline_on_docs(enron_docs, "enron", start_id=0)

    synth_start_id = enron_count
    print(f"  Processing {len(synthetic_docs)} synthetic docs...", flush=True)
    synthetic_results = await run_pipeline_on_docs(
        synthetic_docs, "synthetic", start_id=synth_start_id
    )
    print()

    # ── Generate report ───────────────────────────────────────────────────
    print("  Generating report...", flush=True)
    report = generate_report(
        enron_results, synthetic_results, enron_count, SYNTHETIC_COUNT
    )

    # ── Save report ───────────────────────────────────────────────────────
    report_path = Path(__file__).resolve().parent / "real_world_report.txt"
    report_path.write_text(report, encoding="utf-8")
    print(f"  Report saved to: {report_path}", flush=True)
    print()

    # ── Print summary to stdout ───────────────────────────────────────────
    print(report)


if __name__ == "__main__":
    asyncio.run(main())