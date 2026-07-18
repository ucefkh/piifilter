"""PIIFilter REST API app — transport layer for the core pipeline.

This module exposes ``create_app()`` for programmatic use (e.g. with
``uvicorn`` directly) and a ``register_plugin()`` function so the
plugin registry can discover the API as a plugin.
"""

from __future__ import annotations

import logging
from typing import Optional

from piifilter.interfaces.plugin import Plugin
from piifilter.registry.registry import PluginRegistry

logger = logging.getLogger(__name__)


class RESTAPIPlugin(Plugin):
    """Registers the REST API as a pipeline plugin for lifecycle hooks."""

    name = "piifilter_api"
    version = "2.0.0"
    description = "REST API transport for PIIFilter (FastAPI)"

    async def initialize(self) -> None:
        logger.info("REST API plugin initialised")

    async def shutdown(self) -> None:
        logger.info("REST API plugin shut down")


def create_plugin() -> RESTAPIPlugin:
    """Factory called by PluginLoader."""
    return RESTAPIPlugin()


async def register_plugin(registry: PluginRegistry) -> None:
    """Register the REST API plugin with the given registry (auto-discovery)."""
    plugin = create_plugin()
    registry.register_plugin(plugin)


def create_app(config_path: Optional[str] = None):
    """Create a FastAPI application with the pipeline loaded.

    Args:
        config_path: Optional path to a YAML config file.

    Returns:
        ``fastapi.FastAPI`` instance ready to run.
    """
    from piifilter_api.server import create_app as _create_app
    return _create_app(config_path=config_path)


__all__ = [
    "RESTAPIPlugin",
    "create_plugin",
    "register_plugin",
    "create_app",
]