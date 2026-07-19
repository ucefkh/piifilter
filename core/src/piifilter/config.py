"""PIIFilter v2 — Core configuration with versioning and declarative policy support."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings


class ProviderConfig(BaseModel):
    name: str = "lmstudio"
    endpoint: str = "http://localhost:1234/v1"
    api_key: str = ""
    default_model: str = "gpt-3.5-turbo"


class PolicyRule(BaseModel):
    if_condition: dict[str, Any] = Field(default_factory=dict, alias="if")
    action: str = "REPLACE"  # BLOCK | REPLACE | REVIEW | PASSTHROUGH

    model_config = {"populate_by_name": True}


class PolicyConfig(BaseModel):
    rules: list[PolicyRule] = Field(default_factory=lambda: [
        PolicyRule(if_condition={"type": "API_KEY"}, action="BLOCK"),
        PolicyRule(if_condition={"risk": 80, "operator": ">"}, action="BLOCK"),
    ])


class DetectionConfig(BaseModel):
    enabled_detectors: list[str] = Field(default_factory=lambda: ["regex", "presidio"])
    confidence_threshold: float = 0.5
    min_votes: int = 1  # how many detectors must agree
    pipeline_mode: bool = True  # when True, UNION raw-regex + pipeline results
                               # (max merge: never let pipeline remove a correct regex match)


class ReplacementConfig(BaseModel):
    default_strategy: str = "semantic"  # mask | semantic | generalize
    seed: str = "deterministic"


class LoggingConfig(BaseModel):
    level: str = "INFO"
    audit_enabled: bool = True


class FilterConfig(BaseSettings):
    model_config = {"env_prefix": "PII_"}

    config_version: int = 2
    schema_version: int = 1

    provider: ProviderConfig = ProviderConfig()
    policy: PolicyConfig = PolicyConfig()
    detection: DetectionConfig = DetectionConfig()
    replacement: ReplacementConfig = ReplacementConfig()
    logging: LoggingConfig = LoggingConfig()

    detection_entities: list[str] = Field(
        default_factory=lambda: [
            "PERSON", "EMAIL", "PHONE", "ADDRESS", "CITY", "COUNTRY",
            "COMPANY", "BANK_ACCOUNT", "IBAN", "CREDIT_CARD", "PASSPORT",
            "SOCIAL_SECURITY", "JWT", "API_KEY", "SSH_KEY", "DATABASE_URL",
            "PRIVATE_URL", "PROJECT_NAME", "CUSTOMER_NAME", "EMPLOYEE_NAME",
            "GPS", "DOMAIN", "IP_ADDRESS", "FILE_PATH",
        ]
    )

    @classmethod
    def from_yaml(cls, path: str | Path) -> FilterConfig:
        path = Path(path)
        if not path.exists():
            return cls()
        with open(path) as f:
            data = yaml.safe_load(f) or {}

        cfg = cls()

        # Version migration — when not specified, assume current version (2)
        ver = data.pop("config_version", 2)
        if ver < 2:
            # v1 → v2 migration: flat structure → nested policy/detection
            data = _migrate_v1_to_v2(data)

        if "provider" in data and data["provider"] is not None:
            cfg.provider = ProviderConfig(**{k: (v if v is not None else cfg.provider.model_dump()[k]) for k, v in data["provider"].items()})
        if "policy" in data and data["policy"] is not None:
            rules = data["policy"].get("rules", [])
            cfg.policy = PolicyConfig(rules=[PolicyRule(**r) for r in rules])
        if "detection" in data and data["detection"] is not None:
            cfg.detection = DetectionConfig(**{k: (v if v is not None else cfg.detection.model_dump()[k]) for k, v in data["detection"].items()})
        if "replacement" in data and data["replacement"] is not None:
            for k, v in data["replacement"].items():
                if v is not None and hasattr(cfg.replacement, k):
                    setattr(cfg.replacement, k, v)
        if "logging" in data and data["logging"] is not None:
            cfg.logging = LoggingConfig(**{k: (v if v is not None else cfg.logging.model_dump()[k]) for k, v in data["logging"].items()})

        return cfg

    def to_yaml(self, path: str | Path) -> None:
        data = {
            "config_version": self.config_version,
            "schema_version": self.schema_version,
            "provider": self.provider.model_dump(),
            "policy": {"rules": [r.model_dump(by_alias=True) for r in self.policy.rules]},
            "detection": self.detection.model_dump(),
            "replacement": self.replacement.model_dump(),
            "logging": self.logging.model_dump(),
        }
        with open(path, "w") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)


def _migrate_v1_to_v2(data: dict) -> dict:
    """Migrate v1 config format to v2."""
    result = {"provider": {}, "policy": {"rules": []}, "detection": {}, "replacement": {}, "logging": {}}

    # Provider
    if "provider" in data:
        p = data["provider"]
        if isinstance(p, str):
            result["provider"]["name"] = p
        elif isinstance(p, dict):
            result["provider"] = p

    # Replacement mode → replacement.default_strategy
    if "replacement_mode" in data:
        result["replacement"]["default_strategy"] = data["replacement_mode"]
    if "replacement_seed" in data:
        result["replacement"]["seed"] = str(data["replacement_seed"])

    # Risk threshold → policy rules (approximate)
    if "risk_threshold" in data:
        threshold_map = {"low": 25, "medium": 50, "high": 75, "critical": 90}
        t = threshold_map.get(data["risk_threshold"], 50)
        result["policy"]["rules"].append({"if": {"risk": t, "operator": ">"}, "action": "REVIEW"})

    # Store logs
    if "store_logs" in data:
        result["logging"]["audit_enabled"] = bool(data["store_logs"])

    return result