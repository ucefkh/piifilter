from __future__ import annotations

import importlib
import logging
import pkgutil
from typing import Any, Optional, TypeVar

from piifilter.interfaces.detector import Detector
from piifilter.interfaces.provider import Provider
from piifilter.interfaces.strategy import ReplacementStrategy
from piifilter.interfaces.policy import PolicyEngine
from piifilter.interfaces.plugin import Plugin
from piifilter.interfaces.metrics import MetricsProvider

_T = TypeVar("_T")

logger = logging.getLogger(__name__)


class PluginRegistryError(Exception):
    """Base exception for registry errors."""


class DuplicatePluginError(PluginRegistryError):
    """Raised when a plugin with the same name is already registered."""


class PluginNotFoundError(PluginRegistryError):
    """Raised when a named plugin is not found in the registry."""


class PluginRegistry:
    """Central registry for all plugins.
    
    Core never knows which implementations exist — it asks the registry.
    
    Discovery:
    - Plugins can be registered manually via register_*()
    - Or auto-discovered via discover() scanning installed packages matching a prefix
    - Or loaded from a config file listing plugin paths (via PluginLoader)
    """

    def __init__(self, allow_overwrite: bool = False) -> None:
        self._detectors: dict[str, Detector] = {}
        self._providers: dict[str, Provider] = {}
        self._strategies: dict[str, ReplacementStrategy] = {}
        self._policies: dict[str, PolicyEngine] = {}
        self._plugins: dict[str, Plugin] = {}
        self._metrics: Optional[MetricsProvider] = None
        self._allow_overwrite = allow_overwrite

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register_detector(self, detector: Detector, overwrite: bool | None = None) -> None:
        self._register("detector", self._detectors, detector.name, detector, overwrite)

    def register_provider(self, provider: Provider, overwrite: bool | None = None) -> None:
        self._register("provider", self._providers, provider.name, provider, overwrite)

    def register_strategy(self, strategy: ReplacementStrategy, overwrite: bool | None = None) -> None:
        self._register("strategy", self._strategies, strategy.name, strategy, overwrite)

    def register_policy(self, policy: PolicyEngine, overwrite: bool | None = None) -> None:
        self._register("policy", self._policies, policy.name, policy, overwrite)

    def register_plugin(self, plugin: Plugin, overwrite: bool | None = None) -> None:
        self._register("plugin", self._plugins, plugin.name, plugin, overwrite)

    def set_metrics(self, provider: MetricsProvider) -> None:
        self._metrics = provider

    def _register(
        self,
        kind: str,
        registry: dict[str, _T],
        name: str,
        instance: _T,
        overwrite: bool | None,
    ) -> None:
        allow = self._allow_overwrite if overwrite is None else overwrite
        if name in registry and not allow:
            raise DuplicatePluginError(
                f"{kind} '{name}' is already registered. "
                f"Set overwrite=True to replace it."
            )
        registry[name] = instance
        logger.debug("Registered %s: %s", kind, name)

    # ------------------------------------------------------------------
    # Getters
    # ------------------------------------------------------------------

    def get_detector(self, name: str) -> Detector:
        if name not in self._detectors:
            raise PluginNotFoundError(f"Detector '{name}' not found in registry")
        return self._detectors[name]

    def get_provider(self, name: str) -> Provider:
        if name not in self._providers:
            raise PluginNotFoundError(f"Provider '{name}' not found in registry")
        return self._providers[name]

    def get_strategy(self, name: str) -> ReplacementStrategy:
        if name not in self._strategies:
            raise PluginNotFoundError(f"Strategy '{name}' not found in registry")
        return self._strategies[name]

    def get_policy(self, name: str) -> PolicyEngine:
        if name not in self._policies:
            raise PluginNotFoundError(f"PolicyEngine '{name}' not found in registry")
        return self._policies[name]

    def get_metrics(self) -> Optional[MetricsProvider]:
        return self._metrics

    def get_plugin(self, name: str) -> Plugin:
        if name not in self._plugins:
            raise PluginNotFoundError(f"Plugin '{name}' not found in registry")
        return self._plugins[name]

    # ------------------------------------------------------------------
    # Safe getters (return None instead of raising)
    # ------------------------------------------------------------------

    def get_detector_or_none(self, name: str) -> Optional[Detector]:
        return self._detectors.get(name)

    def get_provider_or_none(self, name: str) -> Optional[Provider]:
        return self._providers.get(name)

    def get_strategy_or_none(self, name: str) -> Optional[ReplacementStrategy]:
        return self._strategies.get(name)

    def get_policy_or_none(self, name: str) -> Optional[PolicyEngine]:
        return self._policies.get(name)

    def get_plugin_or_none(self, name: str) -> Optional[Plugin]:
        return self._plugins.get(name)

    # ------------------------------------------------------------------
    # Listing
    # ------------------------------------------------------------------

    def list_detectors(self) -> list[Detector]:
        return list(self._detectors.values())

    def list_providers(self) -> list[Provider]:
        return list(self._providers.values())

    def list_strategies(self) -> list[ReplacementStrategy]:
        return list(self._strategies.values())

    def list_policies(self) -> list[PolicyEngine]:
        return list(self._policies.values())

    def list_plugins(self) -> list[Plugin]:
        return list(self._plugins.values())

    def list_registered(self) -> dict[str, Any]:
        """Summary of everything registered: category -> [names]."""
        return {
            "detectors": list(self._detectors.keys()),
            "providers": list(self._providers.keys()),
            "strategies": list(self._strategies.keys()),
            "policies": list(self._policies.keys()),
            "plugins": list(self._plugins.keys()),
            "metrics": "set" if self._metrics else None,
        }

    # ------------------------------------------------------------------
    # Discovery (auto-scan)
    # ------------------------------------------------------------------

    async def discover(self, prefix: str = "piifilter_") -> int:
        """Auto-discover installed plugins via package scanning.
        
        Scans all importable modules whose name starts with *prefix*.
        Each module may export a ``register_plugin(registry)`` function
        that registers itself with this registry.
        
        Returns the number of successfully discovered plugins.
        """
        count = 0
        for module_info in pkgutil.iter_modules():
            if module_info.name.startswith(prefix):
                try:
                    module = importlib.import_module(module_info.name)
                    if hasattr(module, "register_plugin"):
                        await module.register_plugin(self)
                        count += 1
                        logger.info("Discovered plugin: %s", module_info.name)
                    else:
                        logger.debug(
                            "Skipped %s: no register_plugin function",
                            module_info.name,
                        )
                except Exception as exc:
                    logger.warning(
                        "Failed to load plugin %s: %s", module_info.name, exc
                    )
        return count

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def initialize_all(self) -> None:
        """Initialize all registered plugins.
        
        Order: standalone plugins first, then detectors/providers/strategies/policies
        that are Plugin subclasses (they may depend on the registry being populated).
        """
        errors: list[tuple[str, Exception]] = []

        for name, plugin in self._plugins.items():
            try:
                await plugin.initialize()
                logger.info("Initialized plugin: %s", name)
            except Exception as exc:
                logger.error("Failed to initialize plugin '%s': %s", name, exc)
                errors.append((name, exc))

        for name, item in self._detectors.items():
            if isinstance(item, Plugin):
                try:
                    await item.initialize()
                except Exception as exc:
                    logger.error("Failed to init detector '%s': %s", name, exc)
                    errors.append((name, exc))

        for name, item in self._providers.items():
            if isinstance(item, Plugin):
                try:
                    await item.initialize()
                except Exception as exc:
                    logger.error("Failed to init provider '%s': %s", name, exc)
                    errors.append((name, exc))

        for name, item in self._strategies.items():
            if isinstance(item, Plugin):
                try:
                    await item.initialize()
                except Exception as exc:
                    logger.error("Failed to init strategy '%s': %s", name, exc)
                    errors.append((name, exc))

        for name, item in self._policies.items():
            if isinstance(item, Plugin):
                try:
                    await item.initialize()
                except Exception as exc:
                    logger.error("Failed to init policy '%s': %s", name, exc)
                    errors.append((name, exc))

        if self._metrics is not None:
            try:
                await self._metrics.initialize()
            except Exception as exc:
                logger.error("Failed to init metrics provider: %s", exc)
                errors.append(("metrics", exc))

        if errors:
            raise PluginRegistryError(
                f"{len(errors)} plugin(s) failed to initialize; see logs for details"
            )

    async def shutdown_all(self) -> None:
        """Graceful shutdown of all registered plugins."""
        for name, plugin in self._plugins.items():
            try:
                await plugin.shutdown()
            except Exception as exc:
                logger.error("Error shutting down plugin '%s': %s", name, exc)

        for name, item in self._detectors.items():
            if isinstance(item, Plugin):
                try:
                    await item.shutdown()
                except Exception as exc:
                    logger.error(
                        "Error shutting down detector '%s': %s", name, exc
                    )

        for name, item in self._providers.items():
            if isinstance(item, Plugin):
                try:
                    await item.shutdown()
                except Exception as exc:
                    logger.error(
                        "Error shutting down provider '%s': %s", name, exc
                    )

        for name, item in self._strategies.items():
            if isinstance(item, Plugin):
                try:
                    await item.shutdown()
                except Exception as exc:
                    logger.error(
                        "Error shutting down strategy '%s': %s", name, exc
                    )

        for name, item in self._policies.items():
            if isinstance(item, Plugin):
                try:
                    await item.shutdown()
                except Exception as exc:
                    logger.error(
                        "Error shutting down policy '%s': %s", name, exc
                    )

        if self._metrics is not None:
            try:
                await self._metrics.shutdown()
            except Exception as exc:
                logger.error(
                    "Error shutting down metrics provider: %s", exc
                )

        logger.info("All plugins shut down")