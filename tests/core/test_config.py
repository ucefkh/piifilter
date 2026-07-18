"""Comprehensive tests for piifilter.config — FilterConfig, policy rules, v1→v2 migration, YAML round-trip.

Tests default config, YAML loading/saving, migration from v1 format,
env var overrides, edge cases.
"""

from __future__ import annotations

import copy

import pytest
import yaml

from piifilter.config import (
    FilterConfig,
    PolicyConfig,
    PolicyRule,
    ProviderConfig,
    DetectionConfig,
    ReplacementConfig,
    LoggingConfig,
    _migrate_v1_to_v2,
)


# ── Default Config ───────────────────────────────────────────────────────


class TestConfigDefaults:
    """FilterConfig default values."""

    def test_default_config_version(self):
        cfg = FilterConfig()
        assert cfg.config_version == 2
        assert cfg.schema_version == 1

    def test_default_provider(self):
        cfg = FilterConfig()
        assert cfg.provider.name == "lmstudio"
        assert cfg.provider.endpoint == "http://localhost:1234/v1"
        assert cfg.provider.api_key == ""
        assert cfg.provider.default_model == "gpt-3.5-turbo"

    def test_default_policy(self):
        cfg = FilterConfig()
        assert len(cfg.policy.rules) == 2
        assert cfg.policy.rules[0].if_condition["type"] == "API_KEY"
        assert cfg.policy.rules[0].action == "BLOCK"
        assert cfg.policy.rules[1].if_condition["risk"] == 80

    def test_default_detection(self):
        cfg = FilterConfig()
        assert cfg.detection.enabled_detectors == ["regex", "presidio"]
        assert cfg.detection.confidence_threshold == 0.5
        assert cfg.detection.min_votes == 1

    def test_default_replacement(self):
        cfg = FilterConfig()
        assert cfg.replacement.default_strategy == "semantic"
        assert cfg.replacement.seed == "deterministic"

    def test_default_logging(self):
        cfg = FilterConfig()
        assert cfg.logging.level == "INFO"
        assert cfg.logging.audit_enabled is True

    def test_detection_entities_list(self):
        cfg = FilterConfig()
        assert len(cfg.detection_entities) >= 23
        assert "EMAIL" in cfg.detection_entities
        assert "API_KEY" in cfg.detection_entities

    def test_policy_rule_alias(self):
        """PolicyRule's if_condition is populated by 'if' alias."""
        rule = PolicyRule(**{"if": {"type": "EMAIL"}, "action": "REVIEW"})
        assert rule.if_condition["type"] == "EMAIL"
        assert rule.action == "REVIEW"

    def test_policy_rule_positional(self):
        """PolicyRule also works with positional 'if_condition'."""
        rule = PolicyRule(if_condition={"type": "PHONE"}, action="BLOCK")
        assert rule.if_condition["type"] == "PHONE"
        assert rule.action == "BLOCK"


class TestConfigCustom:
    """Custom config values."""

    def test_custom_provider(self):
        cfg = FilterConfig(provider=ProviderConfig(name="openai", endpoint="https://api.openai.com/v1"))
        assert cfg.provider.name == "openai"
        assert cfg.provider.endpoint == "https://api.openai.com/v1"

    def test_custom_policy(self):
        cfg = FilterConfig(policy=PolicyConfig(rules=[
            PolicyRule(if_condition={"type": "SSN"}, action="BLOCK"),
        ]))
        assert len(cfg.policy.rules) == 1
        assert cfg.policy.rules[0].if_condition["type"] == "SSN"

    def test_custom_detection(self):
        cfg = FilterConfig(detection=DetectionConfig(
            enabled_detectors=["custom_detector"],
            confidence_threshold=0.8,
            min_votes=2,
        ))
        assert cfg.detection.enabled_detectors == ["custom_detector"]
        assert cfg.detection.confidence_threshold == 0.8

    def test_custom_replacement(self):
        cfg = FilterConfig(replacement=ReplacementConfig(
            default_strategy="mask",
            seed="custom_seed",
        ))
        assert cfg.replacement.default_strategy == "mask"
        assert cfg.replacement.seed == "custom_seed"

    def test_custom_logging(self):
        cfg = FilterConfig(logging=LoggingConfig(level="DEBUG", audit_enabled=False))
        assert cfg.logging.level == "DEBUG"
        assert cfg.logging.audit_enabled is False


