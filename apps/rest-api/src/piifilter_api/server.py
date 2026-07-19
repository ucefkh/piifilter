"""PIIFilter REST API — FastAPI transport for the core pipeline.

Endpoints:
    POST /v1/filter    — detect, assess risk, replace, and optionally forward
    POST /v1/scan      — detect only (no modification)
    POST /v1/explain   — detect + risk + explanation
    POST /v1/health    — health check with registry & config summary
    POST /v1/config    — print or reload configuration

No transport logic leaks into the core.  The API only calls
``FilterPipeline``, ``Session``, and ``FilterConfig``.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from piifilter import FilterPipeline, Session, FilterConfig
from piifilter.shared.models import ReplacementMode
from piifilter.shared.alias_store import AliasStore
from piifilter_api.unfilter import create_unfilter_router

logger = logging.getLogger(__name__)

# ── Request / Response models ────────────────────────────────────────


class SessionRequest(BaseModel):
    """Matches the fields of ``piifilter.session.Session`` relevant to REST."""

    prompt: str
    conversation_id: Optional[str] = None
    request_id: Optional[str] = None
    mode: Optional[str] = None  # ReplacementMode value
    forward: bool = False


class EntityResponse(BaseModel):
    entity_type: str
    value: str
    start: int
    end: int
    confidence: float
    detector: str
    context: Optional[str] = None


class RiskResponse(BaseModel):
    score: float
    level: str
    detected_count: int
    critical_entities: list[str]
    recommendation: str
    details: list[dict[str, Any]]


class ReplacementResponse(BaseModel):
    original: str
    replacement: str
    entity_type: str
    mode: str


class FilterResponse(BaseModel):
    request_id: str
    blocked: bool
    block_reason: Optional[str] = None
    entities: list[EntityResponse]
    risk: Optional[RiskResponse] = None
    filtered_prompt: Optional[str] = None
    replacements: list[ReplacementResponse]
    llm_response: Optional[str] = None
    latency_ms: float


class ScanResponse(BaseModel):
    request_id: str
    blocked: bool
    entities: list[EntityResponse]
    risk: Optional[RiskResponse] = None
    latency_ms: float


class ExplainResponse(BaseModel):
    request_id: str
    prompt_length: int
    blocked: bool
    entities: list[EntityResponse]
    risk: Optional[RiskResponse] = None
    audit_events: list[dict[str, Any]]


class HealthResponse(BaseModel):
    status: str
    version: str
    config: dict[str, Any]
    registry: dict[str, Any]
    plugins_loaded: int


class ConfigResponse(BaseModel):
    config_version: int
    schema_version: int
    provider: dict[str, Any]
    policy: dict[str, Any]
    detection: dict[str, Any]
    replacement: dict[str, Any]
    logging: dict[str, Any]


# ── App factory ──────────────────────────────────────────────────────


def create_app(config_path: Optional[str] = None) -> FastAPI:
    """Create and return a configured FastAPI application.

    The app holds a single ``FilterPipeline`` instance in its state
    along with a shared ``AliasStore`` for conversation-scoped aliasing.
    """
    config = FilterConfig()
    if config_path:
        p = Path(config_path)
        if p.exists():
            config = FilterConfig.from_yaml(p)

    alias_store = AliasStore(seed=config.replacement.seed)
    pipeline = FilterPipeline(config=config, alias_store=alias_store)
    app = FastAPI(
        title="PIIFilter API",
        version="2.0.0",
        description="Local-first AI privacy gateway — detect, classify, "
                    "and replace sensitive information before prompts reach LLMs.",
    )

    # Stash for endpoint use
    app.state.pipeline = pipeline
    app.state.config = config
    app.state.alias_store = alias_store

    # ── Converters ──────────────────────────────────────────────

    def _entity_to_dict(e) -> dict[str, Any]:
        return {
            "entity_type": e.type.value,
            "value": e.text,
            "start": e.start,
            "end": e.end,
            "confidence": e.score,
            "detector": e.detector,
            "context": e.context,
        }

    def _replacement_to_dict(r) -> dict[str, Any]:
        return {
            "original": r.original,
            "replacement": r.replacement,
            "entity_type": r.entity_type.value if hasattr(r.entity_type, "value") else str(r.entity_type),
            "mode": r.mode.value if hasattr(r.mode, "value") else str(r.mode),
        }

    # ── Endpoints ───────────────────────────────────────────────

    @app.post("/v1/filter", response_model=FilterResponse)
    async def filter_endpoint(req: SessionRequest) -> FilterResponse:
        """Run full pipeline: detect → risk → replace → (optional) forward."""
        session = Session(
            prompt=req.prompt,
            conversation_id=req.conversation_id,
            request_id=req.request_id or Session().request_id,
            mode=ReplacementMode(req.mode) if req.mode else None,
        )
        if req.forward:
            session.provider_config = app.state.config.provider

        session = await pipeline.run(session)

        if session.blocked and not session.block_reason:
            session.block_reason = "Request blocked by pipeline"

        risk_resp = None
        if session.risk:
            r = session.risk
            risk_resp = RiskResponse(
                score=r.score,
                level=r.level.value if hasattr(r.level, "value") else str(r.level),
                detected_count=r.detected_count,
                critical_entities=r.critical_entities,
                recommendation=r.recommendation,
                details=r.details,
            )

        return FilterResponse(
            request_id=session.request_id,
            blocked=session.blocked,
            block_reason=session.block_reason,
            entities=[EntityResponse(**_entity_to_dict(e)) for e in session.entities],
            risk=risk_resp,
            filtered_prompt=session.filtered_prompt,
            replacements=[ReplacementResponse(**_replacement_to_dict(r)) for r in session.replacements],
            llm_response=session.llm_response,
            latency_ms=session.latency_ms,
        )

    @app.post("/v1/scan", response_model=ScanResponse)
    async def scan_endpoint(req: SessionRequest) -> ScanResponse:
        """Detect entities and assess risk without modifying the prompt."""
        session = Session(
            prompt=req.prompt,
            conversation_id=req.conversation_id,
            request_id=req.request_id or Session().request_id,
        )
        session = await pipeline.run(session)

        risk_resp = None
        if session.risk:
            r = session.risk
            risk_resp = RiskResponse(
                score=r.score,
                level=r.level.value if hasattr(r.level, "value") else str(r.level),
                detected_count=r.detected_count,
                critical_entities=r.critical_entities,
                recommendation=r.recommendation,
                details=r.details,
            )

        return ScanResponse(
            request_id=session.request_id,
            blocked=session.blocked,
            entities=[EntityResponse(**_entity_to_dict(e)) for e in session.entities],
            risk=risk_resp,
            latency_ms=session.latency_ms,
        )

    @app.post("/v1/explain", response_model=ExplainResponse)
    async def explain_endpoint(req: SessionRequest) -> ExplainResponse:
        """Detect entities and return detailed explanations."""
        session = Session(
            prompt=req.prompt,
            conversation_id=req.conversation_id,
            request_id=req.request_id or Session().request_id,
        )
        session = await pipeline.run(session)

        risk_resp = None
        if session.risk:
            r = session.risk
            risk_resp = RiskResponse(
                score=r.score,
                level=r.level.value if hasattr(r.level, "value") else str(r.level),
                detected_count=r.detected_count,
                critical_entities=r.critical_entities,
                recommendation=r.recommendation,
                details=r.details,
            )

        return ExplainResponse(
            request_id=session.request_id,
            prompt_length=len(req.prompt),
            blocked=session.blocked,
            entities=[EntityResponse(**_entity_to_dict(e)) for e in session.entities],
            risk=risk_resp,
            audit_events=session.audit_events,
        )

    @app.post("/v1/health", response_model=HealthResponse)
    async def health_endpoint() -> HealthResponse:
        """Health check showing config version and registry summary."""
        cfg = app.state.config
        reg = pipeline.registry.list_registered()

        return HealthResponse(
            status="ok",
            version="2.0.0",
            config={
                "version": cfg.config_version,
                "schema": cfg.schema_version,
                "provider": cfg.provider.name,
                "strategy": cfg.replacement.default_strategy,
                "detectors": cfg.detection.enabled_detectors,
                "policy_rules": len(cfg.policy.rules),
            },
            registry=reg,
            plugins_loaded=sum(
                len(v) if isinstance(v, list) else (1 if v else 0)
                for v in reg.values()
            ),
        )

    @app.post("/v1/config", response_model=ConfigResponse)
    async def config_endpoint(reload: bool = False) -> ConfigResponse:
        """Return current configuration.  Pass ``reload=true`` to re-read from disk."""
        if reload and config_path and Path(config_path).exists():
            new_config = FilterConfig.from_yaml(config_path)
            app.state.config = new_config
            app.state.pipeline = FilterPipeline(config=new_config)
            logger.info("Configuration reloaded from %s", config_path)

        cfg = app.state.config
        return ConfigResponse(
            config_version=cfg.config_version,
            schema_version=cfg.schema_version,
            provider=cfg.provider.model_dump(),
            policy={"rules": [r.model_dump(by_alias=True) for r in cfg.policy.rules]},
            detection=cfg.detection.model_dump(),
            replacement=cfg.replacement.model_dump(),
            logging=cfg.logging.model_dump(),
        )

    # ── Unfilter / alias endpoints ────────────────────────────────
    unfilter_router = create_unfilter_router(alias_store)
    app.include_router(unfilter_router)

    return app