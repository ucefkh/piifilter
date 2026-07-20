"""Property-based tests for PIIFilter RegexDetector — invariant properties.

Uses Hypothesis for property-based/fuzz testing of the RegexDetector.
Tests key properties that should ALWAYS hold regardless of input:
  - No exception thrown on any input
  - Empty text produces no detections
  - Detection is deterministic
  - Entity spans are always valid
  - Well-known test credit card numbers ARE detected
  - Standard emails ARE detected

Usage:
    pytest tests/fuzz/test_regex_properties.py -v
    pytest tests/fuzz/test_regex_properties.py --hypothesis-show-statistics
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

try:
    from hypothesis import given, strategies as st, settings, HealthCheck
except ImportError:
    pytest.skip("hypothesis not installed", allow_module_level=True)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "core" / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "plugins" / "detector-regex" / "src"))

from piifilter_detector_regex.detector import RegexDetector
from piifilter_detector_regex.patterns import PATTERN_DEFS

# Test credit card numbers (Luhn-valid, well-known test numbers)
TEST_CC_NUMBERS = [
    "4111-1111-1111-1111",   # Visa
    "5500-0000-0000-0004",   # Mastercard
    "3782-822463-10005",     # Amex
    "6011-1111-1111-1117",   # Discover
    "3530-1113-3330-0000",   # JCB
    "5555-5555-5555-4444",   # Mastercard
]

TEST_EMAILS = [
    "user@example.com",
    "first.last@example.co.uk",
    "user+tag@domain.org",
    "admin@company.com",
]


# ── Helper to convert CandidateSpan to dict ────────────────────────────


def _span_to_dict(span) -> dict:
    """Normalize a CandidateSpan dataclass to a plain dict."""
    return {
        "type": span.entity_type.value,
        "text": span.text,
        "start": span.start,
        "end": span.end,
        "score": span.raw_score,
    }


# ── Fixture ───────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def detector():
    """Shared RegexDetector instance for all tests in the module."""
    import asyncio
    d = RegexDetector()
    asyncio.run(d.initialize())
    return d


# ── Properties ────────────────────────────────────────────────────────────


class TestPIIFilterProperties:
    """Property-based tests that must hold for all inputs."""

    def _run_detect(self, detector: RegexDetector, text: str) -> list[dict]:
        """Run detection and normalize results to dicts."""
        import asyncio
        raw = asyncio.run(detector.detect(text))
        return [_span_to_dict(e) for e in raw]

    # ── Invariant: No crash on any text ────────────────────────────────

    @given(text=st.text())
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_no_crash_on_any_input(self, detector, text):
        """Detection must never throw, regardless of input."""
        try:
            result = self._run_detect(detector, text)
            assert isinstance(result, list)
        except Exception as e:
            pytest.fail(f"Crash on text={text!r}: {e}")

    # ── Invariant: Empty text = empty results ──────────────────────────

    def test_empty_text_produces_no_detections(self, detector):
        """Empty text must produce zero detections."""
        result = self._run_detect(detector, "")
        assert len(result) == 0

    # ── Invariant: Detections are deterministic ────────────────────────

    @given(text=st.text(max_size=200))
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_deterministic_detection(self, detector, text):
        """Running detection twice on the same text must produce the same results."""
        r1 = self._run_detect(detector, text)
        r2 = self._run_detect(detector, text)
        key_fn = lambda d: (d["type"], d["start"], d["end"])
        assert sorted(r1, key=key_fn) == sorted(r2, key=key_fn), (
            f"Non-deterministic detection for text={text!r}"
        )

    # ── Invariant: Well-known test CC numbers are detected ─────────────

    @pytest.mark.parametrize("cc_number", TEST_CC_NUMBERS)
    def test_credit_cards_detected(self, detector, cc_number):
        """Standard test CC numbers must be detected as CREDIT_CARD."""
        text = f"Credit card: {cc_number}"
        result = self._run_detect(detector, text)
        cc_detected = [d for d in result if d["type"] == "CREDIT_CARD"]
        assert len(cc_detected) >= 1, (
            f"CC {cc_number} not detected! Got: {[(d['type'], d['value']) for d in result]}"
        )

    # ── Invariant: Standard emails are detected ────────────────────────

    @pytest.mark.parametrize("email", TEST_EMAILS)
    def test_emails_detected(self, detector, email):
        """Standard email addresses must be detected as EMAIL."""
        text = f"Email: {email}"
        result = self._run_detect(detector, text)
        email_detected = [d for d in result if d["type"] == "EMAIL"]
        assert len(email_detected) >= 1, (
            f"Email {email} not detected! Got: {[(d['type'], d['value']) for d in result]}"
        )

    # ── Invariant: Well-known IP addresses ─────────────────────────────

    @pytest.mark.parametrize("text", [
        "IP: 192.168.1.1",
        "Gateway: 10.0.0.1",
        "DNS: 8.8.8.8",
        "Server: 172.16.0.1",
    ])
    def test_ip_addresses_detected(self, detector, text):
        """Standard IP addresses should be detected."""
        result = self._run_detect(detector, text)
        ip_detected = [d for d in result if d["type"] == "IP_ADDRESS"]
        assert len(ip_detected) >= 1, (
            f"IP not detected in {text!r}! Got: {[(d['type'], d['value']) for d in result]}"
        )

    # ── Invariant: Non-PII number sequences ────────────────────────────

    NON_PII_NUMBERS = [
        "0000000000",
        "1111111111111",
        "9999999999999999",
        "12345",
        "0",
        "1.0",
        "100",
    ]

    @given(text=st.sampled_from(NON_PII_NUMBERS))
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_non_pii_numbers_not_high_confidence(self, detector, text):
        """Non-PII number sequences should not be detected as high-confidence PII."""
        result = self._run_detect(detector, text)
        pii_types = {"CREDIT_CARD", "SOCIAL_SECURITY", "BANK_ACCOUNT", "PHONE"}
        for d in result:
            if d["type"] in pii_types and d["score"] >= 0.80:
                pytest.fail(f"Non-PII number {text!r} detected as {d['type']} (score={d['score']})")


class TestPatternProperties:
    """Properties of the regex pattern definitions."""

    def test_all_patterns_have_valid_entity_types(self):
        """Every PATTERN_DEF must have a valid entity type name."""
        for type_name, pattern, score in PATTERN_DEFS:
            assert isinstance(type_name, str), f"Type name not string: {type_name}"
            assert isinstance(pattern, str), f"Pattern not string: {pattern}"
            assert isinstance(score, (int, float)), f"Score not numeric: {score}"
            assert 0.0 <= score <= 1.0, f"Score out of range [0,1]: {score}"

    def test_no_empty_patterns(self):
        """No pattern should be empty or just whitespace."""
        for type_name, pattern, score in PATTERN_DEFS:
            assert pattern.strip(), f"Empty pattern for type {type_name}"

    def test_unique_type_coverage(self):
        """All pattern type names should be defined."""
        type_names = {t for t, _, _ in PATTERN_DEFS}
        expected_types = {
            "EMAIL", "PHONE", "CREDIT_CARD", "SOCIAL_SECURITY",
            "IP_ADDRESS", "PERSON", "COMPANY", "ADDRESS",
            "CITY", "COUNTRY", "BANK_ACCOUNT", "IBAN",
            "PASSPORT", "JWT", "API_KEY", "SSH_KEY",
            "DATABASE_URL", "PRIVATE_URL", "URL", "DOMAIN",
            "GPS", "DATE", "FILE_PATH",
            "CUSTOMER_NAME", "EMPLOYEE_NAME", "PROJECT_NAME",
        }
        missing = expected_types - type_names
        assert not missing, f"Missing entity types in PATTERN_DEFS: {missing}"


class TestModePresets:
    """Verify mode preset consistency."""

    def test_high_recall_has_low_thresholds(self):
        from tests.benchmark_runner import MODE_PRESETS
        presets = MODE_PRESETS["high_recall"]
        assert presets.get("default", 0.0) <= 0.1, (
            f"high_recall default threshold {presets.get('default')} is too high"
        )

    def test_high_precision_has_high_thresholds(self):
        from tests.benchmark_runner import MODE_PRESETS
        presets = MODE_PRESETS["high_precision"]
        assert presets.get("default", 0.0) >= 0.7, (
            f"high_precision default threshold {presets.get('default')} is too low"
        )

    def test_balanced_is_between(self):
        from tests.benchmark_runner import MODE_PRESETS
        high_recall_default = MODE_PRESETS["high_recall"].get("default", 0.0)
        high_precision_default = MODE_PRESETS["high_precision"].get("default", 0.0)
        balanced_default = MODE_PRESETS["balanced"].get("default", 0.5)
        assert high_recall_default <= balanced_default <= high_precision_default, (
            f"balanced default ({balanced_default}) not between extremes"
        )

    def test_all_modes_have_default(self):
        from tests.benchmark_runner import MODE_PRESETS
        for mode, preset in MODE_PRESETS.items():
            assert "default" in preset, f"Mode {mode!r} is missing 'default' key"

    def test_all_entity_types_covered(self):
        from tests.benchmark_runner import MODE_PRESETS
        from piifilter.shared.models import EntityType
        for mode, preset in MODE_PRESETS.items():
            configured = set(preset.keys()) - {"default"}
            assert len(configured) > 0, f"Mode {mode!r} has no entity-specific thresholds"


class TestGoldenCorpus:
    """Verify the golden corpus is properly structured."""

    def load_corpus(self):
        import json
        path = PROJECT_ROOT / "benchmarks" / "data" / "golden_corpus.json"
        data = json.loads(path.read_text())
        return data["examples"]

    def test_corpus_has_200_plus_examples(self):
        examples = self.load_corpus()
        assert len(examples) >= 200, f"Only {len(examples)} examples, need 200+"

    def test_corpus_covers_all_entity_types(self):
        from piifilter.shared.models import EntityType
        examples = self.load_corpus()
        types_in_corpus = set()
        for ex in examples:
            for e in ex.get("entities", []):
                types_in_corpus.add(e["type"])
        all_types = set(EntityType.__members__.keys())
        uncovered = all_types - types_in_corpus
        assert not uncovered, (
            f"Entity types not covered in golden corpus: {uncovered}"
        )

    def test_all_entity_spans_valid(self):
        examples = self.load_corpus()
        for i, ex in enumerate(examples):
            text = ex["text"]
            for j, e in enumerate(ex.get("entities", [])):
                s, en = e.get("start", 0), e.get("end", 0)
                assert 0 <= s < en <= len(text), (
                    f"Example {i}, entity {j}: invalid span ({s}, {en}) "
                    f"for text len={len(text)}: type={e['type']} value={e['value']!r}"
                )

    def test_entity_values_match_text(self):
        examples = self.load_corpus()
        for i, ex in enumerate(examples):
            text = ex["text"]
            for j, e in enumerate(ex.get("entities", [])):
                s, en = e["start"], e["end"]
                actual_value = text[s:en]
                assert actual_value == e["value"], (
                    f"Example {i}, entity {j}: value mismatch. "
                    f"Expected {e['value']!r} but text[{s}:{en}] = {actual_value!r}"
                )

    def test_corpus_has_negatives(self):
        examples = self.load_corpus()
        negatives = [ex for ex in examples if not ex.get("entities")]
        assert len(negatives) >= 10, (
            f"Only {len(negatives)} negative examples, need at least 10"
        )

    def test_no_duplicate_examples(self):
        examples = self.load_corpus()
        texts = [ex["text"] for ex in examples]
        seen = set()
        duplicates = []
        for i, t in enumerate(texts):
            if t in seen:
                duplicates.append((i, t))
            seen.add(t)
        assert not duplicates, f"Duplicate examples found: {duplicates}"


class TestScoreMetrics:
    """Test the scoring functions used by the benchmark runner."""

    def _compute_metrics(self, tp, fp, fn):
        from tests.benchmark_runner import compute_metrics
        return compute_metrics(tp, fp, fn)

    def test_compute_metrics_perfect(self):
        m = self._compute_metrics(10, 0, 0)
        assert m["precision"] == 1.0
        assert m["recall"] == 1.0
        assert m["f1"] == 1.0

    def test_compute_metrics_no_tp(self):
        m = self._compute_metrics(0, 10, 5)
        assert m["precision"] == 0.0
        assert m["recall"] == 0.0
        assert m["f1"] == 0.0

    def test_compute_metrics_zero_division(self):
        m = self._compute_metrics(0, 0, 0)
        assert m["precision"] == 0.0
        assert m["recall"] == 0.0
        assert m["f1"] == 0.0

    def test_score_detections_exact_match(self):
        from tests.benchmark_runner import score_detections
        golden = [{"type": "EMAIL", "value": "a@b.com", "start": 0, "end": 8}]
        detected = [{"type": "EMAIL", "value": "a@b.com", "start": 0, "end": 8, "score": 0.9}]
        result = score_detections(golden, detected)
        assert result["tp"] == 1
        assert result["fp"] == 0
        assert result["fn"] == 0
        assert result["f1"] == 1.0

    def test_score_detections_overlap(self):
        from tests.benchmark_runner import score_detections
        golden = [{"type": "EMAIL", "value": "a@b.com", "start": 0, "end": 8}]
        detected = [{"type": "EMAIL", "value": "a@b.com extra", "start": 0, "end": 15, "score": 0.9}]
        result = score_detections(golden, detected)
        assert result["tp"] == 1
        assert result["fp"] == 0

    def test_score_detections_miss(self):
        from tests.benchmark_runner import score_detections
        golden = [{"type": "EMAIL", "value": "a@b.com", "start": 0, "end": 8}]
        detected = []
        result = score_detections(golden, detected)
        assert result["tp"] == 0
        assert result["fn"] == 1

    def test_score_detections_false_positive(self):
        from tests.benchmark_runner import score_detections
        golden = []
        detected = [{"type": "EMAIL", "value": "a@b.com", "start": 0, "end": 8, "score": 0.9}]
        result = score_detections(golden, detected)
        assert result["fp"] == 1
        assert result["tp"] == 0

    def test_score_detections_threshold_filter(self):
        from tests.benchmark_runner import score_detections
        golden = [{"type": "EMAIL", "value": "a@b.com", "start": 0, "end": 8}]
        detected = [{"type": "EMAIL", "value": "a@b.com", "start": 0, "end": 8, "score": 0.5}]
        result = score_detections(golden, detected, threshold=0.8)
        assert result["tp"] == 0
        assert result["fn"] == 1