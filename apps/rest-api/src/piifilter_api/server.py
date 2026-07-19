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

import json
import logging
from pathlib import Path
from typing import Any, AsyncGenerator, Optional

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from piifilter import FilterPipeline, Session, FilterConfig
from piifilter.shared.models import ReplacementMode
from piifilter.shared.alias_store import AliasStore
from piifilter.shared.alias_store_persistent import SQLiteAliasBackend
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

    If the environment variable ``PIIFILTER_STORE_KEY`` is set, the
    alias store uses a persistent ``SQLiteAliasBackend`` (encrypted at
    rest).  Otherwise it falls back to the in-memory default.
    """
    config = FilterConfig()
    if config_path:
        p = Path(config_path)
        if p.exists():
            config = FilterConfig.from_yaml(p)

    # Use SQLite backend when encryption key is available (opt-in)
    import os
    if os.environ.get("PIIFILTER_STORE_KEY"):
        backend = SQLiteAliasBackend(seed=config.replacement.seed)
        alias_store = AliasStore(seed=config.replacement.seed, backend=backend)
    else:
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

    # ── Streaming endpoints ────────────────────────────────────────

    class StreamRequest(BaseModel):
        """Request body for streaming endpoints."""
        prompt: str
        conversation_id: Optional[str] = None
        request_id: Optional[str] = None
        mode: Optional[str] = None

    class UnfilterStreamRequest(BaseModel):
        """Request body for the unfilter streaming endpoint.

        The filtered prompt (aliases) is sent as a final field alongside
        conversation context; the actual stream of LLM tokens is sent via
        the ``stream`` field as a list of chunks for simulation, or the
        endpoint connects to a provider for live streaming.
        """
        conversation_id: str
        stream: list[str] = []

    async def _stream_filtered(
        pipeline: FilterPipeline,
        session: Session,
    ) -> AsyncGenerator[str, None]:
        """Run the detection → risk → policy → replace pipeline and yield
        the filtered prompt as an SSE event, then the full pipeline result
        as a final JSON event."""
        session = await pipeline.run(session)

        # Yield the filtered prompt
        yield json.dumps({
            "type": "filtered",
            "data": {
                "request_id": session.request_id,
                "filtered_prompt": session.filtered_prompt,
                "blocked": session.blocked,
                "block_reason": session.block_reason,
                "entity_count": len(session.entities),
            },
        })

        # If the pipeline was blocked, emit an error event
        if session.is_blocked:
            yield json.dumps({
                "type": "blocked",
                "data": {
                    "request_id": session.request_id,
                    "reason": session.block_reason,
                },
            })
            return

        yield json.dumps({
            "type": "done",
            "data": {
                "request_id": session.request_id,
                "latency_ms": session.latency_ms,
            },
        })

    async def _forward_stream(
        pipeline: FilterPipeline,
        session: Session,
    ) -> AsyncGenerator[str, None]:
        """Run the full pipeline, then forward to the LLM in streaming mode
        and yield each chunk as an SSE event."""
        session = await pipeline.run(session)

        if session.is_blocked:
            yield json.dumps({
                "type": "blocked",
                "data": {
                    "request_id": session.request_id,
                    "reason": session.block_reason,
                },
            })
            return

        yield json.dumps({
            "type": "filtered",
            "data": {
                "request_id": session.request_id,
                "entity_count": len(session.entities),
            },
        })

        # Stream from the provider
        provider_name = session.provider_config.name if session.provider_config else session.config.provider.name
        provider = pipeline.registry.get_provider_or_none(provider_name)

        if provider is None:
            yield json.dumps({
                "type": "error",
                "data": {"message": f"Provider '{provider_name}' not found"},
            })
            return

        try:
            chunk_count = 0
            async for chunk in provider.forward_stream(session):
                chunk_count += 1
                yield json.dumps({
                    "type": "chunk",
                    "data": {
                        "text": chunk,
                        "index": chunk_count,
                    },
                })
        except Exception as exc:
            yield json.dumps({
                "type": "error",
                "data": {"message": f"Streaming error: {exc}"},
            })
            return

        yield json.dumps({
            "type": "done",
            "data": {
                "request_id": session.request_id,
                "chunks": chunk_count,
            },
        })

    @app.post("/v1/filter/stream")
    async def filter_stream_endpoint(req: StreamRequest):
        """Stream the filtered prompt as SSE events.

        Returns an SSE stream with events:
          - ``filtered``: the filtered prompt and metadata
          - ``blocked``: (if blocked) block reason
          - ``done``: final metadata
        """
        session = Session(
            prompt=req.prompt,
            conversation_id=req.conversation_id,
            request_id=req.request_id or Session().request_id,
            mode=ReplacementMode(req.mode) if req.mode else None,
        )
        session.alias_store = pipeline.alias_store if hasattr(pipeline, 'alias_store') else app.state.alias_store

        async def event_generator():
            async for event_data in _stream_filtered(pipeline, session):
                yield {"event": "message", "data": event_data}

        return EventSourceResponse(event_generator())

    @app.post("/v1/forward/stream")
    async def forward_stream_endpoint(req: StreamRequest):
        """Stream the filtered prompt **and forward to LLM** as SSE events.

        Returns an SSE stream with events:
          - ``filtered``: the filtered prompt metadata
          - ``chunk``: each streaming token from the LLM
          - ``blocked``: (if blocked) block reason
          - ``error``: streaming error
          - ``done``: final metadata
        """
        session = Session(
            prompt=req.prompt,
            conversation_id=req.conversation_id,
            request_id=req.request_id or Session().request_id,
            mode=ReplacementMode(req.mode) if req.mode else None,
        )
        session.provider_config = app.state.config.provider
        session.alias_store = pipeline.alias_store if hasattr(pipeline, 'alias_store') else app.state.alias_store

        async def event_generator():
            async for event_data in _forward_stream(pipeline, session):
                yield {"event": "message", "data": event_data}

        return EventSourceResponse(event_generator())

    @app.post("/v1/unfilter/stream")
    async def unfilter_stream_endpoint(req: UnfilterStreamRequest):
        """Streaming unfilter: receive a list of stream chunks and emit
        SSE events with original values restored.

        Returns an SSE stream with events:
          - ``chunk``: each unfiltered chunk
          - ``done``: final metadata
        """
        session = Session(
            prompt="",
            conversation_id=req.conversation_id,
        )
        session.alias_store = pipeline.alias_store if hasattr(pipeline, 'alias_store') else app.state.alias_store

        async def stream_chunks():
            for chunk in req.stream:
                yield chunk

        async def event_generator():
            chunk_count = 0
            async for unfiltered_chunk in session.unfilter_stream(stream_chunks()):
                chunk_count += 1
                yield {
                    "event": "message",
                    "data": json.dumps({
                        "type": "chunk",
                        "data": {
                            "text": unfiltered_chunk,
                            "index": chunk_count,
                        },
                    }),
                }
            yield {
                "event": "message",
                "data": json.dumps({
                    "type": "done",
                    "data": {"chunks": chunk_count},
                }),
            }

        return EventSourceResponse(event_generator())

    return app