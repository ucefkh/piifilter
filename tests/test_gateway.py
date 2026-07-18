"""Tests for the PIIFilter LLM Gateway."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from piifilter.config import FilterConfig
from piifilter.gateway import LLMGateway
from piifilter.gateway.provider_map import PROVIDER_MAP, get_provider_info


class TestProviderMap:
    def test_all_providers_have_required_keys(self):
        for name, info in PROVIDER_MAP.items():
            assert "endpoint" in info, f"{name} missing endpoint"
            assert "format" in info, f"{name} missing format"

    def test_all_formats_known(self):
        valid_formats = {"openai", "anthropic", "gemini"}
        for name, info in PROVIDER_MAP.items():
            assert info["format"] in valid_formats, f"{name} has unknown format: {info['format']}"

    def test_all_endpoints_are_urls(self):
        for name, info in PROVIDER_MAP.items():
            assert info["endpoint"].startswith("http"), f"{name} bad endpoint: {info['endpoint']}"

    def test_get_provider_info_known(self):
        assert get_provider_info("openai")["endpoint"] == "https://api.openai.com/v1"
        assert get_provider_info("anthropic")["format"] == "anthropic"
        assert get_provider_info("gemini")["format"] == "gemini"

    def test_get_provider_info_unknown(self):
        assert get_provider_info("nonexistent") == {}

    def test_get_provider_info_case_insensitive_and_space_free(self):
        assert get_provider_info("OpenAI")["endpoint"] == "https://api.openai.com/v1"
        assert get_provider_info("lmstudio")["endpoint"] == "http://localhost:1234/v1"
        # Spaces are stripped; "lm studio" → "lmstudio"
        assert get_provider_info("lm studio")["endpoint"] == "http://localhost:1234/v1"

    def test_known_provider_set(self):
        expected = {"lmstudio", "ollama", "openai", "anthropic", "gemini", "vllm", "deepseek"}
        assert set(PROVIDER_MAP.keys()) == expected


class TestLLMGatewayInit:
    def test_default_config_lmstudio(self):
        cfg = FilterConfig()
        gw = LLMGateway(cfg)
        assert gw._endpoint == "http://localhost:1234/v1"
        assert gw._format == "openai"
        assert gw._default_model == "gpt-3.5-turbo"
        assert gw._api_key == ""

    def test_config_endpoint_overrides_provider_map(self):
        cfg = FilterConfig()
        cfg.provider.name = "openai"
        cfg.provider.endpoint = "https://custom-proxy.example.com/v1"
        cfg.provider.api_key = "custom-key"
        gw = LLMGateway(cfg)
        assert gw._endpoint == "https://custom-proxy.example.com/v1"

    def test_provider_map_fallback_when_config_endpoint_empty(self):
        cfg = FilterConfig()
        cfg.provider.name = "openai"
        cfg.provider.endpoint = ""
        cfg.provider.api_key = "sk-test"
        gw = LLMGateway(cfg)
        assert gw._endpoint == "https://api.openai.com/v1"


class TestAuthHeaders:
    def test_no_auth_for_local_when_no_key(self):
        cfg = FilterConfig()
        gw = LLMGateway(cfg)
        try:
            headers = gw._build_headers()
            assert "Authorization" not in headers
            assert headers["Content-Type"] == "application/json"
        finally:
            gw.close()

    def test_bearer_for_openai(self):
        cfg = FilterConfig()
        cfg.provider.name = "openai"
        cfg.provider.endpoint = ""
        cfg.provider.api_key = "sk-test"
        gw = LLMGateway(cfg)
        try:
            headers = gw._build_headers()
            assert headers["Authorization"] == "Bearer sk-test"
        finally:
            gw.close()

    def test_bearer_for_anthropic(self):
        cfg = FilterConfig()
        cfg.provider.name = "anthropic"
        cfg.provider.endpoint = ""
        cfg.provider.api_key = "ant-test"
        gw = LLMGateway(cfg)
        try:
            headers = gw._build_headers()
            assert headers["Authorization"] == "Bearer ant-test"
        finally:
            gw.close()

    def test_goog_api_key_for_gemini(self):
        cfg = FilterConfig()
        cfg.provider.name = "gemini"
        cfg.provider.endpoint = ""
        cfg.provider.api_key = "gem-key"
        gw = LLMGateway(cfg)
        try:
            headers = gw._build_headers()
            assert headers["x-goog-api-key"] == "gem-key"
            assert "Authorization" not in headers
        finally:
            gw.close()


class TestCheckHealth:
    @pytest.mark.asyncio
    async def test_returns_false_when_unreachable(self):
        cfg = FilterConfig()
        cfg.provider.endpoint = "http://localhost:1"
        cfg.provider.api_key = ""
        gw = LLMGateway(cfg)
        try:
            healthy = await gw.check_health()
            assert healthy is False
        finally:
            await gw.close()

    @pytest.mark.asyncio
    async def test_returns_true_when_mocked(self):
        cfg = FilterConfig()
        gw = LLMGateway(cfg)
        try:
            gw._client.get = AsyncMock(return_value=httpx.Response(200))
            healthy = await gw.check_health()
            assert healthy is True
        finally:
            await gw.close()

    @pytest.mark.asyncio
    async def test_returns_false_on_exception(self):
        cfg = FilterConfig()
        gw = LLMGateway(cfg)
        try:
            gw._client.get = AsyncMock(side_effect=Exception("fail"))
            healthy = await gw.check_health()
            assert healthy is False
        finally:
            await gw.close()


class TestForwardErrors:
    @pytest.mark.asyncio
    async def test_connect_error_returns_placeholder(self):
        cfg = FilterConfig()
        cfg.provider.endpoint = "http://localhost:1"
        cfg.provider.api_key = ""
        gw = LLMGateway(cfg)
        try:
            result = await gw.forward("test prompt", model="test-model")
            assert result.startswith("[PIIFilter Gateway Error:")
            assert "Unable to reach" in result
        finally:
            await gw.close()

    @pytest.mark.asyncio
    async def test_timeout_returns_placeholder(self):
        cfg = FilterConfig()
        cfg.provider.endpoint = "http://localhost:1"
        gw = LLMGateway(cfg)
        try:
            gw._client.post = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
            result = await gw.forward("test", model="m")
            assert result.startswith("[PIIFilter Gateway Error:")
        finally:
            await gw.close()

    @pytest.mark.asyncio
    async def test_http_error_returns_placeholder(self):
        cfg = FilterConfig()
        cfg.provider.endpoint = ""
        cfg.provider.name = "openai"
        cfg.provider.api_key = "sk-test"
        gw = LLMGateway(cfg)
        try:
            gw._client.post = AsyncMock(
                side_effect=httpx.HTTPStatusError(
                    "403", request=httpx.Request("POST", "https://example.com"),
                    response=httpx.Response(403),
                )
            )
            result = await gw.forward("test", model="gpt-4")
            assert "[PIIFilter Gateway Error: Provider returned 403]" in result
        finally:
            await gw.close()


class TestForwardOpenAICompat:
    @pytest.mark.asyncio
    async def test_successful_response(self):
        cfg = FilterConfig()
        cfg.provider.endpoint = "http://localhost:9123/v1"
        cfg.provider.api_key = ""
        gw = LLMGateway(cfg)
        try:
            req = httpx.Request("POST", "http://localhost:9123/v1/chat/completions")
            mock_resp = httpx.Response(
                200,
                json={
                    "choices": [
                        {"message": {"content": "Hello, world!"}}
                    ]
                },
                request=req,
            )
            gw._client.post = AsyncMock(return_value=mock_resp)
            result = await gw.forward("Say hello", model="gpt-4")
            assert result == "Hello, world!"
        finally:
            await gw.close()

    @pytest.mark.asyncio
    async def test_empty_choices_returns_placeholder(self):
        cfg = FilterConfig()
        cfg.provider.endpoint = "http://localhost:9123/v1"
        cfg.provider.api_key = ""
        gw = LLMGateway(cfg)
        try:
            req = httpx.Request("POST", "http://localhost:9123/v1/chat/completions")
            mock_resp = httpx.Response(200, json={"choices": []}, request=req)
            gw._client.post = AsyncMock(return_value=mock_resp)
            result = await gw.forward("test", model="gpt-4")
            assert "empty response" in result
        finally:
            await gw.close()


class TestForwardAnthropic:
    @pytest.mark.asyncio
    async def test_successful_response(self):
        cfg = FilterConfig()
        cfg.provider.name = "anthropic"
        cfg.provider.endpoint = "http://localhost:9123/v1"
        cfg.provider.api_key = ""
        cfg.provider.default_model = "claude-3"
        gw = LLMGateway(cfg)
        try:
            req = httpx.Request("POST", "http://localhost:9123/v1/messages")
            mock_resp = httpx.Response(
                200,
                json={
                    "content": [
                        {"type": "text", "text": "Hello from Claude"}
                    ]
                },
                request=req,
            )
            gw._client.post = AsyncMock(return_value=mock_resp)
            result = await gw.forward("Hi")
            assert result == "Hello from Claude"
        finally:
            await gw.close()

    @pytest.mark.asyncio
    async def test_multiple_text_blocks_concatenated(self):
        cfg = FilterConfig()
        cfg.provider.name = "anthropic"
        cfg.provider.endpoint = "http://localhost:9123/v1"
        cfg.provider.api_key = ""
        cfg.provider.default_model = "claude-3"
        gw = LLMGateway(cfg)
        try:
            req = httpx.Request("POST", "http://localhost:9123/v1/messages")
            mock_resp = httpx.Response(
                200,
                json={
                    "content": [
                        {"type": "text", "text": "Block A"},
                        {"type": "text", "text": "Block B"},
                        {"type": "tool_use", "text": "should be skipped"},
                    ]
                },
                request=req,
            )
            gw._client.post = AsyncMock(return_value=mock_resp)
            result = await gw.forward("test")
            assert result == "Block ABlock B"
        finally:
            await gw.close()


class TestForwardGemini:
    @pytest.mark.asyncio
    async def test_successful_response(self):
        cfg = FilterConfig()
        cfg.provider.name = "gemini"
        cfg.provider.endpoint = "http://localhost:9123/v1beta"
        cfg.provider.default_model = "gemini-pro"
        cfg.provider.api_key = ""
        gw = LLMGateway(cfg)
        try:
            req = httpx.Request("POST", "http://localhost:9123/v1beta/models/gemini-pro:generateContent")
            mock_resp = httpx.Response(
                200,
                json={
                    "candidates": [
                        {
                            "content": {
                                "parts": [{"text": "Hi from Gemini"}]
                            }
                        }
                    ]
                },
                request=req,
            )
            gw._client.post = AsyncMock(return_value=mock_resp)
            result = await gw.forward("Hi")
            assert result == "Hi from Gemini"
        finally:
            await gw.close()

    @pytest.mark.asyncio
    async def test_no_candidates_returns_placeholder(self):
        cfg = FilterConfig()
        cfg.provider.name = "gemini"
        cfg.provider.endpoint = "http://localhost:9123/v1beta"
        cfg.provider.default_model = "gemini-pro"
        cfg.provider.api_key = ""
        gw = LLMGateway(cfg)
        try:
            req = httpx.Request("POST", "http://localhost:9123/v1beta/models/gemini-pro:generateContent")
            mock_resp = httpx.Response(200, json={"candidates": []}, request=req)
            gw._client.post = AsyncMock(return_value=mock_resp)
            result = await gw.forward("test")
            assert "empty response" in result
        finally:
            await gw.close()