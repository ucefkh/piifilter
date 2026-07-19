"""Comprehensive tests for piifilter.registry.registry — PluginRegistry.

Covers registration, getters, listing, discovery, lifecycle (initialize_all,
shutdown_all), error types, and edge cases.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from piifilter.registry.registry import (
    PluginRegistry,
    DuplicatePluginError,
    PluginNotFoundError,
    PluginRegistryError,
)
from piifilter.interfaces.detector import Detector
from piifilter.interfaces.provider import Provider, ProviderCapabilities
from piifilter.interfaces.strategy import ReplacementStrategy
from piifilter.interfaces.policy import PolicyEngine
from piifilter.interfaces.plugin import Plugin
from piifilter.interfaces.metrics import MetricsProvider


# ── Mock implementations ─────────────────────────────────────────────────


class MockDetector(Detector):
    def __init__(self, name: str = "mock_detector") -> None:
        self._name = name

    @property
    def name(self) -> str:
        return self._name

    async def detect(self, text: str, *, language: str | None = None) -> list[dict[str, Any]]:
        return []

    async def initialize(self) -> None:
        pass

    async def shutdown(self) -> None:
        pass


class MockProvider(Provider):
    def __init__(self, name: str = "mock_provider") -> None:
        self._name = name

    @property
    def name(self) -> str:
        return self._name

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities()

    async def initialize(self) -> None:
        pass

    async def shutdown(self) -> None:
        pass

    async def check_health(self) -> bool:
        return True

    async def forward(self, session) -> str:
        return f"Echo: {session.prompt}"


class MockStrategy(ReplacementStrategy):
    def __init__(self, name: str = "mock_strategy") -> None:
        self._name = name

    @property
    def name(self) -> str:
        return self._name

    async def apply(self, text: str, detections: list[dict]) -> str:
        return text

    async def initialize(self) -> None:
        pass

    async def shutdown(self) -> None:
        pass


class MockPolicy(PolicyEngine):
    def __init__(self, name: str = "mock_policy") -> None:
        self._name = name

    @property
    def name(self) -> str:
        return self._name

    async def evaluate(self, detections: list[dict], context: dict | None = None) -> list[dict]:
        return detections

    async def initialize(self) -> None:
        pass

    async def shutdown(self) -> None:
        pass


class MockPlugin(Plugin):
    def __init__(self, name: str = "mock_plugin", version: str = "1.0.0") -> None:
        self._name = name
        self._version = version
        self.initialized = False
        self.shutdown_called = False

    @property
    def name(self) -> str:
        return self._name

    @property
    def version(self) -> str:
        return self._version

    def metadata(self) -> dict[str, Any]:
        return {"name": self._name, "version": self._version}

    async def initialize(self) -> None:
        self.initialized = True

    async def shutdown(self) -> None:
        self.shutdown_called = True


class MockFailingPlugin(Plugin):
    """Plugin that fails on initialize."""
    def __init__(self, name: str = "failing") -> None:
        self._name = name

    @property
    def name(self) -> str:
        return self._name

    @property
    def version(self) -> str:
        return "0.1.0"

    def metadata(self) -> dict[str, Any]:
        return {"name": self._name}

    async def initialize(self) -> None:
        raise RuntimeError("Initialization failed")

    async def shutdown(self) -> None:
        pass


class MockMetrics(MetricsProvider):
    def __init__(self) -> None:
        self.initialized = False
        self.shutdown_called = False

    def increment(self, metric: str, tags: dict[str, str] | None = None, value: int = 1) -> None:
        pass

    def gauge(self, metric: str, value: float, tags: dict[str, str] | None = None) -> None:
        pass

    def histogram(self, metric: str, value: float, tags: dict[str, str] | None = None) -> None:
        pass

    async def initialize(self) -> None:
        self.initialized = True

    async def shutdown(self) -> None:
        self.shutdown_called = True


@pytest.fixture
def registry():
    return PluginRegistry()


@pytest.fixture
def overwrite_registry():
    return PluginRegistry(allow_overwrite=True)


# ── Registration ─────────────────────────────────────────────────────────


class TestRegistryRegistration:
    """Registering detectors, providers, strategies, policies, plugins."""

    def test_register_detector(self, registry):
        d = MockDetector("test_detector")
        registry.register_detector(d)
        assert registry.get_detector("test_detector") is d

    def test_register_provider(self, registry):
        p = MockProvider("test_provider")
        registry.register_provider(p)
        assert registry.get_provider("test_provider") is p

    def test_register_strategy(self, registry):
        s = MockStrategy("test_strategy")
        registry.register_strategy(s)
        assert registry.get_strategy("test_strategy") is s

    def test_register_policy(self, registry):
        p = MockPolicy("test_policy")
        registry.register_policy(p)
        assert registry.get_policy("test_policy") is p

    def test_register_plugin(self, registry):
        p = MockPlugin("test_plugin")
        registry.register_plugin(p)
        assert registry.get_plugin("test_plugin") is p

    def test_register_metrics(self, registry):
        m = MockMetrics()
        registry.set_metrics(m)
        assert registry.get_metrics() is m

    def test_register_metrics_returns_none_when_not_set(self, registry):
        assert registry.get_metrics() is None

    def test_duplicate_detector_raises(self, registry):
        d = MockDetector("dup")
        registry.register_detector(d)
        with pytest.raises(DuplicatePluginError):
            registry.register_detector(MockDetector("dup"))

    def test_duplicate_provider_raises(self, registry):
        registry.register_provider(MockProvider("dup"))
        with pytest.raises(DuplicatePluginError):
            registry.register_provider(MockProvider("dup"))

    def test_duplicate_strategy_raises(self, registry):
        registry.register_strategy(MockStrategy("dup"))
        with pytest.raises(DuplicatePluginError):
            registry.register_strategy(MockStrategy("dup"))

    def test_duplicate_policy_raises(self, registry):
        registry.register_policy(MockPolicy("dup"))
        with pytest.raises(DuplicatePluginError):
            registry.register_policy(MockPolicy("dup"))

    def test_duplicate_plugin_raises(self, registry):
        registry.register_plugin(MockPlugin("dup"))
        with pytest.raises(DuplicatePluginError):
            registry.register_plugin(MockPlugin("dup"))


class TestRegistryOverwrite:
    """Allow overwrite behaviour."""

    def test_overwrite_detector(self, overwrite_registry):
        d1 = MockDetector("over")
        d2 = MockDetector("over")
        overwrite_registry.register_detector(d1)
        overwrite_registry.register_detector(d2, overwrite=True)
        assert overwrite_registry.get_detector("over") is d2

    def test_overwrite_with_constructor_flag(self):
        reg = PluginRegistry(allow_overwrite=True)
        d1 = MockDetector("x")
        d2 = MockDetector("x")
        reg.register_detector(d1)
        reg.register_detector(d2)  # allow_overwrite is True from constructor
        assert reg.get_detector("x") is d2

    def test_overwrite_plugin(self, overwrite_registry):
        p1 = MockPlugin("plug")
        p2 = MockPlugin("plug")
        overwrite_registry.register_plugin(p1)
        overwrite_registry.register_plugin(p2, overwrite=True)
        assert overwrite_registry.get_plugin("plug") is p2

    def test_per_call_overwrite_trumps_constructor(self):
        """Per-call overwrite=False blocks even when constructor allows."""
        reg = PluginRegistry(allow_overwrite=True)
        reg.register_detector(MockDetector("x"))
        with pytest.raises(DuplicatePluginError):
            reg.register_detector(MockDetector("x"), overwrite=False)

    def test_per_call_overwrite_true_without_constructor(self):
        """Per-call overwrite=True works even when constructor is False."""
        reg = PluginRegistry(allow_overwrite=False)
        reg.register_detector(MockDetector("x"))
        reg.register_detector(MockDetector("x"), overwrite=True)
        # Should succeed


class TestRegistryGetters:
    """Getting registered items (safe and strict)."""

    def test_get_detector_or_none_found(self, registry):
        d = MockDetector("d")
        registry.register_detector(d)
        assert registry.get_detector_or_none("d") is d

    def test_get_detector_or_none_missing(self, registry):
        assert registry.get_detector_or_none("nonexistent") is None

    def test_get_provider_or_none_found(self, registry):
        p = MockProvider("p")
        registry.register_provider(p)
        assert registry.get_provider_or_none("p") is p

    def test_get_provider_or_none_missing(self, registry):
        assert registry.get_provider_or_none("missing") is None

    def test_get_strategy_or_none_found(self, registry):
        s = MockStrategy("s")
        registry.register_strategy(s)
        assert registry.get_strategy_or_none("s") is s

    def test_get_strategy_or_none_missing(self, registry):
        assert registry.get_strategy_or_none("missing") is None

    def test_get_policy_or_none_found(self, registry):
        p = MockPolicy("p")
        registry.register_policy(p)
        assert registry.get_policy_or_none("p") is p

    def test_get_policy_or_none_missing(self, registry):
        assert registry.get_policy_or_none("missing") is None

    def test_get_plugin_or_none_found(self, registry):
        p = MockPlugin("p")
        registry.register_plugin(p)
        assert registry.get_plugin_or_none("p") is p

    def test_get_plugin_or_none_missing(self, registry):
        assert registry.get_plugin_or_none("missing") is None

    def test_get_missing_detector_raises(self, registry):
        with pytest.raises(PluginNotFoundError):
            registry.get_detector("i_do_not_exist")

    def test_get_missing_provider_raises(self, registry):
        with pytest.raises(PluginNotFoundError):
            registry.get_provider("i_do_not_exist")

    def test_get_missing_strategy_raises(self, registry):
        with pytest.raises(PluginNotFoundError):
            registry.get_strategy("i_do_not_exist")

    def test_get_missing_policy_raises(self, registry):
        with pytest.raises(PluginNotFoundError):
            registry.get_policy("i_do_not_exist")

    def test_get_missing_plugin_raises(self, registry):
        with pytest.raises(PluginNotFoundError):
            registry.get_plugin("i_do_not_exist")

    def test_error_messages_include_name(self, registry):
        with pytest.raises(PluginNotFoundError, match="not found"):
            registry.get_detector("ghost")


class TestRegistryListing:
    """list_detectors, list_providers, list_strategies, list_policies, list_plugins."""

    def test_list_detectors_empty(self, registry):
        assert registry.list_detectors() == []

    def test_list_detectors(self, registry):
        d1 = MockDetector("d1")
        d2 = MockDetector("d2")
        registry.register_detector(d1)
        registry.register_detector(d2)
        assert len(registry.list_detectors()) == 2

    def test_list_providers_empty(self, registry):
        assert registry.list_providers() == []

    def test_list_providers(self, registry):
        registry.register_provider(MockProvider("p1"))
        registry.register_provider(MockProvider("p2"))
        assert len(registry.list_providers()) == 2

    def test_list_strategies(self, registry):
        registry.register_strategy(MockStrategy("s1"))
        assert len(registry.list_strategies()) == 1

    def test_list_policies(self, registry):
        registry.register_policy(MockPolicy("pol1"))
        registry.register_policy(MockPolicy("pol2"))
        assert len(registry.list_policies()) == 2

    def test_list_plugins(self, registry):
        registry.register_plugin(MockPlugin("plug1"))
        registry.register_plugin(MockPlugin("plug2"))
        assert len(registry.list_plugins()) == 2

    def test_list_registered_empty(self, registry):
        summary = registry.list_registered()
        assert summary["detectors"] == []
        assert summary["providers"] == []
        assert summary["strategies"] == []
        assert summary["policies"] == []
        assert summary["plugins"] == []
        assert summary["metrics"] is None

    def test_list_registered_populated(self, registry):
        registry.register_detector(MockDetector("d1"))
        registry.register_provider(MockProvider("p1"))
        registry.register_strategy(MockStrategy("s1"))
        registry.register_policy(MockPolicy("pol1"))
        registry.register_plugin(MockPlugin("plug1"))
        registry.set_metrics(MockMetrics())

        summary = registry.list_registered()
        assert summary["detectors"] == ["d1"]
        assert summary["providers"] == ["p1"]
        assert summary["strategies"] == ["s1"]
        assert summary["policies"] == ["pol1"]
        assert summary["plugins"] == ["plug1"]
        assert summary["metrics"] == "set"


class TestRegistryLifecycle:
    """initialize_all and shutdown_all lifecycle."""

    async def test_initialize_all_plugins(self, registry):
        p1 = MockPlugin("p1")
        p2 = MockPlugin("p2")
        registry.register_plugin(p1)
        registry.register_plugin(p2)
        await registry.initialize_all()
        assert p1.initialized is True
        assert p2.initialized is True

    async def test_initialize_detector_plugin_subclasses(self, registry):
        """Detectors that are Plugin subclasses get initialized."""
        p = MockPlugin("detector_plugin")
        # Re-register as a detector (treat it as a Plugin subclass detector)
        registry.register_detector(p)
        await registry.initialize_all()
        assert p.initialized is True

    async def test_initialize_metrics(self, registry):
        m = MockMetrics()
        registry.set_metrics(m)
        await registry.initialize_all()
        assert m.initialized is True

    async def test_initialize_failure_aggregates_errors(self, registry):
        registry.register_plugin(MockFailingPlugin("fail"))
        registry.register_plugin(MockPlugin("good"))
        with pytest.raises(PluginRegistryError):
            await registry.initialize_all()

    async def test_initialize_good_plugin_still_runs_when_another_fails(self, registry):
        """A failing plugin doesn't stop others from being initialized."""
        fail = MockFailingPlugin("fail")
        good = MockPlugin("good")
        registry.register_plugin(fail)
        registry.register_plugin(good)

        with pytest.raises(PluginRegistryError):
            await registry.initialize_all()

        assert good.initialized is True

    async def test_shutdown_all_plugins(self, registry):
        p1 = MockPlugin("p1")
        p2 = MockPlugin("p2")
        registry.register_plugin(p1)
        registry.register_plugin(p2)
        await registry.shutdown_all()
        assert p1.shutdown_called is True
        assert p2.shutdown_called is True

    async def test_shutdown_metrics(self, registry):
        m = MockMetrics()
        registry.set_metrics(m)
        await registry.shutdown_all()
        assert m.shutdown_called is True

    async def test_shutdown_without_initialize_does_not_raise(self, registry):
        await registry.shutdown_all()

    async def test_initialize_empty_registry(self, registry):
        await registry.initialize_all()  # should not raise


