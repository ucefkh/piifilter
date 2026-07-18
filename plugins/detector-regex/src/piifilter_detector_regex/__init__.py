"""RegexDetector plugin for PIIFilter.

Registers the ``RegexDetector`` with the plugin registry so it becomes
available during the ``discover()`` scan or via explicit registration.
"""

from __future__ import annotations

from piifilter.interfaces.detector import Detector
from piifilter.shared.models import DetectedEntity, EntityType
from piifilter.session import Session

from .detector import RegexDetector


async def register_plugin(registry) -> None:
    """Register ``RegexDetector`` with the plugin *registry*.

    Called automatically during ``registry.discover()`` when the module
    is found via ``pkgutil.iter_modules()``.
    """
    registry.register_detector(RegexDetector())


__all__ = [
    "RegexDetector",
    "register_plugin",
]