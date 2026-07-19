"""Test the max(raw, pipeline) merge logic — pipeline_mode UNION behavior."""
from __future__ import annotations

import pytest

from piifilter.config import FilterConfig, DetectionConfig
from piifilter.shared.models import DetectedEntity, EntityType
from piifilter.pipeline import _entity_detector, _entity_span


class TestMaxMergeHelpers:
    """Verify the module-level helper functions work for both dict and object shapes."""

    def test_entity_detector_from_dict(self):
        e = {"entity_type": "EMAIL", "start": 0, "end": 10, "detector": "regex", "score": 0.9}
        assert _entity_detector(e) == "regex"

    def test_entity_detector_from_object(self):
        e = DetectedEntity(
            entity_type=EntityType.EMAIL, value="test@x.com",
            start=0, end=10, confidence=0.9, detector="regex",
        )
        assert _entity_detector(e) == "regex"

    def test_entity_detector_unknown(self):
        e = {"entity_type": "EMAIL", "start": 0, "end": 10}
        assert _entity_detector(e) == ""

    def test_entity_span_from_dict(self):
        e = {"entity_type": "EMAIL", "start": 5, "end": 20, "detector": "regex", "score": 0.9}
        assert _entity_span(e) == (5, 20, "EMAIL")

    def test_entity_span_from_object(self):
        e = DetectedEntity(
            entity_type=EntityType.EMAIL, value="test@x.com",
            start=5, end=20, confidence=0.9, detector="regex",
        )
        assert _entity_span(e) == (5, 20, "EMAIL")


class TestPipelineModeConfig:
    """Verify the pipeline_mode config field behaves correctly."""

    def test_default_is_true(self):
        cfg = FilterConfig()
        assert cfg.detection.pipeline_mode is True

    def test_can_set_false(self):
        cfg = FilterConfig(detection=DetectionConfig(pipeline_mode=False))
        assert cfg.detection.pipeline_mode is False

    def test_roundtrip_via_yaml(self, tmp_path):
        cfg = FilterConfig(detection=DetectionConfig(pipeline_mode=False))
        path = tmp_path / "test_config.yaml"
        cfg.to_yaml(str(path))
        loaded = FilterConfig.from_yaml(str(path))
        assert loaded.detection.pipeline_mode is False

    def test_pipeline_mode_persists_after_yaml_roundtrip_true(self, tmp_path):
        cfg = FilterConfig()  # default True
        path = tmp_path / "test_config2.yaml"
        cfg.to_yaml(str(path))
        loaded = FilterConfig.from_yaml(str(path))
        assert loaded.detection.pipeline_mode is True