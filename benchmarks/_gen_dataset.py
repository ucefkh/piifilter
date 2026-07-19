#!/usr/bin/env python3
"""Regenerate the labeled dataset with correct character positions."""
import json
from pathlib import Path

EXAMPLES = [
    # ── Standard PII ─────────────────────────────────────────────────
    {"text": "Hi, I'm Alice Johnson from Acme Corp. Email: alice@acme.com Phone: +1-555-123-4567",
     "entities": ["PERSON:Alice Johnson", "COMPANY:Acme Corp", "EMAIL:alice@acme.com", "PHONE:+1-555-123-4567"]},

    {"text": "Our office is at 350 Fifth Avenue, New York, NY 10118",
     "entities": ["ADDRESS:350 Fifth Avenue, New York, NY 10118"]},

    {"text": "Paris has a population of over 2 million people and is the capital of France.",
     "entities": ["CITY:Paris", "COUNTRY:France"]},

    {"text": "My bank account is 123456789012 and my IBAN is DE89 3704 0044 0532 0130 00",
     "entities": ["BANK_ACCOUNT:123456789012", "IBAN:DE89 3704 0044 0532 0130 00"]},

    {"text": "Credit card: 4111-1111-1111-1111 and another card 5500 0000 0000 0004",
     "entities": ["CREDIT_CARD:4111-1111-1111-1111", "CREDIT_CARD:5500 0000 0000 0004"]},

    {"text": "My passport is AB1234567 and my SSN is 987-65-4321",
     "entities": ["PASSPORT:AB1234567", "SOCIAL_SECURITY:987-65-4321"]},

    {"text": "The server IP is 192.168.1.100 and the backup is 10.0.0.5",
     "entities": ["IP_ADDRESS:192.168.1.100", "IP_ADDRESS:10.0.0.5"]},

    {"text": "JWT token: eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNvrBuFQiulGqjDh0g",
     "entities": ["JWT:eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNvrBuFQiulGqjDh0g"]},

    {"text": "API key: sk-abcdef1234567890abcdef1234567890abcdef12",
     "entities": ["API_KEY:sk-abcdef1234567890abcdef1234567890abcdef12"]},

    {"text": "SSH key: -----BEGIN OPENSSH PRIVATE KEY-----\nABC123...\n-----END OPENSSH PRIVATE KEY-----",
     "entities": ["SSH_KEY:-----BEGIN OPENSSH PRIVATE KEY-----"]},

    {"text": "Database URL: postgresql://admin:secret@db.internal:5432/production",
     "entities": ["DATABASE_URL:postgresql://admin:secret@db.internal:5432/production"]},

    {"text": "Internal URL: https://jenkins.internal:8080/job/deploy and https://admin.corp.intranet/login",
     "entities": ["PRIVATE_URL:https://jenkins.internal:8080/job/deploy", "PRIVATE_URL:https://admin.corp.intranet/login"]},

    {"text": "Domain: google.com and api.github.com and my-site.internal",
     "entities": ["DOMAIN:google.com", "DOMAIN:api.github.com", "DOMAIN:my-site.internal"]},

    {"text": "Coordinates: 40.7128, -74.0060 (NYC) and lat: 51.5074, lon: -0.1278 (London)",
     "entities": ["GPS:40.7128", "GPS:-74.0060", "GPS:51.5074", "GPS:-0.1278"]},

    {"text": "File path: /home/alice/projects/src/main/config.yaml and C:\\Users\\Bob\\Documents\\report.pdf",
     "entities": ["FILE_PATH:/home/alice/projects/src/main/config.yaml", "FILE_PATH:C:\\Users\\Bob\\Documents\\report.pdf"]},

    {"text": "Project: Project Phoenix is our codename for the new ERP rollout.",
     "entities": ["PROJECT_NAME:Project Phoenix"]},

    {"text": "Our customer Jane Smith from Widgets Inc. wants her data removed.",
     "entities": ["CUSTOMER_NAME:Jane Smith", "COMPANY:Widgets Inc."]},

    {"text": "Employee Bob Marley from accounting needs VPN access to 10.88.0.1",
     "entities": ["EMPLOYEE_NAME:Bob Marley", "IP_ADDRESS:10.88.0.1"]},

    {"text": "Contact me at bob.smith@example.org or call +44 20 7946 0958 for the project Vulcan.",
     "entities": ["EMAIL:bob.smith@example.org", "PHONE:+44 20 7946 0958", "PROJECT_NAME:project Vulcan"]},

    {"text": "The best customer we have is Clara Oswald and she works at Data Corp.",
     "entities": ["CUSTOMER_NAME:Clara Oswald", "COMPANY:Data Corp"]},

    {"text": "Please add employee David Tennant to the access list for project Galactic.",
     "entities": ["EMPLOYEE_NAME:David Tennant", "PROJECT_NAME:project Galactic"]},

    {"text": "Visit us at 10 Downing Street, London, SW1A 2AA",
     "entities": ["ADDRESS:10 Downing Street, London, SW1A 2AA", "CITY:London"]},

    {"text": "Located in Berlin, Germany - our HQ is at Unter den Linden 1, 10117 Berlin",
     "entities": ["CITY:Berlin", "COUNTRY:Germany", "ADDRESS:Unter den Linden 1, 10117 Berlin"]},

    {"text": "Send to: maria.garcia@co.jp | CC: info@company.co.uk | BCC: devops@internal.corp",
     "entities": ["EMAIL:maria.garcia@co.jp", "EMAIL:info@company.co.uk", "EMAIL:devops@internal.corp"]},

    {"text": "Token: eyJraWQiOiIxMjMiLCJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJhZG1pbiJ9.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c",
     "entities": ["JWT:eyJraWQiOiIxMjMiLCJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJhZG1pbiJ9.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"]},

    {"text": "API key: pk-98765fedcba0987654321fedcba0987654321fedcba",
     "entities": ["API_KEY:pk-98765fedcba0987654321fedcba0987654321fedcba"]},

    {"text": "Redis connection: redis://default:password@cache-cluster.internal:6379",
     "entities": ["DATABASE_URL:redis://default:password@cache-cluster.internal:6379"]},

    {"text": "MongoDB: mongodb://admin:secret@mongo-prod.internal:27017/sales",
     "entities": ["DATABASE_URL:mongodb://admin:secret@mongo-prod.internal:27017/sales"]},

    {"text": "SSH config: -----BEGIN EC PRIVATE KEY-----\nMHcCAQEEIIxYb...\n-----END EC PRIVATE KEY-----",
     "entities": ["SSH_KEY:-----BEGIN EC PRIVATE KEY-----"]},

    {"text": "Coordinates: 48.8566 N, 2.3522 E is the center of Paris",
     "entities": ["GPS:48.8566", "GPS:2.3522"]},

    {"text": "Passport: CD987654 and also passport XY123456",
     "entities": ["PASSPORT:CD987654", "PASSPORT:XY123456"]},

    {"text": "SSN: 123-45-6789 and also 456-78-9012",
     "entities": ["SOCIAL_SECURITY:123-45-6789", "SOCIAL_SECURITY:456-78-9012"]},

    {"text": "CC: 3782-822463-10005 (Amex) and 6011-1111-1111-1117 (Discover)",
     "entities": ["CREDIT_CARD:3782-822463-10005", "CREDIT_CARD:6011-1111-1111-1117"]},

    {"text": "Bank: 98765432109876543210 and IBAN: GB29 NWBK 6016 1331 9268 19",
     "entities": ["BANK_ACCOUNT:98765432109876543210", "IBAN:GB29 NWBK 6016 1331 9268 19"]},

    {"text": "Private: https://localhost:3000/dashboard and http://127.0.0.1/api/health",
     "entities": ["PRIVATE_URL:https://localhost:3000/dashboard", "PRIVATE_URL:http://127.0.0.1/api/health"]},

    {"text": "File paths: /var/log/nginx/access.log and /etc/ssh/sshd_config",
     "entities": ["FILE_PATH:/var/log/nginx/access.log", "FILE_PATH:/etc/ssh/sshd_config"]},

    {"text": "Our CEO Bob Smith (bob@company.com) approved the merger.",
     "entities": ["PERSON:Bob Smith", "EMAIL:bob@company.com"]},

    {"text": "IT: www.example.com, support@help.io, 192.168.0.1, and /tmp/test/data/cache.log",
     "entities": ["DOMAIN:www.example.com", "EMAIL:support@help.io", "IP_ADDRESS:192.168.0.1"]},

    {"text": "Connect as user: postgresql://app_user:Str0ng!Pass@db-prod.internal:5432/analytics",
     "entities": ["DATABASE_URL:postgresql://app_user:Str0ng!Pass@db-prod.internal:5432/analytics"]},

    {"text": "The employee named John (employee John) can access server 10.0.0.50",
     "entities": ["EMPLOYEE_NAME:John", "IP_ADDRESS:10.0.0.50"]},

    {"text": "Customer: Martha Jones (martha.jones@bigpharma.com) order #ORD-001",
     "entities": ["CUSTOMER_NAME:Martha Jones", "EMAIL:martha.jones@bigpharma.com"]},

    {"text": "Project Nebula starts Q1 and Project Orion is in maintenance mode.",
     "entities": ["PROJECT_NAME:Project Nebula", "PROJECT_NAME:Project Orion"]},

    {"text": "IPv6 address: 2001:0db8:85a3:0000:0000:8a2e:0370:7334",
     "entities": ["IP_ADDRESS:2001:0db8:85a3:0000:0000:8a2e:0370:7334"]},

    {"text": "Compressed IPv6: 2001:db8::1 and fe80::1",
     "entities": ["IP_ADDRESS:2001:db8::1", "IP_ADDRESS:fe80::1"]},

    {"text": "Home address: 123 Maple Drive, Springfield, IL 62704, USA",
     "entities": ["ADDRESS:123 Maple Drive, Springfield, IL 62704, USA"]},

    {"text": "Person: Dr. Sarah Chen works at Microsoft Research in Redmond",
     "entities": ["PERSON:Dr. Sarah Chen", "COMPANY:Microsoft Research", "CITY:Redmond"]},

    {"text": "City pop: Tokyo (37M), Delhi (32M), Shanghai (28M)",
     "entities": ["CITY:Tokyo", "CITY:Delhi", "CITY:Shanghai"]},

    {"text": "Countries: Canada, Australia, Japan, Brazil, India, Egypt",
     "entities": ["COUNTRY:Canada", "COUNTRY:Australia", "COUNTRY:Japan", "COUNTRY:Brazil", "COUNTRY:India", "COUNTRY:Egypt"]},

    {"text": "SSN: 111-22-3333 is used as the sample number",
     "entities": ["SOCIAL_SECURITY:111-22-3333"]},

    {"text": "IPv4: 10.10.10.10, 172.16.0.1, 192.168.10.255",
     "entities": ["IP_ADDRESS:10.10.10.10", "IP_ADDRESS:172.16.0.1", "IP_ADDRESS:192.168.10.255"]},

    {"text": "Phone: +1-212-555-0198 and (415) 555-2671 and 555-123-4567",
     "entities": ["PHONE:+1-212-555-0198", "PHONE:(415) 555-2671", "PHONE:555-123-4567"]},

    {"text": "Email: test.user+tag@mail.company.io",
     "entities": ["EMAIL:test.user+tag@mail.company.io"]},

    {"text": "Email: firstname_lastname@mail-server.co.jp",
     "entities": ["EMAIL:firstname_lastname@mail-server.co.jp"]},

    {"text": "Domain: subdomain.company.example.org and a.io",
     "entities": ["DOMAIN:subdomain.company.example.org", "DOMAIN:a.io"]},

    {"text": "Lat: 35.6762, Lng: 139.6503 (Tokyo) and latitude: -33.8688, longitude: 151.2093 (Sydney)",
     "entities": ["GPS:35.6762", "GPS:139.6503", "GPS:-33.8688", "GPS:151.2093"]},

    {"text": "GPS: 27.1751 N, 78.0421 E (Taj Mahal)",
     "entities": ["GPS:27.1751", "GPS:78.0421"]},

    {"text": "File: /opt/application/config/production/settings.json",
     "entities": ["FILE_PATH:/opt/application/config/production/settings.json"]},

    {"text": "File: /home/user/tmp/cache/data",
     "entities": ["FILE_PATH:/home/user/tmp/cache/data"]},

    {"text": "SSH key: -----BEGIN RSA PRIVATE KEY-----\nProc-Type: 4,ENCRYPTED\n-----END RSA PRIVATE KEY-----",
     "entities": ["SSH_KEY:-----BEGIN RSA PRIVATE KEY-----"]},

    {"text": "SSH: -----BEGIN DSA PRIVATE KEY-----\nMIIBvAIB...\n-----END DSA PRIVATE KEY-----",
     "entities": ["SSH_KEY:-----BEGIN DSA PRIVATE KEY-----"]},

    {"text": "MySQL: mysql://dev_user:dev_pass@mysql-dev.internal:3306/staging",
     "entities": ["DATABASE_URL:mysql://dev_user:dev_pass@mysql-dev.internal:3306/staging"]},

    {"text": "SQLite: sqlite:///data/db/production.db",
     "entities": ["DATABASE_URL:sqlite:///data/db/production.db"]},

    {"text": "Oracle: oracle://scott:tiger@oracle.internal:1521/XEPDB1",
     "entities": ["DATABASE_URL:oracle://scott:tiger@oracle.internal:1521/XEPDB1"]},

    {"text": "IBAN: FR76 3000 6000 0112 3456 7890 189",
     "entities": ["IBAN:FR76 3000 6000 0112 3456 7890 189"]},

    {"text": "IBAN: CH93 0076 2011 6238 5295 7",
     "entities": ["IBAN:CH93 0076 2011 6238 5295 7"]},

    {"text": "Passport num: EF12345678",
     "entities": ["PASSPORT:EF12345678"]},

    {"text": "API key: api_key_abcdef1234567890abcdef1234567890",
     "entities": ["API_KEY:api_key_abcdef1234567890abcdef1234567890"]},

    {"text": "Token: secret_a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0",
     "entities": ["API_KEY:secret_a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0"]},

    {"text": "Domain: example.internal and mysql.corp.local and api.staging.private",
     "entities": ["DOMAIN:example.internal", "DOMAIN:mysql.corp.local", "DOMAIN:api.staging.private"]},

    {"text": "Employee: Rose Tyler (rose@torchwood.xyz), employee: Jack Harkness (jack@torchwood.xyz)",
     "entities": ["EMPLOYEE_NAME:Rose Tyler", "EMAIL:rose@torchwood.xyz", "EMPLOYEE_NAME:Jack Harkness", "EMAIL:jack@torchwood.xyz"]},

    {"text": "Customer: Amy Pond (amy.pond@weeping-angels.com) - project Pandorica",
     "entities": ["CUSTOMER_NAME:Amy Pond", "EMAIL:amy.pond@weeping-angels.com", "PROJECT_NAME:project Pandorica"]},

    {"text": "Contact person: Donna Noble (donna@temp-services.co.uk). Project Bad Wolf is GO.",
     "entities": ["PERSON:Donna Noble", "EMAIL:donna@temp-services.co.uk", "PROJECT_NAME:Project Bad Wolf"]},

    {"text": "Bank: 1234567890123456 and account: 8765432109876543",
     "entities": ["BANK_ACCOUNT:1234567890123456", "BANK_ACCOUNT:8765432109876543"]},

    {"text": "CC: 4111111111111111 and 5500000000000004 (no dashes)",
     "entities": ["CREDIT_CARD:4111111111111111", "CREDIT_CARD:5500000000000004"]},

    {"text": "Private endpoint: https://control-plane.internal:8443/api/v1/config",
     "entities": ["PRIVATE_URL:https://control-plane.internal:8443/api/v1/config"]},

    {"text": "Local: http://localhost:4000/graphql for the playground",
     "entities": ["PRIVATE_URL:http://localhost:4000/graphql"]},

    {"text": "Internal app: https://payroll.corp.local/admin",
     "entities": ["PRIVATE_URL:https://payroll.corp.local/admin"]},

    {"text": "City: The population of Mumbai is over 20 million.",
     "entities": ["CITY:Mumbai"]},

    {"text": "Country: Switzerland has 4 official languages.",
     "entities": ["COUNTRY:Switzerland"]},

    {"text": "The server at 10.0.0.1 handles requests from 192.168.1.50 to 172.16.0.10",
     "entities": ["IP_ADDRESS:10.0.0.1", "IP_ADDRESS:192.168.1.50", "IP_ADDRESS:172.16.0.10"]},

    {"text": "Phone: +49 30 12345678 (Berlin office)",
     "entities": ["PHONE:+49 30 12345678"]},

    {"text": "Phone: 07700 900 123 (UK mobile)",
     "entities": ["PHONE:07700 900 123"]},

    {"text": "JWT: eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ",
     "entities": ["JWT:eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ"]},

    {"text": "JWT with sig: eyJhbGciOiJIUzUxMiJ9.eyJzdWIiOiJhZG1pbiJ9.V0rtziRdmiYSdgCwTSAOfFzQxPmuZLLO4ZTjvOEM_Oo",
     "entities": ["JWT:eyJhbGciOiJIUzUxMiJ9.eyJzdWIiOiJhZG1pbiJ9.V0rtziRdmiYSdgCwTSAOfFzQxPmuZLLO4ZTjvOEM_Oo"]},

    {"text": "API: pk-a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6",
     "entities": ["API_KEY:pk-a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6"]},

    {"text": "File: D:\\Projects\\Backup\\2024\\financial\\statements.xlsx",
     "entities": ["FILE_PATH:D:\\Projects\\Backup\\2024\\financial\\statements.xlsx"]},

    {"text": "GPS: lat: 55.7558, lng: 37.6173 (Moscow) and lat: 59.9343, lng: 30.3351 (SPB)",
     "entities": ["GPS:55.7558", "GPS:37.6173", "GPS:59.9343", "GPS:30.3351"]},

    {"text": "Employee: Mickey Smith (mickey@ctos.earth) for project Last Centurion",
     "entities": ["EMPLOYEE_NAME:Mickey Smith", "EMAIL:mickey@ctos.earth", "PROJECT_NAME:project Last Centurion"]},

    {"text": "Customer: River Song (river@library.silence) - project Impossible Astronaut",
     "entities": ["CUSTOMER_NAME:River Song", "EMAIL:river@library.silence", "PROJECT_NAME:project Impossible Astronaut"]},

    # ── Negative examples (NO PII) ─────────────────────────────────────
    {"text": "The quick brown fox jumps over the lazy dog.", "entities": []},
    {"text": "Meeting at 2 PM tomorrow in the conference room B.", "entities": []},
    {"text": "The price of milk is $3.50 at the local grocery store.", "entities": []},
    {"text": "Please review the quarterly report before Friday.", "entities": []},
    {"text": "The server maintenance is scheduled for this weekend.", "entities": []},
    {"text": "User typed a phone-like number: 123-456-7890 but this is not a real phone.", "entities": []},
    {"text": "My street is 123 Main Street, not 123 Main St.", "entities": []},
    {"text": "Version 3.1.4 is the latest release of the software package.", "entities": []},
    {"text": "The year 2025 will be important for our company growth.", "entities": []},
    {"text": "Please use ticket number TKT-12345 for the bug report.", "entities": []},
    {"text": "What does a@b or x@y mean? These arent real emails - short local parts.", "entities": []},
    {"text": "The value 555-1212 is often used in TV shows as a fake number.", "entities": []},
    {"text": "The address is at 42 Wallaby Way, Sydney (famous from Finding Nemo).", "entities": []},
    {"text": "User 192.168.x.x is a common notation for private networks.", "entities": []},
    {"text": "The parameter --api_endpoint should use https://example.com/api.", "entities": []},

    # ── Unicode / International PII ────────────────────────────────────
    {"text": "Unicode PII: 联系用户张伟，邮箱是zhangwei@example.cn，电话+86 138-0013-8000",
     "entities": ["PERSON:张伟", "EMAIL:zhangwei@example.cn", "PHONE:+86 138-0013-8000"]},

    {"text": "Arabic: اتصل بـ أحمد على ahmed@example.sa أو +966 55 123 4567",
     "entities": ["PERSON:أحمد", "EMAIL:ahmed@example.sa", "PHONE:+966 55 123 4567"]},

    {"text": "Russian: Иван Иванов, email: ivan@example.ru, тел: +7 495 123-45-67",
     "entities": ["PERSON:Иван Иванов", "EMAIL:ivan@example.ru", "PHONE:+7 495 123-45-67"]},

    {"text": "Japanese: 田中太郎のメールはtanaka@example.jp、電話は+81 90-1234-5678",
     "entities": ["PERSON:田中太郎", "EMAIL:tanaka@example.jp", "PHONE:+81 90-1234-5678"]},

    {"text": "Greek: O Γιώργος έχει email: giorgos@example.gr",
     "entities": ["PERSON:Γιώργος", "EMAIL:giorgos@example.gr"]},

    # ── Edge cases ─────────────────────────────────────────────────────
    {"text": "Very long JWT: eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiYWRtaW4iOnRydWUsImlhdCI6MTUxNjIzOTAyMiwiZXhwIjoxNTE2MjQyNjIyfQ.HV1nKqHCpGmxzk8TMJcCnFmv5LmEHkzF1J7c5XiSgFX4pSxFrraoYUFX_NOeFgl3iDTPsoB8bSblV_QfGLxt_A",
     "entities": ["JWT:eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiYWRtaW4iOnRydWUsImlhdCI6MTUxNjIzOTAyMiwiZXhwIjoxNTE2MjQyNjIyfQ.HV1nKqHCpGmxzk8TMJcCnFmv5LmEHkzF1J7c5XiSgFX4pSxFrraoYUFX_NOeFgl3iDTPsoB8bSblV_QfGLxt_A"]},

    {"text": "mixed RTL/LTR: my email is john@doe.com and my phone is +972 50 123 4567 שלום",
     "entities": ["EMAIL:john@doe.com", "PHONE:+972 50 123 4567"]},

    {"text": "Base64 encoded email: dGVzdEBleGFtcGxlLmNvbQ== looks like a token but its an email",
     "entities": []},

    {"text": "Partially redacted: My credit card is ****-****-****-1111 and SSN is ***-**-6789",
     "entities": []},

    {"text": "Redacted phone: XXX-XXX-7890 and email: xxxx@domain.com",
     "entities": []},

    {"text": "Person: James researcher published his findings in Nature at London University.",
     "entities": []},

    {"text": "SSN-like: 987654321 is just a long number, not an SSN (no dashes).",
     "entities": []},

    {"text": "Phone-like: 5552368 is short sequence, not enough digits for phone.",
     "entities": []},

    {"text": "Email-like: admin@localhost is technically valid but internal-only.",
     "entities": []},

    {"text": "Domain: 123 is not a valid domain name by itself.",
     "entities": []},

    {"text": "Path: tmp/foo/bar is relative, not absolute, so not a FILE_PATH.",
     "entities": []},

    {"text": "Base64 encoded SSN: MTIzLTQ1LTY3ODk= in base64, detectors should not decode this",
     "entities": []},

    {"text": "JWT-like in text: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ...flQpDQEf4RZwtYVgYkY9wQfF0sZgRv8nKpLmNvXzUxM",
     "entities": []},
]

