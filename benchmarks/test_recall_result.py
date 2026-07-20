"""Tests for RecallResult metrics — ensuring F1 is arithmetically sound."""
from __future__ import annotations

from benchmarks.recall import RecallResult


def test_f1_harmonic_mean_between_p_and_r() -> None:
    """F1 is a harmonic mean of precision and recall, so it must lie between them."""
    r = RecallResult(entity_type="TEST_1", true_positives=45, false_positives=7, false_negatives=4)
    p = r.precision
    rec = r.recall
    f1 = r.f1
    # Harmonic mean always sits between the two values (or equals them when p == r)
    assert min(p, rec) <= f1 <= max(p, rec), (
        f"F1={f1:.4f} must lie between P={p:.4f} and R={rec:.4f}"
    )


def test_f1_known_values() -> None:
    """Smoke test: F1 for known TP/FP/FN values matches expected."""
    # TP=9, FP=2, FN=1  →  P=9/11≈0.8182, R=9/10=0.9  →  F1≈0.8571
    r = RecallResult(entity_type="IP_ADDRESS", true_positives=9, false_positives=2, false_negatives=1)
    assert abs(r.precision - 9 / 11) < 1e-10
    assert r.recall == 0.9
    # 2*0.8182*0.9 / (0.8182+0.9) = 1.4727/1.7182 = 0.8571
    expected_f1 = 2 * (9 / 11) * 0.9 / ((9 / 11) + 0.9)
    assert abs(r.f1 - expected_f1) < 1e-6, f"F1={r.f1} != expected={expected_f1:.6f}"
    assert abs(r.f1 - 0.85714286) < 1e-4, f"F1={r.f1} != 0.8571"


def test_f1_with_precision_equals_recall() -> None:
    """When P == R, F1 must equal P (=R)."""
    r = RecallResult(entity_type="TEST_EQ", true_positives=8, false_positives=2, false_negatives=2)
    assert r.precision == 0.8
    assert r.recall == 0.8
    assert abs(r.f1 - 0.8) < 1e-12, f"F1={r.f1} should be ~0.8 when P=R=0.8"


def test_f1_perfect_scores() -> None:
    """Perfect precision and recall should give F1 = 1.0."""
    r = RecallResult(entity_type="PERFECT", true_positives=50, false_positives=0, false_negatives=0)
    assert r.precision == 1.0
    assert r.recall == 1.0
    assert r.f1 == 1.0


def test_f1_zero_division() -> None:
    """F1 should be 0.0 when p+r == 0."""
    r = RecallResult(entity_type="ZERO", true_positives=0, false_positives=0, false_negatives=0)
    assert r.f1 == 0.0

    r2 = RecallResult(entity_type="ZERO_P", true_positives=0, false_positives=5, false_negatives=5)
    assert r2.f1 == 0.0


def test_f1_arithmetic_impossibility_guard() -> None:
    """Regression: F1 must never exceed the larger of P and R."""
    # Prior bug double-counted TP, inflating both P and R and breaking the
    # harmonic-mean invariant.  This test catches any regression.
    r = RecallResult(entity_type="IP_ADDRESS", true_positives=9, false_positives=1, false_negatives=1)
    p = r.precision  # 9/10 = 0.9
    rec = r.recall    # 9/10 = 0.9
    f1 = r.f1         # must be 0.9
    assert 0 <= f1 <= max(p, rec), f"F1={f1:.4f} exceeds bounds [0, {max(p, rec):.4f}]"

    # The reported impossible case: P=0.8654, R=0.9231 → F1 must be ~0.893, not 0.9615
    r2 = RecallResult(entity_type="IP_ADDRESS", true_positives=865, false_positives=135, false_negatives=77)
    assert abs(r2.precision - 0.865) < 0.001
    assert abs(r2.recall - 0.918) < 0.001  # 865/(865+77) = 0.918
    f1_check = r2.f1
    assert f1_check < max(r2.precision, r2.recall), (
        f"F1={f1_check:.4f} must be < max(P={r2.precision:.4f}, R={r2.recall:.4f})"
    )