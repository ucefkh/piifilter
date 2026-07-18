"""Configuration model for PIIFilter."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings


class ReplacementConfig(BaseModel):
    mode: str = "semantic"  # mask | semantic | generalize | policy
    seed: str = "deterministic"


class RiskConfig(BaseModel):
    threshold: str = "medium"  # low | medium | high | critical


class LoggingConfig(BaseModel):
    store_logs: bool = False
    level: str = "INFO"


class ProviderConfig(BaseModel):
    name: str = "lmstudio"
    endpoint: str = "http://localhost:1234/v1"
    api_key: str = ""
    default_model: str = "gpt-3.5-turbo"


class FilterConfig(BaseSettings):
    model_config = {"env_prefix": "PII_"}

    replacement: ReplacementConfig = ReplacementConfig()
    risk: RiskConfig = RiskConfig()
    logging: LoggingConfig = LoggingConfig()
    provider: ProviderConfig = ProviderConfig()

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
            data = yaml.safe_load(f)
        cfg = cls()

        if data:
            if "replacement_mode" in data:
                cfg.replacement.mode = data["replacement_mode"]
            if "risk_threshold" in data:
                cfg.risk.threshold = data["risk_threshold"]
            if "store_logs" in data:
                cfg.logging.store_logs = bool(data["store_logs"])
            if "replacement_seed" in data:
                cfg.replacement.seed = str(data["replacement_seed"])
            if "provider" in data:
                if isinstance(data["provider"], str):
                    cfg.provider.name = data["provider"]
                elif isinstance(data["provider"], dict):
                    cfg.provider.name = data["provider"].get("name", cfg.provider.name)
                    cfg.provider.endpoint = data["provider"].get("endpoint", cfg.provider.endpoint)
                    cfg.provider.api_key = data["provider"].get("api_key", cfg.provider.api_key)
                    cfg.provider.default_model = data["provider"].get("default_model", cfg.provider.default_model)

        return cfg

    def to_yaml(self, path: str | Path) -> None:
        data = {
            "replacement_mode": self.replacement.mode,
            "risk_threshold": self.risk.threshold,
            "store_logs": self.logging.store_logs,
            "replacement_seed": self.replacement.seed,
            "provider": {
                "name": self.provider.name,
                "endpoint": self.provider.endpoint,
                "api_key": "***" if self.provider.api_key else "",
                "default_model": self.provider.default_model,
            },
        }
        with open(path, "w") as f:
            yaml.dump(data, f, default_flow_style=False)