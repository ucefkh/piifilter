"""Shared utilities for PIIFilter."""

from __future__ import annotations

import hashlib
import json
import re
import time
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any


def generate_alias(text: str, seed: str = "deterministic") -> str:
    """Generate a deterministic alias for a given text.

    Uses the text hash to pick from a curated set of replacement names,
    ensuring the same original always maps to the same alias.
    """
    # Categorized alias pools for realistic semantic replacement
    alias_pools = {
        "PERSON": [
            "Janette", "Michael", "Sarah", "David", "Emma", "James",
            "Olivia", "William", "Sophia", "Alexander", "Isabella", "Ethan",
            "Mia", "Daniel", "Charlotte", "Benjamin", "Amelia", "Henry",
        ],
        "CUSTOMER_NAME": [
            "Acme Corp", "Globex Inc", "Initech", "Hooli", "Stark Industries",
            "Wayne Enterprises", "Oscorp", "Cyberdyne Systems",
        ],
        "EMPLOYEE_NAME": [
            "Taylor", "Jordan", "Morgan", "Casey", "Riley", "Avery",
            "Quinn", "Skyler", "Peyton", "Drew",
        ],
        "COMPANY": [
            "TechCorp", "DataSystems", "CloudNine", "NexGen", "AlphaByte",
            "QuantumSoft", "Pinnacle", "OmniCorp",
        ],
        "CITY": [
            "Metropolis", "Central City", "Star City", "Coast City",
            "Gotham", "Midtown", "Bayview", "Riverside",
        ],
        "COUNTRY": [
            "Northern Region", "Southern District", "Eastern Province",
            "Western Territory", "Central State",
        ],
        "STREET": [
            "Main Street", "Oak Avenue", "Elm Drive", "Park Lane",
            "Broadway", "Highland Road", "Cedar Court",
        ],
        "ADDRESS": [
            "a downtown business district",
            "a major metropolitan business district",
            "an urban commercial center",
            "a corporate office park",
            "a central business hub",
        ],
        "PHONE": ["[PHONE REDACTED]"],
        "EMAIL": ["[EMAIL REDACTED]"],
    }

    norm = text.lower().strip()
    h = int(hashlib.md5((seed + norm).encode()).hexdigest(), 16)

    # Detect entity type from regex hints
    if re.search(r'\b[\w.+-]+@[\w-]+\.[\w.-]+\b', norm):
        pool = alias_pools["EMAIL"]
    elif re.search(r'[,]\s*(?:Inc|Corp|LLC|Ltd|GmbH|SA)\b', text, re.IGNORECASE) or text.istitle() and len(text.split()) <= 3:
        pool = alias_pools["COMPANY"]
    elif re.search(r'\b(?:Mr|Mrs|Ms|Dr)\.?\s+\w+\b', text, re.IGNORECASE) or text.istitle() and len(text.split()) == 1:
        pool = alias_pools["PERSON"]
    else:
        for key in ["STREET", "ADDRESS", "CITY", "COUNTRY"]:
            pool = alias_pools.get(key, alias_pools["PERSON"])
            if key == "STREET":
                if any(w in norm for w in ["street", "avenue", "road", "drive", "lane", "court", "boulevard"]):
                    break
        else:
            pool = alias_pools["PERSON"]

    pool = alias_pools.get("PERSON", alias_pools["PERSON"])
    # Better type detection
    if any(w in text.lower() for w in ["street", "avenue", "road", "boulevard"]):
        pool = alias_pools.get("ADDRESS", alias_pools["PERSON"])
    elif re.search(r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b', norm) and len(norm) >= 10:
        pool = alias_pools["PHONE"]
    elif re.search(r'\b[\w.+-]+@[\w-]+\.[\w.-]+\b', norm):
        pool = alias_pools["EMAIL"]
    elif text.istitle() and len(text.split()) <= 4:
        if len(text.split()) == 1:
            pool = alias_pools["PERSON"]
        else:
            pool = alias_pools["COMPANY"]

    return pool[h % len(pool)]


def mask_text(text: str, entity_type: str = "PERSON") -> str:
    """Mask text with entity type label."""
    return f"[{entity_type}]"


def time_it(func):
    """Decorator to measure function execution time in ms."""
    async def wrapper(*args, **kwargs):
        start = time.perf_counter()
        result = await func(*args, **kwargs)
        elapsed = (time.perf_counter() - start) * 1000
        if isinstance(result, tuple) and hasattr(result[-1], '__setitem__'):
            pass  # handled by caller
        return result, elapsed
    return wrapper


def truncate_prompt(text: str, max_len: int = 100_000) -> str:
    """Truncate prompt to prevent abuse."""
    if len(text) > max_len:
        return text[:max_len] + "\n[...truncated]"
    return text


def config_hash(cfg: Any) -> str:
    """Generate a hash of the config for health checks."""
    raw = json.dumps(cfg.model_dump() if hasattr(cfg, 'model_dump') else cfg, sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()[:12]


__all__ = [
    "generate_alias",
    "mask_text",
    "time_it",
    "truncate_prompt",
    "config_hash",
]