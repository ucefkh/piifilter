"""Tests for the telemetry module — counters, histograms, transforms, latency, canary."""

from __future__ import annotations

import pytest

from piifilter.telemetry import _Telemetry, _bucket_label, CONFIDENCE_BUCKETS, CANARY_EXAMPLES


@pytest.fixture(autouse=True)
def fresh_telemetry():
    """Return a fresh _Telemetry instance for each test (no cross-test contamination)."""
    t = _Telemetry()
    yield t


# ── Bucket labelling ──────────────────────────────────────────────────────────


class TestBucketLabel:
    def test_below_point_five(self):
        assert _bucket_label(0.0) == "<0.5"
        assert _bucket_label(0.49) == "<0.5"

    def test_mid_buckets(self):
        assert _bucket_label(0.5) == "0.5-0.7"
        assert _bucket_label(0.69) == "0.5-0.7"
        assert _bucket_label(0.7) == "0.7-0.85"
        assert _bucket_label(0.84) == "0.7-0.85"
        assert _bucket_label(0.85) == "0.85-0.95"
        assert _bucket_label(0.94) == "0.85-0.95"

    def test_top_bucket(self):
        assert _bucket_label(0.95) == "0.95+"
        assert _bucket_label(1.0) == "0.95+"


# ── Thread-safe singleton — counters ─────────────────────────────────────────


class TestCounters:
    def test_call_count_increments(self, fresh_telemetry):
        t = fresh_telemetry
        assert t.get_stats()["call_count"] == 0
        t.record(elapsed=0.01, detections=[], transforms=[])
        assert t.get_stats()["call_count"] == 1

    def test_per_type_detection_counts(self, fresh_telemetry):
        t = fresh_telemetry
        detections = [
            {"type": "EMAIL", "score": 0.9},
            {"type": "EMAIL", "score": 0.9},
            {"type": "SSN", "score": 0.95},
        ]
        t.record(elapsed=0.01, detections=detections, transforms=[])
        stats = t.get_stats()
        assert stats["per_type"]["EMAIL"] == 2
        assert stats["per_type"]["SSN"] == 1
        assert "PERSON" not in stats["per_type"]

    def test_multiple_types_in_one_call(self, fresh_telemetry):
        t = fresh_telemetry
        detections = [
            {"type": "EMAIL", "score": 0.9},
            {"type": "CREDIT_CARD", "score": 0.95},
            {"type": "PHONE", "score": 0.85},
        ]
        t.record(elapsed=0.02, detections=detections, transforms=[])
        stats = t.get_stats()
        assert stats["per_type"]["EMAIL"] == 1
        assert stats["per_type"]["CREDIT_CARD"] == 1
        assert stats["per_type"]["PHONE"] == 1
        # Verify snapshot resets after get_stats
        assert t.get_stats()["call_count"] == 0


# ── Confidence histogram ──────────────────────────────────────────────────────


class TestConfidenceHistogram:
    def test_histogram_buckets(self, fresh_telemetry):
        t = fresh_telemetry
        detections = [
            {"type": "PERSON", "score": 0.4},
            {"type": "EMAIL", "score": 0.6},
            {"type": "PHONE", "score": 0.7},
            {"type": "SSN", "score": 0.9},
            {"type": "JWT", "score": 0.95},
        ]
        t.record(elapsed=0.01, detections=detections, transforms=[])
        stats = t.get_stats()
        h = stats["confidence_histogram"]
        assert h.get("<0.5") == 1
        assert h.get("0.5-0.7") == 1
        assert h.get("0.7-0.85") == 1
        assert h.get("0.85-0.95") == 1
        assert h.get("0.95+") == 1

    def test_empty_histogram(self, fresh_telemetry):
        t = fresh_telemetry
        t.record(elapsed=0.01, detections=[], transforms=[])
        stats = t.get_stats()
        assert stats["confidence_histogram"] == {}


# ── Transform activation ──────────────────────────────────────────────────────


class TestTransforms:
    def test_transform_counts(self, fresh_telemetry):
        t = fresh_telemetry
        transforms = [
            {"transform": "NFKC", "changed": True},
            {"transform": "at_dot", "changed": True},
            {"transform": "html_entities", "changed": False},
            {"transform": "NFKC", "changed": True},
        ]
        t.record(elapsed=0.01, detections=[], transforms=transforms)
        stats = t.get_stats()
        assert stats["transform_activations"]["NFKC"] == 2
        assert stats["transform_activations"]["at_dot"] == 1
        assert "html_entities" not in stats["transform_activations"]

    def test_no_transforms_fired(self, fresh_telemetry):
        t = fresh_telemetry
        transforms = [
            {"transform": "NFKC", "changed": False},
            {"transform": "at_dot", "changed": False},
        ]
        t.record(elapsed=0.01, detections=[], transforms=transforms)
        stats = t.get_stats()
        assert stats["transform_activations"] == {}