def build_example(text, entities):
    """Build an example with auto-computed positions."""
    result_entities = []
    for ent in entities:
        typ, val = ent.split(":", 1)
        start = text.find(val)
        assert start >= 0, f"Value {val!r} not found in text: {text!r}"
        result_entities.append({
            "type": typ,
            "value": val,
            "start": start,
            "end": start + len(val),
        })
    return {"text": text, "entities": result_entities}

output = {
    "description": "PIIFilter Detection Recall Benchmark Dataset — 122 labeled examples covering all 24 entity types plus edge cases and negatives. Auto-generated with verified positions.",
    "version": "1.1.0",
    "examples": [build_example(e["text"], e["entities"]) for e in EXAMPLES],
}

# Validate
for i, ex in enumerate(output["examples"]):
    for j, ent in enumerate(ex["entities"]):
        assert ent["start"] <= ent["end"], f"#{i} ent#{j}: start > end"
        assert ent["end"] <= len(ex["text"]), f"#{i} ent#{j}: end {ent['end']} > len {len(ex['text'])}"
        actual = ex["text"][ent["start"]:ent["end"]]
        assert actual == ent["value"], f"#{i} ent#{j}: |{actual}| != |{ent['value']}|"

# Write
Path("benchmarks/data/pii_dataset.json").write_text(json.dumps(output, indent=2, ensure_ascii=False))
print(f"Written {len(output['examples'])} examples")
total_ents = sum(len(ex["entities"]) for ex in output["examples"])
print(f"Total entities: {total_ents}")
types = sorted(set(ent["type"] for ex in output["examples"] for ent in ex["entities"]))
print(f"Entity types ({len(types)}): {types}")
print("All positions verified correct.")