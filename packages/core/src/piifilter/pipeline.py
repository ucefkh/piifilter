"""PIIFilter pipeline — orchestrates detection → risk → replacement → gateway."""

from __future__ import annotations

import time
from typing import Optional

from piifilter.config import FilterConfig
from piifilter.detection.engine import DetectionEngine
from piifilter.replacement.engine import ReplacementEngine
from piifilter.risk.engine import RiskEngine
from piifilter.gateway.proxy import LLMGateway
from piifilter.shared.models import (
    DetectedEntity,
    FilterRequest,
    FilterResponse,
    Replacement,
    ReplacementMode,
    RiskAssessment,
    RiskLevel,
    ScanRequest,
    ScanResponse,
    RiskRequest,
    RiskResponse,
)


class FilterPipeline:
    """Main pipeline orchestration for PIIFilter."""

    def __init__(self, config: Optional[FilterConfig] = None):
        self.config = config or FilterConfig()
        self.detection = DetectionEngine(self.config)
        self.replacement = ReplacementEngine(self.config)
        self.risk = RiskEngine(self.config)
        self.gateway = LLMGateway(self.config)

    async def filter(self, request: FilterRequest) -> FilterResponse:
        """Run the full filter pipeline: detect → risk → replace."""
        start = time.perf_counter()
        mode = request.mode or ReplacementMode(self.config.replacement.mode)

        # Step 1: Detect entities
        entities = await self.detection.detect(
            request.prompt,
            entity_filter=request.entities,
        )

        # Step 2: Calculate risk
        risk = await self.risk.assess(request.prompt, entities)

        # Step 3: Replace entities
        filtered_text, replacements = await self.replacement.replace(
            request.prompt,
            entities,
            mode=mode,
            policy=request.policy,
        )

        latency_ms = (time.perf_counter() - start) * 1000

        return FilterResponse(
            original=request.prompt,
            filtered=filtered_text,
            risk=risk,
            entities=entities,
            replacements=replacements,
            latency_ms=round(latency_ms, 2),
        )

    async def scan(self, request: ScanRequest) -> ScanResponse:
        """Detect entities in a prompt without modifying it."""
        start = time.perf_counter()
        entities = await self.detection.detect(request.prompt)
        risk = await self.risk.assess(request.prompt, entities)
        latency_ms = (time.perf_counter() - start) * 1000

        return ScanResponse(
            entities=entities,
            count=len(entities),
            risk=risk,
            latency_ms=round(latency_ms, 2),
        )

    async def assess_risk(self, request: RiskRequest) -> RiskResponse:
        """Assess risk of a prompt without modifying it."""
        start = time.perf_counter()
        entities = await self.detection.detect(request.prompt)
        risk = await self.risk.assess(request.prompt, entities)
        latency_ms = (time.perf_counter() - start) * 1000

        return RiskResponse(
            assessment=risk,
            latency_ms=round(latency_ms, 2),
        )

    async def filter_and_forward(
        self,
        request: FilterRequest,
        model: Optional[str] = None,
    ) -> tuple[FilterResponse, str]:
        """Filter a prompt and forward it to an LLM."""
        filtered = await self.filter(request)
        llm_response = await self.gateway.forward(filtered.filtered, model=model)
        return filtered, llm_response