# ── Latency ────────────────────────────────────────────────────────────────────


class TestLatency:
    def test_latency_accumulation(self, fresh_telemetry):
        t = fresh_telemetry
        t.record(elapsed=0.1, detections=[], transforms=[])
        t.record(elapsed=0.2, detections=[], transforms=[])
        stats = t.get_stats()
        assert stats["latency"]["count"] == 2
        assert stats["latency"]["total"] == pytest.approx(0.3)
        assert stats["latency"]["mean"] == pytest.approx(0.15)
        assert stats["latency"]["min"] == pytest.approx(0.1)
        assert stats["latency"]["max"] == pytest.approx(0.2)

    def test_single_call_latency(self, fresh_telemetry):
        t = fresh_telemetry
        t.record(elapsed=0.05, detections=[], transforms=[])
        stats = t.get_stats()
        assert stats["latency"]["count"] == 1
        assert stats["latency"]["min"] == stats["latency"]["max"]

    def test_latency_when_no_calls(self, fresh_telemetry):
        t = fresh_telemetry
        stats = t.get_stats()
        assert stats["latency"]["count"] == 0
        assert stats["latency"]["mean"] == 0.0
        assert stats["latency"]["min"] == 0.0


# ── get_stats() snapshot and reset ──────────────────────────────────────────────


class TestSnapshotReset:
    def test_snapshot_resets_counters(self, fresh_telemetry):
        t = fresh_telemetry
        t.record(elapsed=0.01, detections=[{"type": "EMAIL", "score": 0.9}], transforms=[])
        s1 = t.get_stats()
        assert s1["call_count"] == 1

        s2 = t.get_stats()
        assert s2["call_count"] == 0
        assert s2["per_type"] == {}
        assert s2["latency"]["count"] == 0

    def test_snapshot_is_independent(self, fresh_telemetry):
        t = fresh_telemetry
        t.record(elapsed=0.01, detections=[{"type": "EMAIL", "score": 0.9}], transforms=[])
        stats = t.get_stats()
        # Modify the returned dict — should NOT affect internal state
        stats["per_type"]["EMAIL"] = 999
        stats2 = t.get_stats()
        # Internal state was reset by the first get_stats(), so EMAIL is gone
        assert "EMAIL" not in stats2["per_type"]
        # But the EMAIL value we injected should still be in our copy
        assert stats["per_type"]["EMAIL"] == 999


# ── get_stats() module-level convenience ─────────────────────────────────────────


class TestModuleLevel:
    def test_module_level_get_stats_exists(self):
        from piifilter.telemetry import get_stats as gs

        stats = gs()
        # Should return a dict without raising
        assert isinstance(stats, dict)

    def test_module_level_telemetry_instance(self):
        from piifilter.telemetry import telemetry

        assert hasattr(telemetry, "record")
        assert hasattr(telemetry, "get_stats")


# ── Canary examples exist and are well-formed ────────────────────────────────────


class TestCanaryExamples:
    def test_canary_labels_are_unique(self):
        labels = [label for label, _ in CANARY_EXAMPLES]
        assert len(labels) == len(set(labels))

    def test_canary_strings_nonempty(self):
        for label, pii_str in CANARY_EXAMPLES:
            assert len(pii_str) > 0, f"Canary '{label}' has empty PII string"

    def test_canary_alerts_accumulate(self, fresh_telemetry):
        t = fresh_telemetry
        assert len(t.get_stats()["canary_alerts"]) == 0
        t.canary_check_failed("email", "Did not detect alice@acme.com")
        t.canary_check_failed("ssn", "Did not detect 123-45-6789")
        stats = t.get_stats()
        assert len(stats["canary_alerts"]) == 2
        assert stats["canary_alerts"][0]["label"] == "email"
        assert stats["canary_alerts"][1]["label"] == "ssn"

    def test_canary_interval_settable(self, fresh_telemetry):
        t = fresh_telemetry
        assert t.get_stats()["canary_interval"] == 100
        t.set_canary_interval(50)
        assert t.get_stats()["canary_interval"] == 50


# ── Thread safety (basic) ─────────────────────────────────────────────────────


class TestThreadSafety:
    def test_concurrent_record_no_crash(self, fresh_telemetry):
        t = fresh_telemetry
        import threading

        errors = []

        def worker(n: int):
            try:
                for _ in range(100):
                    t.record(
                        elapsed=0.01,
                        detections=[{"type": "EMAIL", "score": 0.9}] if n % 2 == 0 else [],
                        transforms=[{"transform": "NFKC", "changed": True}] if n % 3 == 0 else [],
                    )
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
        for th in threads:
            th.start()
        for th in threads:
            th.join()

        assert not errors, f"Thread safety errors: {errors}"
        stats = t.get_stats()
        # 10 threads × 100 calls = 1000
        assert stats["call_count"] == 1000