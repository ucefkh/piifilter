"""Presidio PII Detector plugin — auto-discovery entry point.

Exposes ``register_plugin(registry)`` so that
``PluginRegistry.discover()`` can find and register this detector.
"""

from __future__ import annotations

import logging

from piifilter.registry.registry import PluginRegistry

from piifilter_detector_presidio.detector import PresidioDetector

logger = logging.getLogger(__name__)


def register_plugin(registry: PluginRegistry) -> None:
    """Register the PresidioDetector with the given *registry*.

    Called automatically by ``PluginRegistry.discover()`` when the
    ``piifilter_detector_presidio`` package is scanned.
    """
    detector = PresidioDetector()
    registry.register_detector(detector)
    logger.info("Registered PresidioDetector as '%s'", detector.name)