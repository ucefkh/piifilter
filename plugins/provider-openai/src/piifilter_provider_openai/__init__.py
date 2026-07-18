"""OpenAI provider plugin — registers the OpenAI provider with the registry."""

from __future__ import annotations

from logging import getLogger
from typing import TYPE_CHECKING

from piifilter_provider_openai.provider import OpenAIProvider

if TYPE_CHECKING:
    from piifilter.registry.registry import PluginRegistry

logger = getLogger(__name__)


async def register_plugin(registry: "PluginRegistry") -> None:
    """Register the OpenAI provider with the plugin registry.

    Args:
        registry: The central ``PluginRegistry`` instance.
    """
    provider = OpenAIProvider()
    registry.register_provider(provider)
    logger.info("Registered provider '%s'", provider.name)