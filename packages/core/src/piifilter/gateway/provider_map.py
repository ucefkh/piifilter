"""Provider endpoint and format mapping for the LLM Gateway."""

PROVIDER_MAP = {
    "lmstudio": {"endpoint": "http://localhost:1234/v1", "format": "openai"},
    "ollama": {"endpoint": "http://localhost:11434/v1", "format": "openai"},
    "openai": {"endpoint": "https://api.openai.com/v1", "format": "openai"},
    "anthropic": {"endpoint": "https://api.anthropic.com/v1", "format": "anthropic"},
    "gemini": {"endpoint": "https://generativelanguage.googleapis.com/v1beta", "format": "gemini"},
    "vllm": {"endpoint": "http://localhost:8000/v1", "format": "openai"},
    "deepseek": {"endpoint": "https://api.deepseek.com/v1", "format": "openai"},
}


def get_provider_info(name: str) -> dict:
    """Return provider endpoint and format info for a given provider name.

    Args:
        name: Provider name (lowercase, e.g. "openai", "anthropic", "lmstudio").

    Returns:
        Dictionary with "endpoint" and "format" keys, or an empty dict if
        the provider name is not recognised.

    """
    name_lower = name.strip().lower().replace(" ", "")
    return PROVIDER_MAP.get(name_lower, {})