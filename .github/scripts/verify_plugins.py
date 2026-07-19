"""PIIFilter — Verify all plugins import successfully.

Called by CI as: uv run python .github/scripts/verify_plugins.py
"""

import sys

PLUGIN_PATHS = [
    "plugins/detector-regex/src",
    "plugins/detector-presidio/src",
    "plugins/detector-gliner/src",
    "plugins/strategy-mask/src",
    "plugins/strategy-semantic/src",
    "plugins/strategy-generalize/src",
    "plugins/provider-openai/src",
    "plugins/provider-anthropic/src",
    "plugins/provider-gemini/src",
    "plugins/provider-lmstudio/src",
    "plugins/provider-ollama/src",
    "plugins/provider-vllm/src",
]

PLUGIN_MODULES = [
    "piifilter_detector_regex",
    "piifilter_detector_presidio",
    "piifilter_detector_gliner",
    "piifilter_strategy_mask",
    "piifilter_strategy_semantic",
    "piifilter_strategy_generalize",
    "piifilter_provider_openai",
    "piifilter_provider_anthropic",
    "piifilter_provider_gemini",
    "piifilter_provider_lmstudio",
    "piifilter_provider_ollama",
    "piifilter_provider_vllm",
]


def main() -> int:
    for p in PLUGIN_PATHS:
        sys.path.insert(0, p)

    failures = []
    for mod in PLUGIN_MODULES:
        try:
            __import__(mod)
            print(f"✅ {mod}")
        except Exception as e:
            print(f"❌ {mod}: {e}")
            failures.append(mod)

    if failures:
        print(f"\n❌ {len(failures)} plugin(s) failed to import: {', '.join(failures)}")
        return 1

    print(f"\n✅ All {len(PLUGIN_MODULES)} plugins import successfully")
    return 0


if __name__ == "__main__":
    sys.exit(main())