"""SemanticStrategy plugin — replaces PII with deterministic fake aliases."""

from __future__ import annotations

from logging import getLogger
from typing import TYPE_CHECKING

from piifilter_strategy_semantic.strategy import SemanticStrategy

if TYPE_CHECKING:
    from piifilter.registry.registry import PluginRegistry

logger = getLogger(__name__)


async def register_plugin(registry: "PluginRegistry") -> None:
    """Register the SemanticStrategy with the plugin registry.

    Args:
        registry: The central ``PluginRegistry`` instance.
    """
    strategy = SemanticStrategy()
    registry.register_strategy(strategy)
    logger.info("Registered SemanticStrategy as '%s'", strategy.name)