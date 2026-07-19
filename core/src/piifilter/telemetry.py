"""PIIFilter telemetry — per-type detection counts, confidence histograms,
transform activation, per-call latency, and canary health checks.

Thread-safe singleton pattern with a dict accumulator.  Import the module-level
``telemetry`` instance and call ``telemetry.record(...)`` after each ``detect()``.

Call ``get_stats()`` to retrieve a snapshot and atomically reset the counters.
"""

from __future__ import annotations

import threading
import time
from collections import Counter
from typing import Any

# ── Confidence histogram buckets ──────────────────────────────────────────────

CONFIDENCE_BUCKETS: list[tuple[float, float, str]] = [
    (0.0, 0.5, "<0.5"),
    (0.5, 0.7, "0.5-0.7"),
    (0.7, 0.85, "0.7-0.85"),
    (0.85, 0.95, "0.85-0.95"),
    (0.95, 1.01, "0.95+"),
]


def _bucket_label(confidence: float) -> str:
    """Return the bucket label for a confidence value."""
    for lo, hi, label in CONFIDENCE_BUCKETS:
        if lo <= confidence < hi:
            return label
    return "0.95+"  # fallback for exactly 1.0


# ── Known PII strings for the canary check ────────────────────────────────────

CANARY_EXAMPLES: list[tuple[str, str]] = [
    # (label, PII string that the regex detector should find)
    ("email", "alice@acme.com"),
    ("ssn", "123-45-6789"),
    ("credit_card", "4111 1111 1111 1111"),
    ("phone", "+1 (555) 123-4567"),
    ("ipv4", "192.168.1.1"),
    ("jwt", "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVonUG-tPk1234567890abc"),
    ("api_key", "sk-abc123def456ghi789jkl012"),
    ("iban", "GB29 NWBK 6016 1331 9268 19"),
    ("passport", "AB1234567"),
    ("database_url", "postgresql://user:pass@localhost:5432/mydb"),
]


class _Telemetry:
    """Thread-safe singleton telemetry accumulator.

    Thread safety is provided by a ``threading.Lock``.  Every public method
    acquires the lock to guarantee visibility across producer (detect) and
    consumer (get_stats).
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._reset()

    # ── Public API ─────────────────────────────────────────────────────────

    def record(
        self,
        *,
        elapsed: float,
        detections: list[dict[str, Any]],
        transforms: list[dict[str, Any]],
    ) -> None:
        """Record telemetry for one ``detect()`` call.

        Parameters
        ----------
        elapsed:
            Wall-clock time in seconds the detection took.
        detections:
            The list of detection dicts returned by ``detect()``.
            Each dict should have ``"type"`` and ``"score"`` keys.
        transforms:
            The deobfuscator transform log — a list of dicts each with at
            least a ``"transform"`` key.
        """
        with self._lock:
            self._call_count += 1

            # Per-type detection counts
            seen_types: set[str] = set()
            for d in detections:
                pii_type = d.get("type", "UNKNOWN")
                score = d.get("score", 0.0)
                self._per_type[pii_type] += 1
                seen_types.add(pii_type)
                # Confidence histogram
                label = _bucket_label(score)
                self._confidence_histogram[label] += 1

            # Transform activation (which transforms fired)
            for t in transforms:
                if t.get("changed"):
                    name = t.get("transform", "unknown")
                    self._transform_activations[name] += 1

            # Per-call latency
            self._latency_total += elapsed
            self._latency_count += 1
            if elapsed < self._latency_min:
                self._latency_min = elapsed
            if elapsed > self._latency_max:
                self._latency_max = elapsed
            self._latencies.append(elapsed)

            # Canary check — run every N calls
            self._calls_since_canary += 1
            if self._calls_since_canary >= self._canary_interval:
                self._calls_since_canary = 0

    def canary_check_failed(self, label: str, detail: str) -> None:
        """Record a canary detection failure."""
        with self._lock:
            self._canary_alerts.append({"label": label, "detail": detail})

    def set_canary_interval(self, n: int) -> None:
        """Set how many ``detect()`` calls between canary runs."""
        with self._lock:
            self._canary_interval = n

    # ── Snapshot ───────────────────────────────────────────────────────────

    def get_stats(self) -> dict[str, Any]:
        """Return an atomic snapshot of all counters and reset them.

        Returns a dict with:

        - ``call_count``
        - ``per_type``: dict of PII type → count
        - ``confidence_histogram``: dict of bucket label → count
        - ``transform_activations``: dict of transform name → count
        - ``latency``: dict with mean, min, max, total, count
        - ``canary_alerts``: list of alert dicts
        - ``calls_since_canary``: how many calls since last canary check
        """
        with self._lock:
            snapshot = {
                "call_count": self._call_count,
                "per_type": dict(self._per_type),
                "confidence_histogram": dict(self._confidence_histogram),
                "transform_activations": dict(self._transform_activations),
                "latency": {
                    "mean": self._latency_total / self._latency_count if self._latency_count else 0.0,
                    "min": self._latency_min if self._latency_count else 0.0,
                    "max": self._latency_max if self._latency_count else 0.0,
                    "total": self._latency_total,
                    "count": self._latency_count,
                },
                "canary_alerts": list(self._canary_alerts),
                "calls_since_canary": self._calls_since_canary,
                "canary_interval": self._canary_interval,
            }
            self._reset()
            return snapshot

    # ── Reset ──────────────────────────────────────────────────────────────

    def _reset(self) -> None:
        """Zero all counters.  Caller must hold ``_lock``."""
        self._call_count: int = 0
        self._per_type: Counter[str] = Counter()
        self._confidence_histogram: Counter[str] = Counter()
        self._transform_activations: Counter[str] = Counter()
        self._latency_total: float = 0.0
        self._latency_count: int = 0
        self._latency_min: float = float("inf")
        self._latency_max: float = 0.0
        self._latencies: list[float] = []
        self._canary_alerts: list[dict[str, str]] = []
        self._calls_since_canary: int = 0
        self._canary_interval: int = 100

    # ── Context manager for timing ─────────────────────────────────────────

    def timed_detect(self, detections: list[dict[str, Any]], transforms: list[dict[str, Any]], *, elapsed: float | None = None) -> None:
        """Convenience: record with an explicit elapsed value.

        Prefer calling ``record(...)`` directly with an elapsed value you
        measured externally.  This method is kept for backward compat.
        """
        self.record(elapsed=elapsed or 0.0, detections=detections, transforms=transforms)


# ── Module-level singleton ────────────────────────────────────────────────────

telemetry = _Telemetry()


# ── Public helper: snapshot ───────────────────────────────────────────────────

def get_stats() -> dict[str, Any]:
    """Return a snapshot of all telemetry counters and reset them.

    Usage::

        from piifilter.telemetry import get_stats
        stats = get_stats()
    """
    return telemetry.get_stats()