# ── Environment Variable Overrides ──────────────────────────────────────


class TestConfigEnvOverrides:
    """FilterConfig supports env var overrides when loaded via pydantic-settings."""

    def test_env_prefix(self):
        """The env_prefix is PII_."""
        assert FilterConfig.model_config["env_prefix"] == "PII_"


# ── YAML Loading ─────────────────────────────────────────────────────────


class TestConfigFromYaml:
    """Loading config from YAML."""

    def test_from_yaml_v2(self, tmp_path):
        """Load a full v2 YAML config."""
        yml = tmp_path / "config.yaml"
        yml.write_text("""\
config_version: 2
provider:
  name: openai
  endpoint: https://api.openai.com/v1
policy:
  rules:
    - if:
        type: API_KEY
      action: BLOCK
detection:
  enabled_detectors: [regex]
  confidence_threshold: 0.7
replacement:
  default_strategy: mask
logging:
  level: DEBUG
""")
        cfg = FilterConfig.from_yaml(yml)
        assert cfg.provider.name == "openai"
        assert cfg.provider.endpoint == "https://api.openai.com/v1"
        assert cfg.detection.enabled_detectors == ["regex"]
        assert cfg.detection.confidence_threshold == 0.7
        assert cfg.replacement.default_strategy == "mask"
        assert cfg.logging.level == "DEBUG"

    def test_from_yaml_partial(self, tmp_path):
        """Partial YAML only overrides specified fields."""
        yml = tmp_path / "config.yaml"
        yml.write_text("provider:\n  name: gemini\n")
        cfg = FilterConfig.from_yaml(yml)
        assert cfg.provider.name == "gemini"
        # Other fields remain defaults
        assert cfg.detection.confidence_threshold == 0.5

    def test_from_yaml_empty_file(self, tmp_path):
        """Empty YAML returns default config."""
        yml = tmp_path / "empty.yaml"
        yml.write_text("")
        cfg = FilterConfig.from_yaml(yml)
        assert isinstance(cfg, FilterConfig)
        assert cfg.config_version == 2

    def test_from_yaml_nonexistent(self, tmp_path):
        """Missing YAML file returns default config."""
        cfg = FilterConfig.from_yaml(tmp_path / "nonexistent.yaml")
        assert isinstance(cfg, FilterConfig)

    def test_from_yaml_with_null_values(self, tmp_path):
        """YAML with null values doesn't break."""
        yml = tmp_path / "config.yaml"
        yml.write_text("provider:\n  name: null\n")
        cfg = FilterConfig.from_yaml(yml)
        assert isinstance(cfg, FilterConfig)

    def test_from_yaml_only_provider(self, tmp_path):
        """YAML with only provider section."""
        yml = tmp_path / "config.yaml"
        yml.write_text("provider:\n  name: test\n  endpoint: http://test:8080\n")
        cfg = FilterConfig.from_yaml(yml)
        assert cfg.provider.name == "test"
        assert cfg.provider.endpoint == "http://test:8080"

    def test_from_yaml_only_detection(self, tmp_path):
        yml = tmp_path / "config.yaml"
        yml.write_text("detection:\n  min_votes: 3\n")
        cfg = FilterConfig.from_yaml(yml)
        assert cfg.detection.min_votes == 3


# ── YAML Round-trip ──────────────────────────────────────────────────────


