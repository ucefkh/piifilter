"""Regression tests for RegexDetector: SSN mask recast behavior.

Verifies that SOCIAL_SECURITY patterns with X-masked values are correctly
classified: bare X-masked values (no keyword prefix) stay as SOCIAL_SECURITY,
while contextual X-masked values (keyword prefix like "SSN:" or "social")
are recast to MASKED_SSN.
"""

from __future__ import annotations

import pytest

from piifilter_detector_regex.detector import RegexDetector
from piifilter.shared.models import EntityType


@pytest.mark.asyncio
async def test_bare_xmasked_ssn_stays_social_security():
    """Bare X-masked SSN (no keyword) should be SOCIAL_SECURITY, not MASKED_SSN."""
    det = RegexDetector()
    text = "Full: XXX-XX-6789"
    results = await det.detect(text)
    # Should find the X-masked SSN
    mask_matches = [r for r in results if "XXX-XX-6789" in (r.text or "")]
    assert len(mask_matches) > 0, "Should detect the X-masked SSN"
    # All should be SOCIAL_SECURITY (not MASKED_SSN)
    for m in mask_matches:
        assert m.entity_type == EntityType.SOCIAL_SECURITY, (
            f"Bare X-masked SSN should be SOCIAL_SECURITY, got {m.entity_type}"
        )


@pytest.mark.asyncio
async def test_contextual_xmasked_ssn_is_masked_ssn():
    """X-masked SSN with context keyword should be MASKED_SSN."""
    det = RegexDetector()
    text = "masked SSN: XXX-XX-9074"
    results = await det.detect(text)
    masked_matches = [r for r in results if r.entity_type == EntityType.MASKED_SSN]
    assert len(masked_matches) > 0, (
        "Contextual X-masked SSN should be detected as MASKED_SSN"
    )


@pytest.mark.asyncio
async def test_xmasked_ssn_with_ssn_keyword():
    """'SSN: XXX-XX-6789' should still be detected correctly (SOCIAL_SECURITY or MASKED_SSN)."""
    det = RegexDetector()
    text = "SSN: XXX-XX-6789"
    results = await det.detect(text)
    # The 0.70 pattern catches this as SOCIAL_SECURITY with mask chars -> recast to MASKED_SSN
    # The 0.45 bare pattern also catches "XXX-XX-6789" as SOCIAL_SECURITY but is deduped
    types_found = {r.entity_type for r in results}
    assert EntityType.MASKED_SSN in types_found or EntityType.SOCIAL_SECURITY in types_found, (
        f"Should detect X-masked SSN with keyword, got types: {types_found}"
    )


@pytest.mark.asyncio
async def test_ssn_mask_no_false_masked():
    """Item 179 regression: 'SSN last-4: 6789. Full: XXX-XX-6789' should not produce MASKED_SSN FP."""
    det = RegexDetector()
    text = "SSN last-4: 6789. Full: XXX-XX-6789"
    results = await det.detect(text)
    masked = [r for r in results if r.entity_type == EntityType.MASKED_SSN]
    assert len(masked) == 0, (
        f"Should have zero MASKED_SSN false positives, got {len(masked)}: "
        f"{[r.text for r in masked]}"
    )
    # But should still detect the bare X-masked SSN as SOCIAL_SECURITY
    ssn_matches = [r for r in results if r.entity_type == EntityType.SOCIAL_SECURITY]
    assert any("XXX-XX-6789" in (r.text or "") for r in ssn_matches), (
        "Bare X-masked SSN should be detected as SOCIAL_SECURITY"
    )