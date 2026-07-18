"""GeneralizationStrategy plugin — replaces PII with general category labels."""

from __future__ import annotations

from logging import getLogger
from typing import TYPE_CHECKING

from piifilter_strategy_generalize.strategy import GeneralizationStrategy

if TYPE_CHECKING:
    from piifilter.registry.registry import PluginRegistry

logger = getLogger(__name__)


async def register_plugin(registry: "PluginRegistry") -> None:
    """Register the GeneralizationStrategy with the plugin registry.

    Args:
        registry: The central ``PluginRegistry`` instance.
    """
    strategy = GeneralizationStrategy()
    registry.register_strategy(strategy)
    logger.info("Registered GeneralizationStrategy as '%s'", strategy.name)