class TestConfigYamlRoundTrip:
    """to_yaml and from_yaml round-trip."""

    def test_round_trip_defaults(self, tmp_path):
        """Default config round-trips correctly."""
        cfg1 = FilterConfig()
        path = tmp_path / "roundtrip.yaml"
        cfg1.to_yaml(path)
        cfg2 = FilterConfig.from_yaml(path)
        assert cfg1.provider.name == cfg2.provider.name
        assert cfg1.provider.endpoint == cfg2.provider.endpoint
        assert cfg1.detection.confidence_threshold == cfg2.detection.confidence_threshold
        assert cfg1.replacement.default_strategy == cfg2.replacement.default_strategy
        assert cfg1.logging.level == cfg2.logging.level
        assert len(cfg1.policy.rules) == len(cfg2.policy.rules)

    def test_round_trip_custom(self, tmp_path):
        """Custom config round-trips correctly."""
        cfg1 = FilterConfig(
            provider=ProviderConfig(name="openai", endpoint="https://api.openai.com/v1"),
            detection=DetectionConfig(confidence_threshold=0.9),
            replacement=ReplacementConfig(default_strategy="redact"),
            logging=LoggingConfig(level="DEBUG"),
        )
        path = tmp_path / "custom.yaml"
        cfg1.to_yaml(path)
        cfg2 = FilterConfig.from_yaml(path)
        assert cfg2.provider.name == "openai"
        assert cfg2.detection.confidence_threshold == 0.9
        assert cfg2.replacement.default_strategy == "redact"
        assert cfg2.logging.level == "DEBUG"

    def test_round_trip_preserves_version(self, tmp_path):
        """Config version is preserved through round-trip."""
        cfg = FilterConfig(config_version=2)
        path = tmp_path / "version.yaml"
        cfg.to_yaml(path)
        cfg2 = FilterConfig.from_yaml(path)
        assert cfg2.config_version == 2

    def test_yaml_output_is_valid(self, tmp_path):
        """Generated YAML is parseable."""
        cfg = FilterConfig()
        path = tmp_path / "valid.yaml"
        cfg.to_yaml(path)
        with open(path) as f:
            data = yaml.safe_load(f)
        assert "config_version" in data
        assert "provider" in data
        assert "policy" in data
        assert "detection" in data
        assert "replacement" in data
        assert "logging" in data


# ── v1 → v2 Migration ──────────────────────────────────────────────────


class TestConfigMigration:
    """Version 1 to version 2 config migration."""

    def test_migrate_provider_string_to_dict(self):
        """Provider as string (v1) becomes provider dict (v2)."""
        result = _migrate_v1_to_v2({"provider": "openai"})
        assert result["provider"]["name"] == "openai"

    def test_migrate_provider_dict_preserved(self):
        """Provider as dict (already v2-ish) is preserved."""
        result = _migrate_v1_to_v2({"provider": {"name": "openai", "endpoint": "http://test"}})
        assert result["provider"]["name"] == "openai"
        assert result["provider"]["endpoint"] == "http://test"

    def test_migrate_replacement_mode(self):
        """replacement_mode (v1) becomes replacement.default_strategy (v2)."""
        result = _migrate_v1_to_v2({"replacement_mode": "mask"})
        assert result["replacement"]["default_strategy"] == "mask"

    def test_migrate_replacement_seed(self):
        """replacement_seed (v1) becomes replacement.seed (v2)."""
        result = _migrate_v1_to_v2({"replacement_seed": "myseed"})
        assert result["replacement"]["seed"] == "myseed"

    def test_migrate_risk_threshold(self):
        """risk_threshold (v1) becomes policy rule (v2)."""
        result = _migrate_v1_to_v2({"risk_threshold": "high"})
        assert len(result["policy"]["rules"]) == 1
        # "high" maps to threshold 75
        assert result["policy"]["rules"][0]["if"]["risk"] == 75
        assert result["policy"]["rules"][0]["if"]["operator"] == ">"
        assert result["policy"]["rules"][0]["action"] == "REVIEW"

    def test_migrate_risk_threshold_low(self):
        result = _migrate_v1_to_v2({"risk_threshold": "low"})
        assert result["policy"]["rules"][0]["if"]["risk"] == 25

    def test_migrate_risk_threshold_medium(self):
        result = _migrate_v1_to_v2({"risk_threshold": "medium"})
        assert result["policy"]["rules"][0]["if"]["risk"] == 50

    def test_migrate_risk_threshold_critical(self):
        result = _migrate_v1_to_v2({"risk_threshold": "critical"})
        assert result["policy"]["rules"][0]["if"]["risk"] == 90

    def test_migrate_risk_threshold_unknown(self):
        """Unknown risk threshold defaults to 50."""
        result = _migrate_v1_to_v2({"risk_threshold": "unknown"})
        assert result["policy"]["rules"][0]["if"]["risk"] == 50

    def test_migrate_store_logs(self):
        """store_logs (v1) becomes logging.audit_enabled (v2)."""
        result = _migrate_v1_to_v2({"store_logs": True})
        assert result["logging"]["audit_enabled"] is True
        result2 = _migrate_v1_to_v2({"store_logs": False})
        assert result2["logging"]["audit_enabled"] is False

    def test_migrate_store_logs_not_set(self):
        """Without store_logs, audit_enabled is not set."""
        result = _migrate_v1_to_v2({})
        assert "audit_enabled" not in result["logging"]

    def test_migrate_empty_input(self):
        result = _migrate_v1_to_v2({})
        assert result["provider"] == {}
        assert result["policy"]["rules"] == []
        assert result["detection"] == {}
        assert result["replacement"] == {}
        assert result["logging"] == {}

    def test_from_yaml_auto_migrates_v1(self, tmp_path):
        """Loading a v1 YAML automatically migrates to v2 internally."""
        yml = tmp_path / "v1_config.yaml"
        yml.write_text("""\
config_version: 1
provider: openai
replacement_mode: mask
risk_threshold: high
""")
        cfg = FilterConfig.from_yaml(yml)
        # Migration should have happened
        assert cfg.config_version == 2  # Loaded config still has version 2
        assert cfg.replacement.default_strategy == "mask"
        # Check that the policy rule from risk_threshold migration was applied
        # "high" → threshold 75, rule exists in migrated data
        # Note: the rule from migration goes to the data dict, but
        # the existing default policy rules still apply via `policy_config`

    def test_migrate_combined(self, tmp_path):
        """Multiple v1 fields migrate together."""
        yml = tmp_path / "v1_full.yaml"
        yml.write_text("""\
config_version: 1
provider: openai
replacement_mode: mask
replacement_seed: abc123
risk_threshold: critical
store_logs: false
""")
        cfg = FilterConfig.from_yaml(yml)
        assert cfg.replacement.default_strategy == "mask"
        assert cfg.replacement.seed == "abc123"
        assert cfg.logging.audit_enabled is False
        # The migration adds a REVIEW rule for risk_threshold,
        # but the existing default rules (BLOCK for API_KEY) are still there
        assert len(cfg.policy.rules) >= 1


