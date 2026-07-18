"""PIIFilter client — the core PIIFilter SDK class."""

from __future__ import annotations

import logging
from typing import Any, Optional

# ── Import piifilter internals directly ────────────────────────────────
# We import submodules individually rather than going through
# piifilter/__init__.py, which triggers a circular import due to the
# module/package shadowing between piifilter/pipeline.py (real module)
# and piifilter/pipeline/__init__.py (placeholder package).
import piifilter.session as _piifilter_session
import piifilter.config as _piifilter_config
import piifilter.registry.registry as _piifilter_registry
import piifilter.events.bus as _piifilter_bus
import piifilter.shared.models as _piifilter_models
import piifilter.errors as _piifilter_errors

Session = _piifilter_session.Session
FilterConfig = _piifilter_config.FilterConfig
PluginRegistry = _piifilter_registry.PluginRegistry
EventBus = _piifilter_bus.EventBus
ReplacementMode = _piifilter_models.ReplacementMode
PIIFilterError = _piifilter_errors.PIIFilterError

# ── Import FilterPipeline from the core package ──────────────────────
# piifilter/pipeline/__init__.py is the package that defines FilterPipeline.
from piifilter.pipeline import FilterPipeline  # noqa: F811

logger = logging.getLogger(__name__)


class PIIFilter:
    """Programmatic SDK for PIIFilter — no HTTP server, no CLI.

    The easiest way for developers to use PIIFilter::

        from piifilter_sdk import PIIFilter

        async with PIIFilter() as pii:
            # Filter a prompt — detect, assess risk, replace
            result = await pii.filter("My SSN is 123-45-6789")

            # Just scan for entities without replacing
            scan_result = await pii.scan("Contact me at john@example.com")

            # Filter + forward to an LLM provider
            response = await pii.forward(
                "What is my email?", provider="lmstudio"
            )

    Args:
        config_path: Optional path to a YAML config file.
        detectors: Pre-initialized detector instances to register.
        strategies: Pre-initialized replacement strategy instances.
        providers: Pre-initialized provider instances.
        auto_discover: If True, auto-discover installed plugins via
            package scanning (prefix ``piifilter_``).
        config: A pre-built FilterConfig (alternative to config_path).
        registry: A pre-populated PluginRegistry (alternative to
            auto-discovery).
    """

    def __init__(
        self,
        config_path: Optional[str | Path] = None,
        detectors: Optional[list[Any]] = None,
        strategies: Optional[list[Any]] = None,
        providers: Optional[list[Any]] = None,
        auto_discover: bool = False,
        config: Optional[FilterConfig] = None,
        registry: Optional[PluginRegistry] = None,
    ) -> None:
        # ── Configuration ──────────────────────────────────────────────────
        if config is not None:
            self.config = config
        elif config_path is not None:
            self.config = FilterConfig.from_yaml(Path(config_path))
        else:
            self.config = FilterConfig()

        # ── Registry ──────────────────────────────────────────────────────
        self.registry = registry if registry is not None else PluginRegistry()
        self._auto_discover = auto_discover

        # Register any pre-built plugin instances
        if detectors:
            for d in detectors:
                self.registry.register_detector(d)
        if strategies:
            for s in strategies:
                self.registry.register_strategy(s)
        if providers:
            for p in providers:
                self.registry.register_provider(p)

        # ── Event bus & pipeline ──────────────────────────────────────────
        self.event_bus = EventBus()
        self.pipeline = FilterPipeline(
            config=self.config,
            registry=self.registry,
            event_bus=self.event_bus,
        )

        # ── Lifecycle tracking ─────────────────────────────────────────────
        self._initialized = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def filter(
        self,
        prompt: str,
        mode: Optional[str | ReplacementMode] = None,
        conversation_id: Optional[str] = None,
        *,
        provider: Optional[str] = None,
    ) -> dict[str, Any]:
        """Run the full PIIFilter pipeline: detect -> risk -> policy -> replace.

        Args:
            prompt: The user prompt to process.
            mode: Replacement mode (e.g. ``"semantic"``, ``"redact"``,
                ``"hash"``). Defaults to config value.
            conversation_id: Optional conversation identifier for audit
                correlation.
            provider: Optional provider name to forward to after
                filtering.

        Returns:
            dict with keys:
                - ``filtered`` -- the prompt after PII replacement
                - ``risk`` -- ``RiskAssessment`` object
                - ``entities`` -- list of ``DetectedEntity`` objects
                - ``replacements`` -- list of ``Replacement`` objects
                - ``latency_ms`` -- pipeline execution time in ms
                - ``blocked`` -- whether the prompt was blocked
                - ``block_reason`` -- reason if blocked
                - ``request_id`` -- unique request identifier
                - ``audit_events`` -- pipeline audit trail
        """
        await self._ensure_initialized()

        mode_enum = self._resolve_mode(mode)
        session = Session(
            prompt=prompt,
            mode=mode_enum,
            conversation_id=conversation_id,
        )

        # Set provider config if forwarding
        if provider:
            session.provider_config = self.config.provider
            session.provider_config.name = provider

        session = await self.pipeline.run(session)

        return self._build_filter_result(session)

    async def scan(self, prompt: str) -> dict[str, Any]:
        """Scan a prompt for PII entities *without* replacing them.

        Runs detection and risk assessment only -- no replacement,
        no LLM forwarding.

        Args:
            prompt: The text to scan.

        Returns:
            dict with keys:
                - ``entities`` -- list of ``DetectedEntity`` objects
                - ``risk`` -- ``RiskAssessment`` object
                - ``count`` -- number of entities detected
                - ``latency_ms`` -- pipeline execution time in ms
                - ``blocked`` -- whether the prompt was blocked
                - ``block_reason`` -- reason if blocked
                - ``request_id`` -- unique request identifier
        """
        await self._ensure_initialized()

        session = Session(prompt=prompt, mode=ReplacementMode.PASSTHROUGH)
        session = await self.pipeline.run(session)

        return {
            "entities": session.entities,
            "risk": session.risk,
            "count": len(session.entities),
            "latency_ms": session.latency_ms,
            "blocked": session.blocked,
            "block_reason": session.block_reason,
            "request_id": session.request_id,
        }

    async def forward(
        self,
        prompt: str,
        mode: Optional[str | ReplacementMode] = None,
        conversation_id: Optional[str] = None,
        *,
        provider: Optional[str] = None,
        model: Optional[str] = None,
    ) -> dict[str, Any]:
        """Filter a prompt, then forward it to an LLM provider.

        Runs the full pipeline: detect -> risk -> policy -> replace ->
        forward. The response from the LLM is included in the result.

        Args:
            prompt: The user prompt to process.
            mode: Replacement mode override.
            conversation_id: Optional conversation identifier.
            provider: Provider name (e.g. ``"lmstudio"``,
                ``"openai"``). Defaults to config value.
            model: Optional model override for the provider.

        Returns:
            dict with keys:
                - ``filtered`` -- the prompt after PII replacement
                - ``response`` -- the LLM response text (or error
                  message if forwarding failed)
                - ``risk`` -- ``RiskAssessment`` object
                - ``entities`` -- list of ``DetectedEntity`` objects
                - ``replacements`` -- list of ``Replacement`` objects
                - ``latency_ms`` -- pipeline execution time in ms
                - ``blocked`` -- whether the prompt was blocked
                - ``block_reason`` -- reason if blocked
                - ``request_id`` -- unique request identifier
        """
        await self._ensure_initialized()

        mode_enum = self._resolve_mode(mode)
        session = Session(
            prompt=prompt,
            mode=mode_enum,
            conversation_id=conversation_id,
        )

        # Configure forwarding
        session.provider_config = self.config.provider
        if provider:
            session.provider_config.name = provider
        if model:
            session.provider_config.default_model = model

        session = await self.pipeline.run(session)

        result = self._build_filter_result(session)
        result["response"] = session.llm_response
        return result

    async def close(self) -> None:
        """Shut down the pipeline and all registered plugins.

        Releases resources held by detectors, providers, and strategies.
        Safe to call multiple times.
        """
        if not self._initialized:
            return
        try:
            await self.pipeline.close()
        except Exception as exc:
            logger.warning("Error during pipeline shutdown: %s", exc)
        self._initialized = False

    async def __aenter__(self) -> PIIFilter:
        await self._ensure_initialized()
        return self

    async def __aexit__(
        self,
        exc_type: Optional[type],
        exc_val: Optional[BaseException],
        exc_tb: Optional[object],
    ) -> None:
        await self.close()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _ensure_initialized(self) -> None:
        """Ensure plugins are initialized (idempotent)."""
        if self._initialized:
            return

        if self._auto_discover:
            discovered = await self.registry.discover()
            if discovered:
                logger.info("Auto-discovered %d plugin(s)", discovered)

        await self.registry.initialize_all()
        self._initialized = True

    @staticmethod
    def _resolve_mode(
        mode: Optional[str | ReplacementMode],
    ) -> Optional[ReplacementMode]:
        """Convert a string mode to a ReplacementMode enum."""
        if mode is None or isinstance(mode, ReplacementMode):
            return mode
        try:
            return ReplacementMode(mode.lower())
        except ValueError:
            valid = ", ".join(m.value for m in ReplacementMode)
            raise PIIFilterError(
                f"Invalid replacement mode '{mode}'. "
                f"Valid options: {valid}",
                code="INVALID_MODE",
            )

    @staticmethod
    def _build_filter_result(session: _piifilter_session.Session) -> dict[str, Any]:
        """Build the standard result dict from a completed session."""
        return {
            "filtered": session.filtered_prompt,
            "risk": session.risk,
            "entities": session.entities,
            "replacements": session.replacements,
            "latency_ms": session.latency_ms,
            "blocked": session.blocked,
            "block_reason": session.block_reason,
            "request_id": session.request_id,
            "audit_events": session.audit_events,
        }