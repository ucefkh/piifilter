"""Tests for ValidatorRegistry — Luhn+BIN, SSN struct, phonenumbers, pluggable Protocol."""

from __future__ import annotations

import pytest

from piifilter.shared.validation import (
    CreditCardValidator,
    DuplicateValidatorError,
    PhoneValidator,
    SsnValidator,
    ValidationResult,
    ValidationStatus,
    ValidatorNotFoundError,
    ValidatorRegistry,
)


# ═══════════════════════════════════════════════════════════════════════════════
# ValidationResult
# ═══════════════════════════════════════════════════════════════════════════════


class TestValidationResult:
    def test_valid_factory(self) -> None:
        r = ValidationResult.valid(score=0.95, reasons=["All good"], brand="visa")
        assert r.status == ValidationStatus.VALID
        assert r.score == 0.95
        assert r.reasons == ["All good"]
        assert r.metadata == {"brand": "visa"}
        assert r  # __bool__

    def test_invalid_factory(self) -> None:
        r = ValidationResult.invalid(score=0.0, reasons=["Failed"])
        assert r.status == ValidationStatus.INVALID
        assert r.score == 0.0
        assert not r  # __bool__

    def test_plausible_factory(self) -> None:
        r = ValidationResult.plausible(score=0.5)
        assert r.status == ValidationStatus.PLAUSIBLE
        assert r.score == 0.5
        assert r  # __bool__


# ═══════════════════════════════════════════════════════════════════════════════
# CreditCardValidator
# ═══════════════════════════════════════════════════════════════════════════════


class TestCreditCardValidator:
    """Tests Luhn checksum + BIN range validation."""

    validator = CreditCardValidator()

    # ── Known good test numbers ──────────────────────────────────────────

    def test_visa(self) -> None:
        r = self.validator.validate("4111 1111 1111 1111")
        assert r.status == ValidationStatus.VALID
        assert r.metadata.get("brand") == "visa"
        assert r.metadata.get("luhn_pass") is True
        assert r.score > 0.9

    def test_mastercard(self) -> None:
        r = self.validator.validate("5555 5555 5555 4444")
        assert r.status == ValidationStatus.VALID
        assert r.metadata.get("brand") == "mastercard"
        assert r.score > 0.9

    def test_american_express(self) -> None:
        r = self.validator.validate("3782 8224 6310 005")
        assert r.status == ValidationStatus.VALID
        assert r.metadata.get("brand") == "american_express"
        assert r.score > 0.9

    def test_discover(self) -> None:
        r = self.validator.validate("6011 1111 1111 1117")
        assert r.status == ValidationStatus.VALID
        assert r.metadata.get("brand") == "discover"
        assert r.score > 0.9

    def test_jcb(self) -> None:
        r = self.validator.validate("3530 1113 3330 0000")
        assert r.status == ValidationStatus.VALID
        assert r.metadata.get("brand") == "jcb"

    def test_maestro(self) -> None:
        r = self.validator.validate("6759 6498 2643 8453")
        assert r.status == ValidationStatus.VALID

    def test_visa_electron(self) -> None:
        r = self.validator.validate("4917 3040 0963 6781")
        assert r.status == ValidationStatus.VALID
        assert r.metadata.get("brand") == "visa_electron"

    # ── Various input formats ────────────────────────────────────────────

    def test_with_dashes(self) -> None:
        r = self.validator.validate("4111-1111-1111-1111")
        assert r.status == ValidationStatus.VALID

    def test_with_dots(self) -> None:
        r = self.validator.validate("4111.1111.1111.1111")
        assert r.status == ValidationStatus.VALID

    def test_continuous_digits(self) -> None:
        r = self.validator.validate("4111111111111111")
        assert r.status == ValidationStatus.VALID

    # ── Invalid cases ───────────────────────────────────────────────────

    def test_luhn_fail(self) -> None:
        r = self.validator.validate("1234 5678 9012 3456")
        assert r.status == ValidationStatus.INVALID
        assert r.metadata.get("luhn_pass") is False

    def test_short_number(self) -> None:
        r = self.validator.validate("1234")
        assert r.status == ValidationStatus.INVALID

    def test_empty(self) -> None:
        r = self.validator.validate("")
        assert r.status == ValidationStatus.INVALID

    def test_non_digit_chars(self) -> None:
        r = self.validator.validate("abcd efgh ijkl mnop")
        assert r.status == ValidationStatus.INVALID

    # ── Plausible (Luhn valid, unknown BIN) ──────────────────────────────

    def test_luhn_valid_unknown_bin(self) -> None:
        # A 16-digit number that passes Luhn but has no known BIN
        r = self.validator.validate("9999 9999 9999 9999")
        assert r.status in (ValidationStatus.VALID, ValidationStatus.PLAUSIBLE)

    # ── BIN ranges ──────────────────────────────────────────────────────

    def test_uatp(self) -> None:
        r = self.validator.validate("1354 0000 0000 0003")
        assert r.status == ValidationStatus.VALID
        assert r.metadata.get("brand") == "uatp"

    def test_wex(self) -> None:
        r = self.validator.validate("6901 0000 0000 0009")
        assert r.status == ValidationStatus.VALID
        assert r.metadata.get("brand") == "wex"


