"""PIIFilter API server — FastAPI REST API."""

from __future__ import annotations

import json
import time
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from piifilter import __version__, FilterPipeline
from piifilter.config import FilterConfig
from piifilter.shared.models import (
    ConfigResponse,
    FilterRequest,
    FilterResponse,
    HealthResponse,
    ReplacementMode,
    RiskRequest,
    RiskResponse,
    ScanRequest,
    ScanResponse,
)
from piifilter.shared.utils import config_hash


def create_app(config: Optional[FilterConfig] = None) -> FastAPI:
    """Create and configure the FastAPI application."""
    cfg = config or FilterConfig()
    pipeline = FilterPipeline(cfg)

    app = FastAPI(
        title="PIIFilter API",
        version=__version__,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.post("/filter", response_model=FilterResponse)
    async def filter_prompt(request: FilterRequest):
        """Detect and replace PII in a prompt."""
        result = await pipeline.filter(request)
        return result

    @app.post("/scan", response_model=ScanResponse)
    async def scan_prompt(request: ScanRequest):
        """Scan a prompt for PII without modifying it."""
        result = await pipeline.scan(request)
        return result

    @app.post("/risk", response_model=RiskResponse)
    async def assess_risk(request: RiskRequest):
        """Assess the risk level of a prompt."""
        result = await pipeline.assess_risk(request)
        return result

    @app.get("/health", response_model=HealthResponse)
    async def health():
        """Health check endpoint."""
        det_ok = pipeline.detection is not None
        rep_ok = pipeline.replacement is not None
        risk_ok = pipeline.risk is not None
        gw_ok = await pipeline.gateway.check_health()

        return HealthResponse(
            status="ok" if all([det_ok, rep_ok, risk_ok]) else "degraded",
            version=__version__,
            detection_engine=det_ok,
            replacement_engine=rep_ok,
            risk_engine=risk_ok,
            gateway=gw_ok,
            config_hash=config_hash(cfg),
        )

    @app.post("/config", response_model=ConfigResponse)
    async def get_config():
        """Return current configuration."""
        return ConfigResponse(
            config=cfg.model_dump(),
            effective=cfg.model_dump(),
        )

    @app.post("/forward")
    async def forward_prompt(
        request: FilterRequest,
        model: Optional[str] = None,
    ):
        """Filter prompt and forward to LLM in one step."""
        filtered, llm_response = await pipeline.filter_and_forward(request, model=model)
        return {
            "filtered": filtered.model_dump(),
            "llm_response": llm_response,
        }

    return app