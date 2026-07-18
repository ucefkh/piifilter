"""PIIFilter SDK — the easiest way to use PIIFilter programmatically.

No HTTP server. No CLI. Just import and use::

    from piifilter_sdk import PIIFilter

    async with PIIFilter() as pii:
        result = await pii.filter("My email is john@example.com")
        print(result["filtered"])   # "My email is [REDACTED_EMAIL]"
        print(result["risk"])       # RiskAssessment(score=10, level='low')
"""

from piifilter_sdk.client import PIIFilter

__version__ = "2.0.0"

__all__ = [
    "PIIFilter",
]