# ═══════════════════════════════════════════════════════════════════════════════
# SsnValidator
# ═══════════════════════════════════════════════════════════════════════════════


class TestSsnValidator:
    """Tests SSN area/group/serial structural validation."""

    validator = SsnValidator()

    def test_valid_ssn(self) -> None:
        r = self.validator.validate("078-05-1120")
        assert r.status == ValidationStatus.VALID
        assert r.metadata == {"area": "078", "group": "05", "serial": "1120"}
        assert r.score == 0.9

    def test_valid_ssn_no_separator(self) -> None:
        r = self.validator.validate("123456789")
        assert r.status == ValidationStatus.VALID

    def test_valid_ssn_space_separator(self) -> None:
        r = self.validator.validate("123 45 6789")
        assert r.status == ValidationStatus.VALID

    def test_area_000(self) -> None:
        r = self.validator.validate("000-12-3456")
        assert r.status == ValidationStatus.INVALID

    def test_area_666(self) -> None:
        r = self.validator.validate("666-00-0000")
        assert r.status == ValidationStatus.INVALID

    def test_area_over_900(self) -> None:
        r = self.validator.validate("987-65-4321")
        assert r.status == ValidationStatus.INVALID

    def test_group_00(self) -> None:
        r = self.validator.validate("123-00-4567")
        assert r.status == ValidationStatus.INVALID

    def test_serial_0000(self) -> None:
        r = self.validator.validate("123-45-0000")
        assert r.status == ValidationStatus.INVALID

    def test_too_short(self) -> None:
        r = self.validator.validate("123-45")
        assert r.status == ValidationStatus.INVALID

    def test_too_long(self) -> None:
        r = self.validator.validate("123-45-67890")
        assert r.status == ValidationStatus.INVALID

    def test_empty(self) -> None:
        r = self.validator.validate("")
        assert r.status == ValidationStatus.INVALID


# ═══════════════════════════════════════════════════════════════════════════════
# PhoneValidator
# ═══════════════════════════════════════════════════════════════════════════════


class TestPhoneValidator:
    """Tests phonenumbers integration for phone validation."""

    validator = PhoneValidator(strict=True)

    def test_valid_international(self) -> None:
        r = self.validator.validate("+1-650-253-0000")
        assert r.status == ValidationStatus.VALID
        assert r.metadata.get("country_code") == 1
        assert r.score > 0.9

    def test_valid_us_format(self) -> None:
        r = self.validator.validate("(415) 555-2671")
        assert r.status == ValidationStatus.VALID
        assert r.score > 0.9

    def test_invalid_555_number(self) -> None:
        """555-01xx are not real numbers — phonenumbers rejects them."""
        r = self.validator.validate("+1-555-123-4567")
        assert r.status == ValidationStatus.INVALID

    def test_invalid_format(self) -> None:
        r = self.validator.validate("+0-000-000-0000")
        assert r.status == ValidationStatus.INVALID

    def test_empty(self) -> None:
        r = self.validator.validate("")
        assert r.status == ValidationStatus.INVALID

    def test_loose_validator(self) -> None:
        """Loose mode uses is_possible_number."""
        loose = PhoneValidator(strict=False)
        r = loose.validate("555-123-4567")
        assert r.status == ValidationStatus.VALID
        assert r.score < 0.9  # lower confidence

    def test_loose_invalid(self) -> None:
        loose = PhoneValidator(strict=False)
        r = loose.validate("not-a-phone")
        assert r.status == ValidationStatus.INVALID

    def test_e164_output(self) -> None:
        r = self.validator.validate("+1-650-253-0000")
        assert r.metadata.get("e164") == "+16502530000"

    def test_national_format(self) -> None:
        r = self.validator.validate("+1-650-253-0000")
        assert r.metadata.get("national") is not None


