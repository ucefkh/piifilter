"""Shared data models for PIIFilter."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class EntityType(str, Enum):
    PERSON = "PERSON"
    EMAIL = "EMAIL"
    PHONE = "PHONE"
    ADDRESS = "ADDRESS"
    CITY = "CITY"
    COUNTRY = "COUNTRY"
    COMPANY = "COMPANY"
    BANK_ACCOUNT = "BANK_ACCOUNT"
    IBAN = "IBAN"
    CREDIT_CARD = "CREDIT_CARD"
    PASSPORT = "PASSPORT"
    SOCIAL_SECURITY = "SOCIAL_SECURITY"
    JWT = "JWT"
    API_KEY = "API_KEY"
    SSH_KEY = "SSH_KEY"
    DATABASE_URL = "DATABASE_URL"
    PRIVATE_URL = "PRIVATE_URL"
    PROJECT_NAME = "PROJECT_NAME"
    CUSTOMER_NAME = "CUSTOMER_NAME"
    EMPLOYEE_NAME = "EMPLOYEE_NAME"
    GPS = "GPS"
    DOMAIN = "DOMAIN"
    IP_ADDRESS = "IP_ADDRESS"
    FILE_PATH = "FILE_PATH"


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ReplacementMode(str, Enum):
    MASK = "mask"
    SEMANTIC = "semantic"
    GENERALIZE = "generalize"
    POLICY = "policy"


class DetectedEntity(BaseModel):
    text: str
    type: EntityType
    start: int
    end: int
    score: float = Field(ge=0.0, le=1.0)
    source_detector: str = "regex"  # regex | presidio | gliner


class Replacement(BaseModel):
    original: str
    replacement: str
    entity_type: EntityType
    mode: ReplacementMode


class RiskAssessment(BaseModel):
    score: float = Field(ge=0.0, le=100.0)
    level: RiskLevel
    detected_count: int
    critical_entities: list[EntityType] = Field(default_factory=list)
    recommendation: str = ""
    details: list[dict] = Field(default_factory=list)


class FilterRequest(BaseModel):
    prompt: str
    mode: Optional[ReplacementMode] = None
    entities: Optional[list[EntityType]] = None
    policy: Optional[dict] = None


class FilterResponse(BaseModel):
    original: str
    filtered: str
    risk: RiskAssessment
    entities: list[DetectedEntity] = Field(default_factory=list)
    replacements: list[Replacement] = Field(default_factory=list)
    latency_ms: float = 0.0
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class ScanRequest(BaseModel):
    prompt: str


class ScanResponse(BaseModel):
    entities: list[DetectedEntity]
    count: int
    risk: RiskAssessment
    latency_ms: float = 0.0


class RiskRequest(BaseModel):
    prompt: str


class RiskResponse(BaseModel):
    assessment: RiskAssessment
    latency_ms: float = 0.0


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "1.0.0"
    detection_engine: bool = False
    replacement_engine: bool = False
    risk_engine: bool = False
    gateway: bool = False
    config_hash: str = ""


class ConfigResponse(BaseModel):
    config: dict
    effective: dict