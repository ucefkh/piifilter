"""PIIFilter CLI app — transport layer for the core pipeline.

This module exposes ``run()`` for programmatic use and a
``register_plugin()`` function so the plugin registry can discover
the CLI as a plugin (its lifecycle hooks).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from piifilter.interfaces.plugin import Plugin
from piifilter.registry.registry import PluginRegistry

logger = logging.getLogger(__name__)


class CLIPlugin(Plugin):
    """Registers the CLI as a pipeline plugin for lifecycle hooks."""

    name = "piifilter_cli"
    version = "2.0.0"
    description = "CLI transport for PIIFilter (Click-based)"

    async def initialize(self) -> None:
        logger.info("CLI plugin initialised")

    async def shutdown(self) -> None:
        logger.info("CLI plugin shut down")


def create_plugin() -> CLIPlugin:
    """Factory called by PluginLoader."""
    return CLIPlugin()


async def register_plugin(registry: PluginRegistry) -> None:
    """Register the CLI plugin with the given registry (auto-discovery)."""
    plugin = create_plugin()
    registry.register_plugin(plugin)


def run(args: Optional[list[str]] = None):
    """Entry point to invoke the CLI programmatically.

    Args:
        args: Argument list (defaults to ``sys.argv[1:]``).

    Returns:
        ``click.testing.Result`` if *args* were provided, else ``None``.
    """
    from piifilter_cli.main import cli
    from click.testing import CliRunner

    if args is None:
        cli()
    else:
        runner = CliRunner()
        result = runner.invoke(cli, args)
        if result.exception:
            logger.error("CLI error: %s", result.exception)
        return result


__all__ = [
    "CLIPlugin",
    "create_plugin",
    "register_plugin",
    "run",
]