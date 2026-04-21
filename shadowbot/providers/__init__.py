from .base import BaseProvider
from .anthropic_provider import AnthropicProvider
from .openai_provider import OpenAIProvider


def get_provider(config: dict) -> BaseProvider:
    """Factory — pilih provider berdasarkan config"""
    provider_name = config.get("provider", "anthropic").lower()

    providers_cfg = config.get("providers", {})
    prov_cfg = providers_cfg.get(provider_name, {})

    api_key = prov_cfg.get("api_key") or config.get("api_key", "")
    model = prov_cfg.get("model") or config.get("model", "")
    base_url = prov_cfg.get("base_url") or config.get("base_url", "")

    if provider_name == "anthropic":
        return AnthropicProvider(api_key=api_key, model=model or "claude-sonnet-4-6")

    # Semua provider OpenAI-compatible (openai, ollama, openrouter, deepseek, gemini, custom)
    return OpenAIProvider(
        api_key=api_key,
        model=model or "gpt-4o-mini",
        base_url=base_url or None,
        provider_name=provider_name,
    )


__all__ = ["BaseProvider", "AnthropicProvider", "OpenAIProvider", "get_provider"]
