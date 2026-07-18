"""LM Studio provider plugin — registers the LM Studio provider with the registry."""

from __future__ import annotations

from logging import getLogger
from typing import TYPE_CHECKING

from piifilter_provider_lmstudio.provider import LMStudioProvider

if TYPE_CHECKING:
    from piifilter.registry.registry import PluginRegistry

logger = getLogger(__name__)


async def register_plugin(registry: "PluginRegistry") -> None:
    """Register the LM Studio provider with the plugin registry.

    Args:
        registry: The central ``PluginRegistry`` instance.
    """
    provider = LMStudioProvider()
    registry.register_provider(provider)
    logger.info("Registered provider '%s'", provider.name)