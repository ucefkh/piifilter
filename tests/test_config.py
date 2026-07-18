"""Tests for PIIFilter core components."""

import pytest
from piifilter.config import FilterConfig
from piifilter.shared.models import FilterRequest, ReplacementMode, EntityType


class TestConfig:
    def test_default_config(self):
        cfg = FilterConfig()
        assert cfg.replacement.mode == "semantic"
        assert cfg.risk.threshold == "medium"
        assert cfg.logging.store_logs is False

    def test_config_from_yaml(self, tmp_path):
        yaml_path = tmp_path / "config.yaml"
        yaml_path.write_text("replacement_mode: mask\nrisk_threshold: high\n")
        cfg = FilterConfig.from_yaml(str(yaml_path))
        assert cfg.replacement.mode == "mask"
        assert cfg.risk.threshold == "high"

    def test_config_env_override(self, monkeypatch):
        monkeypatch.setenv("PII_REPLACEMENT_MODE", "mask")
        monkeypatch.setenv("PII_RISK_THRESHOLD", "critical")
        cfg = FilterConfig()
        assert cfg.replacement.mode == "mask"
        assert cfg.risk.threshold == "critical"


class TestFilterRequest:
    def test_basic_request(self):
        req = FilterRequest(prompt="Hello, my name is Susan")
        assert req.prompt == "Hello, my name is Susan"
        assert req.mode is None

    def test_request_with_mode(self):
        req = FilterRequest(prompt="Test", mode=ReplacementMode.MASK)
        assert req.mode == ReplacementMode.MASK


class TestEntityTypes:
    def test_all_types_defined(self):
        """All 23 entity types from the spec must be present."""
        expected = [
            "PERSON", "EMAIL", "PHONE", "ADDRESS", "CITY", "COUNTRY",
            "COMPANY", "BANK_ACCOUNT", "IBAN", "CREDIT_CARD", "PASSPORT",
            "SOCIAL_SECURITY", "JWT", "API_KEY", "SSH_KEY", "DATABASE_URL",
            "PRIVATE_URL", "PROJECT_NAME", "CUSTOMER_NAME", "EMPLOYEE_NAME",
            "GPS", "DOMAIN", "IP_ADDRESS", "FILE_PATH",
        ]
        for entity in expected:
            assert hasattr(EntityType, entity), f"Missing EntityType.{entity}"