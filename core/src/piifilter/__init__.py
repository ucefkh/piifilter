"""PIIFilter v2 — Local-first AI privacy gateway.

Architecture:
- Session: single unified object through pipeline
- Pipeline: event-driven stage chain
- Interfaces: Detector, Provider, ReplacementStrategy, PolicyEngine, Plugin
- PluginRegistry: discovers and manages plugins
- EventBus: before/after hooks per stage

No provider code. No transport code. No Chrome code.
All plugins live in piifilter.plugins.* or external packages.
"""

from __future__ import annotations

from piifilter.session import Session
from piifilter.pipeline import FilterPipeline
from piifilter.config import FilterConfig
from piifilter.registry.registry import PluginRegistry
from piifilter.events.bus import EventBus, PipelineEvent

__version__ = "2.0.0"

__all__ = [
    "Session",
    "FilterPipeline",
    "FilterConfig",
    "PluginRegistry",
    "EventBus",
    "PipelineEvent",
]