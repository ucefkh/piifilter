from __future__ import annotations

import importlib
import logging
from pathlib import Path
from typing import Any

import yaml

from piifilter.interfaces.detector import Detector
from piifilter.interfaces.plugin import Plugin
from piifilter.interfaces.policy import PolicyEngine
from piifilter.interfaces.provider import Provider
from piifilter.interfaces.strategy import ReplacementStrategy
from piifilter.registry.registry import PluginRegistry

logger = logging.getLogger(__name__)


class PluginSpec:
    """Describes a single plugin from a config file entry."""

    def __init__(
        self,
        module: str,
        *,
        kind: str = "plugin",
        config: dict[str, Any] | None = None,
        version: str | None = None,
        min_version: str | None = None,
    ) -> None:
        self.module = module
        self.kind = kind  # "plugin", "detector", "provider", "strategy", "policy"
        self.config = config or {}
        self.version = version
        self.min_version = min_version

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> PluginSpec:
        return cls(
            module=d["module"],
            kind=d.get("kind", "plugin"),
            config=d.get("config", {}),
            version=str(d.get("version")) if d.get("version") else None,
            min_version=str(d.get("min_version")) if d.get("min_version") else None,
        )


class PluginLoaderError(Exception):
    """Base exception for plugin loading errors."""


class PluginVersionConflictError(PluginLoaderError):
    """Raised when a plugin's version conflicts with requirements."""


class PluginInterfaceMismatchError(PluginLoaderError):
    """Raised when a plugin doesn't satisfy expected interface contract."""


class PluginLoader:
    """Loads plugins from configuration into a PluginRegistry.

    Supports:
    - Loading from a YAML config file listing plugin specifications
    - Per-plugin version constraints
    - Interface validation
    """

    def __init__(self, registry: PluginRegistry) -> None:
        self._registry = registry

    # ------------------------------------------------------------------
    # Load from config file
    # ------------------------------------------------------------------

    async def load_from_file(self, path: str | Path) -> int:
        """Load plugins defined in a YAML config file.

        Expected YAML format::

            plugins:
              - module: piifilter_presidio
                kind: plugin
                config:
                  lang: en
                min_version: "0.1.0"

              - module: piifilter_regex_detector
                kind: detector

        Returns the number of successfully loaded plugins.
        """
        path = Path(path)
        if not path.exists():
            raise PluginLoaderError(f"Plugin config file not found: {path}")

        raw = path.read_text(encoding="utf-8")
        data = yaml.safe_load(raw)
        if not data or "plugins" not in data:
            logger.warning("No 'plugins' key found in %s", path)
            return 0

        specs = [PluginSpec.from_dict(entry) for entry in data["plugins"]]
        return await self.load_specs(specs)

    async def load_specs(self, specs: list[PluginSpec]) -> int:
        """Load a list of PluginSpec entries into the registry."""
        count = 0
        for spec in specs:
            try:
                await self._load_spec(spec)
                count += 1
            except PluginLoaderError as exc:
                logger.error("Failed to load plugin spec %s: %s", spec.module, exc)
        return count

    async def _load_spec(self, spec: PluginSpec) -> None:
        module = importlib.import_module(spec.module)

        if spec.kind == "plugin":
            if not hasattr(module, "create_plugin"):
                raise PluginInterfaceMismatchError(
                    f"Module '{spec.module}' must export 'create_plugin(config) -> Plugin'"
                )
            plugin = module.create_plugin(spec.config)
            if not isinstance(plugin, Plugin):
                raise PluginInterfaceMismatchError(
                    f"'create_plugin' in '{spec.module}' did not return a Plugin instance"
                )
            self._validate_version(spec, plugin)
            self._registry.register_plugin(plugin)

        elif spec.kind == "detector":
            if not hasattr(module, "create_detector"):
                raise PluginInterfaceMismatchError(
                    f"Module '{spec.module}' must export 'create_detector(config) -> Detector'"
                )
            detector = module.create_detector(spec.config)
            if not isinstance(detector, Detector):
                raise PluginInterfaceMismatchError(
                    f"'create_detector' in '{spec.module}' did not return a Detector instance"
                )
            self._registry.register_detector(detector)

        elif spec.kind == "provider":
            if not hasattr(module, "create_provider"):
                raise PluginInterfaceMismatchError(
                    f"Module '{spec.module}' must export 'create_provider(config) -> Provider'"
                )
            provider = module.create_provider(spec.config)
            if not isinstance(provider, Provider):
                raise PluginInterfaceMismatchError(
                    f"'create_provider' in '{spec.module}' did not return a Provider instance"
                )
            self._registry.register_provider(provider)

        elif spec.kind == "strategy":
            if not hasattr(module, "create_strategy"):
                raise PluginInterfaceMismatchError(
                    f"Module '{spec.module}' must export 'create_strategy(config) -> ReplacementStrategy'"
                )
            strategy = module.create_strategy(spec.config)
            if not isinstance(strategy, ReplacementStrategy):
                raise PluginInterfaceMismatchError(
                    f"'create_strategy' in '{spec.module}' did not return a ReplacementStrategy instance"
                )
            self._registry.register_strategy(strategy)

        elif spec.kind == "policy":
            if not hasattr(module, "create_policy"):
                raise PluginInterfaceMismatchError(
                    f"Module '{spec.module}' must export 'create_policy(config) -> PolicyEngine'"
                )
            policy = module.create_policy(spec.config)
            if not isinstance(policy, PolicyEngine):
                raise PluginInterfaceMismatchError(
                    f"'create_policy' in '{spec.module}' did not return a PolicyEngine instance"
                )
            self._registry.register_policy(policy)

        else:
            raise PluginLoaderError(f"Unknown plugin kind: '{spec.kind}'")

        logger.info("Loaded %s: %s", spec.kind, spec.module)

    @staticmethod
    def _validate_version(spec: PluginSpec, plugin: Plugin) -> None:
        """Check version constraints on a plugin (only applies to Plugin kind)."""
        if spec.min_version:
            from packaging.version import Version, InvalidVersion

            try:
                installed = Version(plugin.version)
                required = Version(spec.min_version)
            except (InvalidVersion, ValueError) as exc:
                raise PluginVersionConflictError(
                    f"Cannot compare versions for '{spec.module}': {exc}"
                )

            if spec.version and spec.version != plugin.version:
                raise PluginVersionConflictError(
                    f"Plugin '{spec.module}' version {plugin.version} "
                    f"does not match required {spec.version}"
                )

            if installed < required:
                raise PluginVersionConflictError(
                    f"Plugin '{spec.module}' version {plugin.version} "
                    f"is below minimum required {spec.min_version}"
                )