"""PIIFilter OpenAI Middleware — transparent OpenAI-compatible proxy.

Usage
-----
    uvicorn piifilter_openai_proxy.server:app --port 8080

Or programmatically::

    from piifilter_openai_proxy import create_app
    app = create_app()
"""

from __future__ import annotations

from piifilter_openai_proxy.server import app, create_app

__all__ = ["app", "create_app"]