class TestRegistryErrorHierarchy:
    """Error type hierarchy."""

    def test_duplicate_is_subclass_of_registry_error(self):
        assert issubclass(DuplicatePluginError, PluginRegistryError)

    def test_not_found_is_subclass_of_registry_error(self):
        assert issubclass(PluginNotFoundError, PluginRegistryError)

    def test_duplicate_error_message(self):
        d = MockDetector("dup")
        registry = PluginRegistry()
        registry.register_detector(d)
        with pytest.raises(DuplicatePluginError) as excinfo:
            registry.register_detector(MockDetector("dup"))
        assert "already registered" in str(excinfo.value)
        assert "detector 'dup'" in str(excinfo.value)


class TestRegistryEdgeCases:
    """Edge cases for the registry."""

    def test_register_multiple_same_type(self, registry):
        registry.register_detector(MockDetector("d1"))
        registry.register_detector(MockDetector("d2"))
        registry.register_provider(MockProvider("p1"))
        registry.register_strategy(MockStrategy("s1"))
        assert len(registry.list_detectors()) == 2
        assert len(registry.list_providers()) == 1
        assert len(registry.list_strategies()) == 1

    def test_names_are_case_sensitive(self, registry):
        """Registry keys are case-sensitive."""
        registry.register_detector(MockDetector("Detector"))
        registry.register_detector(MockDetector("detector"))
        assert len(registry.list_detectors()) == 2

    def test_unregister_not_supported(self, registry):
        """No built-in unregistration method exists — the dict is the only source of truth."""
        d = MockDetector("permanent")
        registry.register_detector(d)
        assert registry.get_detector_or_none("permanent") is d