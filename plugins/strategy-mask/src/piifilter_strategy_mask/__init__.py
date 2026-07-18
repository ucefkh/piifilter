"""MaskStrategy plugin — masks PII with [ENTITY_TYPE] labels."""

from __future__ import annotations

from logging import getLogger
from typing import TYPE_CHECKING

from piifilter_strategy_mask.strategy import MaskStrategy

if TYPE_CHECKING:
    from piifilter.registry.registry import PluginRegistry

logger = getLogger(__name__)


async def register_plugin(registry: "PluginRegistry") -> None:
    """Register the MaskStrategy with the plugin registry.

    Args:
        registry: The central ``PluginRegistry`` instance.
    """
    strategy = MaskStrategy()
    registry.register_strategy(strategy)
    logger.info("Registered MaskStrategy as '%s'", strategy.name)