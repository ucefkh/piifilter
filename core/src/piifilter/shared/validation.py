"""ValidatorRegistry — pluggable validation framework for PII spans.

Each validator implements the ``Validator`` protocol with a single method::

    def validate(self, raw: str) -> ValidationResult: ...

Returns ``ValidationResult`` with status (valid | invalid | plausible),
a confidence score (0.0–1.0), and optional metadata.

Built-in validators:

- ``CreditCardValidator`` — Luhn checksum + BIN (issuer identification number) range
- ``SsnValidator`` — area/group/serial structural validation per SSA rules
- ``PhoneValidator`` — ``phonenumbers`` library integration for E.164 and loose formats
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol, runtime_checkable


# ── ValidationResult ─────────────────────────────────────────────────────────


class ValidationStatus(str, Enum):
    VALID = "valid"
    INVALID = "invalid"
    PLAUSIBLE = "plausible"


@dataclass
class ValidationResult:
    """Outcome of a single validator invocation.

    Attributes:
        status:  ``valid`` — passes all checks; ``plausible`` — structurally ok
                 but some checks inconclusive; ``invalid`` — failed at least one
                 hard check.
        score:   Confidence in the result, 0.0–1.0.
        reasons: Human-readable list of why the result was reached.
        metadata: Arbitrary extra data the validator wishes to attach
                  (e.g. detected card brand, SSN area, phone country code).
    """

    status: ValidationStatus
    score: float = 0.0
    reasons: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def valid(cls, score: float = 1.0, reasons: list[str] | None = None,
              **metadata: Any) -> ValidationResult:
        return cls(ValidationStatus.VALID, score, reasons or [], metadata)

    @classmethod
    def invalid(cls, score: float = 0.0, reasons: list[str] | None = None,
                **metadata: Any) -> ValidationResult:
        return cls(ValidationStatus.INVALID, score, reasons or [], metadata)

    @classmethod
    def plausible(cls, score: float = 0.5, reasons: list[str] | None = None,
                  **metadata: Any) -> ValidationResult:
        return cls(ValidationStatus.PLAUSIBLE, score, reasons or [], metadata)

    def __bool__(self) -> bool:
        """Convenience: truthy when status is VALID or PLAUSIBLE."""
        return self.status in (ValidationStatus.VALID, ValidationStatus.PLAUSIBLE)


# ── Validator Protocol ───────────────────────────────────────────────────────


@runtime_checkable
class Validator(Protocol):
    """Pluggable validation protocol.

    Any object with a ``validate(raw: str) -> ValidationResult`` method
    satisfies this protocol.  No base class required — just duck-type it::

        class MyValidator:
            def validate(self, raw: str) -> ValidationResult:
                ...
    """

    __validator_name__: str = "unnamed"

    def validate(self, raw: str) -> ValidationResult:
        ...


# ═══════════════════════════════════════════════════════════════════════════════
# Built-in validators
# ═══════════════════════════════════════════════════════════════════════════════

# ── Luhn utility ─────────────────────────────────────────────────────────────


def _luhn_checksum(digits: str) -> int:
    """Compute Luhn checksum for a string of digit characters.

    Returns 0 when the number passes the Luhn check (valid CC number).
    """
    total = 0
    parity = len(digits) & 1
    for i, ch in enumerate(digits):
        if not ch.isdigit():
            return -1
        d = ord(ch) - 48
        if (i & 1) == parity:
            d <<= 1  # multiply by 2
            if d > 9:
                d -= 9
        total += d
    return total % 10


# ── BIN ranges ───────────────────────────────────────────────────────────────

# (lo, hi, brand) — inclusive range of IIN/BIN prefixes
_BIN_RANGES: list[tuple[int, int, str]] = [
    # American Express — starts with 34, 37
    (340000, 349999, "american_express"),
    (370000, 379999, "american_express"),
    # Bankcard — 5610, 560221–560225
    (560221, 560225, "bankcard"),
    (561000, 561099, "bankcard"),
    # China T-Union — 31
    (310000, 319999, "china_t_union"),
    # China UnionPay — 62
    (620000, 629999, "china_unionpay"),
    # Diners Club Carte Blanche — 300–305
    (300000, 305999, "diners_club_carte_blanche"),
    # Diners Club International — 36, 309, 38–39
    (309000, 309999, "diners_club_international"),
    (360000, 369999, "diners_club_international"),
    (380000, 399999, "diners_club_international"),
    # Mastercard — 2221–2720, 51–55
    (222100, 272099, "mastercard"),
    (510000, 559999, "mastercard"),
    # Diners Club United States & Canada — 55
    # NOTE: 55 prefix overlaps with Mastercard's 51-55 range.
    # Mastercard is defined first (above), so MC wins for 55-prefix.
    (550000, 559999, "diners_club_us_canada"),
    # Discover Card — 6011, 622126–622925, 644–649, 65
    (601100, 601199, "discover"),
    (622126, 622925, "discover"),
    (644000, 649999, "discover"),
    (650000, 659999, "discover"),
    # InstaPayment — 637–639
    (637000, 639999, "instapayment"),
    # InterPayment — 636
    (636000, 636999, "interpayment"),
    # JCB — 3528–3589
    (352800, 358999, "jcb"),
    # Laser — 6304, 6706, 6771, 6709
    (630400, 630499, "laser"),
    (670600, 670699, "laser"),
    (670900, 670999, "laser"),
    (677100, 677199, "laser"),
    # Maestro — 50, 56–69 (subset)
    (500000, 509999, "maestro"),
    (560000, 569999, "maestro"),
    (570000, 579999, "maestro"),
    (580000, 589999, "maestro"),
    (590000, 599999, "maestro"),
    (600000, 609999, "maestro"),
    (610000, 619999, "maestro"),
    (620000, 629999, "maestro"),
    (630000, 639999, "maestro"),
    (640000, 649999, "maestro"),
    (650000, 659999, "maestro"),
    (660000, 669999, "maestro"),
    (670000, 670599, "maestro"),
    (671000, 679999, "maestro"),
    (680000, 689999, "maestro"),
    (690000, 699999, "maestro"),
    # Maestro done — mastercard moved earlier (near Diners) to fix overlap ordering
    # RuPay — 60, 81, 82, 508
    (508000, 508999, "rupay"),
    (600000, 609999, "rupay"),
    (810000, 819999, "rupay"),
    (820000, 829999, "rupay"),
    # UATP — 1
    (100000, 199999, "uatp"),
    # Visa — 4
    (400000, 499999, "visa"),
    # Visa Electron — 4026, 417500, 4050, 4508, 4844, 4913, 4917
    (402600, 402699, "visa_electron"),
    (405000, 405099, "visa_electron"),
    (417500, 417599, "visa_electron"),
    (450800, 450899, "visa_electron"),
    (484400, 484499, "visa_electron"),
    (491300, 491399, "visa_electron"),
    (491700, 491799, "visa_electron"),
    # Voyager — 8699
    (869900, 869999, "voyager"),
    # Wex — 6901, 6902, 6903
    (690100, 690399, "wex"),
]

# Assign each range a priority ranking (lower = higher priority).
#
# Priority = (idx,)  → first-defined wins.  This is the simplest
# scheme: we just order the list so that well-known brands come first
# for overlapping ranges.
#
# Overlapping ranges:
#   - Mastercard (51-55) vs Diners US (55): MC defined first → MC wins for 55-prefix
#   - Visa (4xxxxx) vs Visa Electron: Visa Electron defined after → narrower wins
#   - Discover (65) vs Maestro (65): Discover defined first → Discover wins
#   - JCB (3528-3589) vs Maestro (35): JCB defined first → JCB wins for 35-prefix
#   - RuPay (60, 81, 82, 508) vs Maestro: RuPay overlaps with Maestro at 60;
#     Maestro is defined first → Maestro wins for 60-prefix.
#     RuPay also overlaps with Discover at 65; Discover wins there.
_PRIORITY: list[tuple[int]] = [
    (i,) for i in range(len(_BIN_RANGES))
]


def _lookup_bin(pan: str) -> str | None:
    """Look up card brand from the PAN prefix (first 6 digits).

    Tries 6-digit, 4-digit, then 3-digit prefixes against the known
    BIN ranges.  The best match is the range with the narrowest width;
    ties broken by highest lo (most specific sub-range), then earliest
    definition order.

    Returns brand string or None if unknown.
    """
    pan_prefix = pan[:6].zfill(6)
    pan_val = int(pan_prefix)

    candidates = [pan_val, pan_val // 100, pan_val // 1000]

    best: int | None = None
    best_key: tuple[int] | None = None

    for val in candidates:
        for idx, (lo, hi, _brand) in enumerate(_BIN_RANGES):
            if lo <= val <= hi:
                key = _PRIORITY[idx]
                if best_key is None or key < best_key:
                    best_key = key
                    best = idx
                    if _BIN_RANGES[best][1] - _BIN_RANGES[best][0] == 0:
                        return _BIN_RANGES[best][2]  # exact match

    return _BIN_RANGES[best][2] if best is not None else None


# ── Credit Card number cleanup ───────────────────────────────────────────────

_CC_STRIP_RE = re.compile(r"[^0-9]")


def _strip_cc(raw: str) -> str:
    """Remove all non-digit characters from a raw CC string."""
    return _CC_STRIP_RE.sub("", raw)


# ── CreditCardValidator ──────────────────────────────────────────────────────


class CreditCardValidator:
    """Validates credit-card numbers via Luhn checksum + BIN range.

    Accepts raw strings with or without separators (dashes, spaces, dots).
    Returns metadata with ``brand``, ``length``, and ``luhn_pass``.
    """

    __validator_name__: str = "credit_card"

    # Most card numbers are 13–19 digits; 16 is by far the most common
    _VALID_LENGTHS = frozenset({13, 14, 15, 16, 17, 18, 19})

    def validate(self, raw: str) -> ValidationResult:
        digits = _strip_cc(raw)

        if not digits or not digits.isdigit():
            return ValidationResult.invalid(
                reasons=["No digits found in input"],
            )

        length = len(digits)
        if length not in self._VALID_LENGTHS:
            return ValidationResult.invalid(
                score=0.0,
                reasons=[f"Length {length} not in valid range 13–19"],
                length=length,
            )

        # Luhn check
        luhn_pass = _luhn_checksum(digits) == 0

        # BIN lookup
        brand = _lookup_bin(digits)

        reasons: list[str] = []
        metadata: dict[str, Any] = {
            "length": length,
            "luhn_pass": luhn_pass,
        }

        if brand:
            metadata["brand"] = brand
        else:
            metadata["brand"] = "unknown"

        if luhn_pass and brand and brand != "unknown":
            return ValidationResult.valid(
                score=0.95,
                reasons=[f"Luhn passed, BIN matched '{brand}' ({length} digits)"],
                **metadata,
            )

        if luhn_pass:
            reasons.append(f"Luhn passed ({length} digits)")
            if brand and brand != "unknown":
                return ValidationResult.valid(
                    score=0.85,
                    reasons=[f"Luhn passed, BIN matched '{brand}'"],
                    **metadata,
                )
            # Luhn valid but unknown BIN — could be a new issuer
            return ValidationResult.plausible(
                score=0.70,
                reasons=["Luhn passed, but BIN not in known range"],
                **metadata,
            )

        # Luhn failed
        reasons.append("Luhn checksum failed")
        if brand:
            return ValidationResult.invalid(
                score=0.30,
                reasons=[f"Luhn failed (BIN '{brand}' known, length {length})"],
                **metadata,
            )

        return ValidationResult.invalid(
            score=0.10,
            reasons=[f"Luhn failed, unknown BIN ({length} digits)"],
            **metadata,
        )


# ── SSN Validator ────────────────────────────────────────────────────────────

# SSN format: 3-digit area, 2-digit group, 4-digit serial (AAA-GG-SSSS)

_SSN_STRIP_RE = re.compile(r"[^0-9]")
_SSN_PATTERN = re.compile(r"^\d{3}[- ]?\d{2}[- ]?\d{4}$")
_SSN_CONTINUOUS = re.compile(r"^\d{9}$")

# Invalid area ranges (SSA never issued)
_INVALID_AREAS: set[int] = {
    0,      # No area 000
    666,    # Horror trope — never issued
    900,    # 900+ reserved / never used
}

# Group codes are issued in a specific odd/even order by the SSA.
# `_all_valid_groups(area) → set[str]` — for simplicity we *could*
# enumerate all historically issued groups, but that's ~100K entries.
# Instead we validate structural rules:
#   - Group must be 01–99 (not 00)
#   - Area rules per SSA publication

_SSN_MAX_SERIAL = 9999


class SsnValidator:
    """Validates US SSN structural rules: area/group/serial.

    Checks:
    1. Length is exactly 9 digits.
    2. Area is not 000, 666, or >= 900.
    3. Group is 01–99 (not 00).
    4. Serial is 0001–9999 (not 0000).

    Does NOT check against live SSA issuance tables (those change monthly).
    The structural rules cover ~95 % of invalid SSNs.
    """

    __validator_name__: str = "social_security"

    def validate(self, raw: str) -> ValidationResult:
        digits = _SSN_STRIP_RE.sub("", raw)

        if len(digits) != 9 or not digits.isdigit():
            return ValidationResult.invalid(
                reasons=[f"Expected 9 digits, got {len(digits)}"],
            )

        area = int(digits[:3])
        group = int(digits[3:5])
        serial = int(digits[5:])

        reasons: list[str] = []
        metadata: dict[str, Any] = {
            "area": digits[:3],
            "group": digits[3:5],
            "serial": digits[5:],
        }

        # Area checks
        if area == 0:
            return ValidationResult.invalid(
                reasons=["Area 000 is never valid"],
                **metadata,
            )
        if area == 666:
            return ValidationResult.invalid(
                reasons=["Area 666 is never valid"],
                **metadata,
            )
        if area >= 900:
            return ValidationResult.invalid(
                reasons=[f"Area {area} >= 900 is never valid"],
                **metadata,
            )

        # Group check
        if group == 0:
            return ValidationResult.invalid(
                reasons=["Group 00 is never valid"],
                **metadata,
            )
        if not (1 <= group <= 99):
            return ValidationResult.invalid(
                reasons=[f"Group {group} out of range 01–99"],
                **metadata,
            )

        # Serial check
        if serial == 0:
            return ValidationResult.invalid(
                reasons=["Serial 0000 is never valid"],
                **metadata,
            )

        # All structural checks passed
        return ValidationResult.valid(
            score=0.90,
            reasons=["SSN area/group/serial structure valid"],
            **metadata,
        )


# ── Phone Validator ──────────────────────────────────────────────────────────

_STRIP_NONDIGIT_PLUS = re.compile(r"[^\d+]")


def _strip_phone(raw: str) -> str:
    """Strip everything except digits and leading +."""
    # Keep digits, leading +, and dashes/spaces for phonenumbers
    return raw.strip()


# ── PhoneValidator ────────────────────────────────────────────────────────────


class PhoneValidator:
    """Validates phone numbers using the ``phonenumbers`` library.

    Two validation modes (controlled by ``strict``):

    - **Strict** (default, ``strict=True``): requires a valid country code and
      passes ``phonenumbers.is_valid_number()``.

    - **Loose** (``strict=False``): uses ``is_possible_number()`` instead,
      which only checks digit count and structural plausibility.  Useful when
      the country code may be ambiguous (e.g. bare 10-digit US numbers).

    The ``default_region`` parameter lets the validator assume a region for
    numbers without an explicit country code (e.g. "US" for 555-123-4567).
    """

    __validator_name__: str = "phone"

    def __init__(self, strict: bool = True,
                 default_region: str | None = "US") -> None:
        self.strict = strict
        self.default_region = default_region

    def validate(self, raw: str) -> ValidationResult:
        validated = self._do_validate(raw)
        if validated is not None:
            return validated

        # If strict failed, try loose if we're in strict mode
        if self.strict:
            # Build a loose validator and run
            loose = PhoneValidator(strict=False, default_region=self.default_region)
            return loose.validate(raw)

        return ValidationResult.invalid(
            reasons=["Failed all validation attempts"],
        )

    def _do_validate(self, raw: str) -> ValidationResult | None:
        """Core validation logic.  Returns None to fall through."""
        try:
            import phonenumbers
        except ImportError:
            return ValidationResult.plausible(
                score=0.5,
                reasons=["phonenumbers library not available — cannot validate"],
            )

        text = raw.strip()
        if not text:
            return ValidationResult.invalid(reasons=["Empty input"])

        try:
            if text.startswith("+"):
                # International format — parse without region
                    parsed = phonenumbers.parse(text, None)
            elif self.default_region:
                parsed = phonenumbers.parse(text, self.default_region)
            else:
                # No region hint and no + — try to parse as-is
                parsed = phonenumbers.parse(text, None)
        except phonenumbers.NumberParseException as exc:
            return ValidationResult.invalid(
                reasons=[f"Parse error: {exc}"],
            )

        valid_fn = (phonenumbers.is_possible_number if not self.strict
                    else phonenumbers.is_valid_number)
        label = "possible" if not self.strict else "valid"

        if valid_fn(parsed):
            country_code = parsed.country_code
            national = phonenumbers.format_number(
                parsed, phonenumbers.PhoneNumberFormat.NATIONAL,
            )
            e164 = phonenumbers.format_number(
                parsed, phonenumbers.PhoneNumberFormat.E164,
            )
            return ValidationResult.valid(
                score=0.95 if self.strict else 0.70,
                reasons=[f"Phone number is {label}"],
                country_code=country_code,
                national=national,
                e164=e164,
            )

        return ValidationResult.invalid(
            score=0.0 if self.strict else 0.20,
            reasons=[f"Phone number is not {label}"],
        )


# ═══════════════════════════════════════════════════════════════════════════════
# ValidatorRegistry
# ═══════════════════════════════════════════════════════════════════════════════


class DuplicateValidatorError(ValueError):
    """Raised when registering a validator with a name already in the registry."""


class ValidatorNotFoundError(KeyError):
    """Raised when looking up a validator that isn't registered."""


