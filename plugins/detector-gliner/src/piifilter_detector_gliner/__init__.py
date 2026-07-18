"""GLiNER PII Detector plugin — auto-discovery entry point.

Exposes ``register_plugin(registry)`` so that
``PluginRegistry.discover()`` can find and register this detector.
"""

from __future__ import annotations

import logging

from piifilter.registry.registry import PluginRegistry

from piifilter_detector_gliner.detector import GLiNERDetector

logger = logging.getLogger(__name__)


def register_plugin(registry: PluginRegistry) -> None:
    """Register the GLiNERDetector with the given *registry*.

    Called automatically by ``PluginRegistry.discover()`` when the
    ``piifilter_detector_gliner`` package is scanned.
    """
    detector = GLiNERDetector()
    registry.register_detector(detector)
    logger.info("Registered GLiNERDetector as '%s'", detector.name)