# ═══════════════════════════════════════════════════════════════════════════════
# ValidatorRegistry
# ═══════════════════════════════════════════════════════════════════════════════


class TestValidatorRegistry:
    """Tests the registry: registration, lookup, validation, pluggability."""

    def test_builtin_types(self) -> None:
        registry = ValidatorRegistry()
        assert "CREDIT_CARD" in registry
        assert "SOCIAL_SECURITY" in registry
        assert "PHONE" in registry
        assert len(registry) == 3

    def test_validate_through_registry(self) -> None:
        registry = ValidatorRegistry()
        r = registry.validate("CREDIT_CARD", "4111 1111 1111 1111")
        assert r.status == ValidationStatus.VALID

    def test_validate_many(self) -> None:
        registry = ValidatorRegistry()
        items = [
            ("CREDIT_CARD", "4111 1111 1111 1111"),
            ("SOCIAL_SECURITY", "078-05-1120"),
        ]
        results = registry.validate_many(items)
        assert all(r.status == ValidationStatus.VALID for r in results)

    def test_duplicate_registration(self) -> None:
        registry = ValidatorRegistry()
        with pytest.raises(DuplicateValidatorError):
            registry.register("CREDIT_CARD", CreditCardValidator())

    def test_overwrite(self) -> None:
        registry = ValidatorRegistry()
        registry.register("CREDIT_CARD", CreditCardValidator(), overwrite=True)
        assert "CREDIT_CARD" in registry

    def test_missing_type(self) -> None:
        registry = ValidatorRegistry()
        with pytest.raises(ValidatorNotFoundError):
            registry.validate("UNKNOWN", "test")

    def test_get_or_none(self) -> None:
        registry = ValidatorRegistry()
        assert registry.get_or_none("CREDIT_CARD") is not None
        assert registry.get_or_none("UNKNOWN") is None

    def test_list_types(self) -> None:
        registry = ValidatorRegistry()
        types = registry.list_types()
        assert "CREDIT_CARD" in types
        assert "SOCIAL_SECURITY" in types
        assert "PHONE" in types

    def test_list_validators(self) -> None:
        registry = ValidatorRegistry()
        vmap = registry.list_validators()
        assert "CREDIT_CARD" in vmap
        assert isinstance(vmap["CREDIT_CARD"], CreditCardValidator)

    def test_register_many(self) -> None:
        registry = ValidatorRegistry()
        # Remove builtins to test fresh registration
        registry = ValidatorRegistry.__new__(ValidatorRegistry)
        registry._validators = {}

        class MockValidator:
            __validator_name__ = "mock"
            def validate(self, raw: str) -> ValidationResult:
                return ValidationResult.valid()

        registry.register_many({"MOCK_A": MockValidator(), "MOCK_B": MockValidator()})
        assert "MOCK_A" in registry
        assert "MOCK_B" in registry


# ═══════════════════════════════════════════════════════════════════════════════
# Validator Protocol (pluggability)
# ═══════════════════════════════════════════════════════════════════════════════


class TestValidatorProtocol:
    """Any object with validate(raw) -> ValidationResult satisfies the Protocol."""

    def test_custom_validator(self) -> None:
        """Duck-typed validator, no base class."""

        class LengthValidator:
            __validator_name__ = "length_check"

            def validate(self, raw: str) -> ValidationResult:
                if len(raw) > 5:
                    return ValidationResult.valid(reasons=["Length OK"])
                return ValidationResult.invalid(reasons=["Too short"])

        registry = ValidatorRegistry()
        registry.register("TEST", LengthValidator(), overwrite=True)
        r = registry.validate("TEST", "hello world")
        assert r.status == ValidationStatus.VALID

        r2 = registry.validate("TEST", "hi")
        assert r2.status == ValidationStatus.INVALID

    def test_runtime_checkable(self) -> None:
        from piifilter.shared.validation import Validator

        class GoodValidator:
            __validator_name__ = "good"
            def validate(self, raw: str) -> ValidationResult:
                return ValidationResult.valid()

        assert isinstance(GoodValidator(), Validator)

    def test_registry_accepts_protocol(self) -> None:
        from piifilter.shared.validation import Validator

        class MyValidator:
            __validator_name__ = "my"
            def validate(self, raw: str) -> ValidationResult:
                return ValidationResult.valid()

        v: Validator = MyValidator()  # type check
        registry = ValidatorRegistry()
        registry.register("MY", v, overwrite=True)
        assert "MY" in registry