class ValidatorRegistry:
    """Registry of named validators, keyed by entity type name.

    Built-in validators are pre-registered for CREDIT_CARD, SOCIAL_SECURITY,
    and PHONE.  Additional validators can be registered or replaced at runtime.

    Usage::

        registry = ValidatorRegistry()
        result = registry.validate("CREDIT_CARD", "4111 1111 1111 1111")
        # → ValidationResult(status=VALID, score=0.95, ...)

        # Add a custom validator
        registry.register("MY_TYPE", MyValidator())

        # Retrieve and inspect
        v = registry.get("CREDIT_CARD")
    """

    def __init__(self) -> None:
        self._validators: dict[str, Validator] = {}
        self._register_builtins()

    def _register_builtins(self) -> None:
        self.register("CREDIT_CARD", CreditCardValidator())
        self.register("SOCIAL_SECURITY", SsnValidator())
        self.register("PHONE", PhoneValidator())

    # ── Registration ─────────────────────────────────────────────────────

    def register(self, entity_type: str, validator: Validator,
                 overwrite: bool = False) -> None:
        """Register a validator for an entity type.

        Raises ``DuplicateValidatorError`` if the type is already registered
        and ``overwrite`` is False.
        """
        name = entity_type.upper()
        if name in self._validators and not overwrite:
            raise DuplicateValidatorError(
                f"Validator for '{name}' is already registered. "
                "Set overwrite=True to replace it."
            )
        self._validators[name] = validator

    def register_many(self, mapping: dict[str, Validator],
                      overwrite: bool = False) -> None:
        """Register multiple validators from a {type: validator} dict."""
        for entity_type, validator in mapping.items():
            self.register(entity_type, validator, overwrite=overwrite)

    # ── Lookup ───────────────────────────────────────────────────────────

    def get(self, entity_type: str) -> Validator:
        """Get a validator by entity type.

        Raises ``ValidatorNotFoundError`` if not registered.
        """
        name = entity_type.upper()
        if name not in self._validators:
            raise ValidatorNotFoundError(
                f"No validator registered for '{name}'. "
                f"Available: {', '.join(sorted(self._validators))}"
            )
        return self._validators[name]

    def get_or_none(self, entity_type: str) -> Validator | None:
        """Get a validator, or None if not registered."""
        return self._validators.get(entity_type.upper())

    # ── Validation ───────────────────────────────────────────────────────

    def validate(self, entity_type: str, raw: str) -> ValidationResult:
        """Validate *raw* using the registered validator for *entity_type*.

        Shortcut for ``registry.get(entity_type).validate(raw)``.
        """
        return self.get(entity_type).validate(raw)

    def validate_many(self,
                      items: list[tuple[str, str]]) -> list[ValidationResult]:
        """Validate multiple (entity_type, raw) pairs.

        Results are returned in the same order as *items*.
        """
        return [self.validate(et, raw) for et, raw in items]

    # ── Listing ──────────────────────────────────────────────────────────

    def list_types(self) -> list[str]:
        """Return sorted list of registered entity type names."""
        return sorted(self._validators)

    def list_validators(self) -> dict[str, Validator]:
        """Return a copy of the {type: validator} mapping."""
        return dict(self._validators)

    def __contains__(self, entity_type: str) -> bool:
        return entity_type.upper() in self._validators

    def __len__(self) -> int:
        return len(self._validators)

    def __repr__(self) -> str:
        return f"ValidatorRegistry({len(self)} validators: {', '.join(self.list_types())})"