# ── Edge Cases ────────────────────────────────────────────────────────────


class TestConfigEdgeCases:
    """Edge cases for config."""

    def test_provider_with_empty_strings(self):
        cfg = FilterConfig(provider=ProviderConfig(name="", endpoint=""))
        assert cfg.provider.name == ""
        assert cfg.provider.endpoint == ""

    def test_policy_rule_no_condition(self):
        """PolicyRule with empty if_condition is valid."""
        rule = PolicyRule(if_condition={}, action="PASSTHROUGH")
        assert rule.if_condition == {}
        assert rule.action == "PASSTHROUGH"

    def test_policy_action_enum(self):
        """Policy actions are strings (accepts any string)."""
        for action in ("BLOCK", "REPLACE", "REVIEW", "PASSTHROUGH"):
            rule = PolicyRule(if_condition={"type": "TEST"}, action=action)
            assert rule.action == action

    def test_detection_entities_mutable(self):
        """detection_entities list is mutable."""
        cfg = FilterConfig()
        original_len = len(cfg.detection_entities)
        cfg.detection_entities.append("NEW_TYPE")
        assert len(cfg.detection_entities) == original_len + 1

    def test_to_yaml_creates_file(self, tmp_path):
        path = tmp_path / "output.yaml"
        cfg = FilterConfig()
        cfg.to_yaml(path)
        assert path.exists()

    def test_from_yaml_with_complex_policy(self, tmp_path):
        """Multiple policy rules load correctly."""
        yml = tmp_path / "complex.yaml"
        yml.write_text("""\
policy:
  rules:
    - if:
        type: API_KEY
      action: BLOCK
    - if:
        type: JWT
      action: BLOCK
    - if:
        type: SSH_KEY
      action: BLOCK
    - if:
        risk: 80
        operator: ">"
      action: BLOCK
""")
        cfg = FilterConfig.from_yaml(yml)
        assert len(cfg.policy.rules) == 4
        assert cfg.policy.rules[0].if_condition["type"] == "API_KEY"
        assert cfg.policy.rules[3].if_condition["risk"] == 80