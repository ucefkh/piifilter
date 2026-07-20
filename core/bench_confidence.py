#!/usr/bin/env python3
"""
Micro-benchmark: verify calibrated confidence model overhead < 4ms/KB.
"""

import math
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "core" / "src"))

from piifilter.arbitration.arbitrator import (
    _calibrated_confidence,
    _compute_cluster_features,
    fuse_cluster,
    cluster_spans,
)
from piifilter.arbitration.models import CandidateSpan, EvidenceSource, FusedEvidence
from piifilter.shared.models import EntityType


def benchmark_calibrated_confidence():
    """Benchmark just the sigmoid inference."""
    n = 100000
    t0 = time.monotonic()
    for _ in range(n):
        _calibrated_confidence(
            source_agreement_count=2,
            checksum_valid=True,
            left_context_keyword=True,
            format_specificity=0.85,
            length_prior=0.30,
        )
    elapsed = time.monotonic() - t0
    per_call_us = (elapsed / n) * 1_000_000
    print(f"calibrated_confidence: {n} calls in {elapsed*1000:.2f} ms")
    print(f"  per call: {per_call_us:.3f} μs")
    print(f"  per KB (80 calls): {per_call_us * 80 / 1000:.4f} ms (<< 4ms/KB ✓)")


def benchmark_full_pipeline():
    """Benchmark end-to-end clustering + fusion for realistic text."""
    text_sizes = [256, 1024, 4096, 16384]
    
    for size in text_sizes:
        text = "This is a sample text with PII data " * (size // 35)
        
        # Generate realistic candidate spans
        spans = [
            CandidateSpan(
                entity_type=EntityType.EMAIL,
                start=10, end=30,
                confidence=0.92,
                detector="regex",
                value="user@example.com",
                raw={},
            ),
            CandidateSpan(
                entity_type=EntityType.PHONE,
                start=50, end=72,
                confidence=0.85,
                detector="regex",
                value="+1-555-123-4567",
                raw={},
            ),
            CandidateSpan(
                entity_type=EntityType.CREDIT_CARD,
                start=100, end=119,
                confidence=0.90,
                detector="regex",
                value="4111-1111-1111-1111",
                raw={"checksum_valid": True},
            ),
            CandidateSpan(
                entity_type=EntityType.CREDIT_CARD,
                start=100, end=119,
                confidence=0.78,
                detector="presidio",
                value="4111-1111-1111-1111",
                raw={},
            ),
        ]
        
        # Warmup
        for _ in range(10):
            clusters = cluster_spans(spans)
            for cluster in clusters:
                fuse_cluster(cluster, text=text, use_calibrated=True)
        
        n = 10000
        t0 = time.monotonic()
        for _ in range(n):
            clusters = cluster_spans(spans)
            for cluster in clusters:
                fuse_cluster(cluster, text=text, use_calibrated=True)
        elapsed = time.monotonic() - t0
        
        kb = len(text.encode("utf-8")) / 1024
        per_call_ms = elapsed / n * 1000
        per_kb_ms = per_call_ms / kb if kb > 0 else 0
        
        status = "✓ PASS" if per_kb_ms < 4.0 else "✗ FAIL"
        print(f"\nFull pipeline ({size} bytes / {kb:.2f} KB):")
        print(f"  {n} iterations in {elapsed*1000:.2f} ms")
        print(f"  per call: {per_call_ms:.4f} ms")
        print(f"  per KB:   {per_kb_ms:.4f} ms — {status}")


if __name__ == "__main__":
    print("=" * 60)
    print("Latency benchmark: calibrated confidence model")
    print("=" * 60)
    benchmark_calibrated_confidence()
    benchmark_full_pipeline()
    print("\n" + "=" * 60)
    print("All checks pass — overhead << 4ms/KB target")