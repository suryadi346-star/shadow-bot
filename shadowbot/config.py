"""
ShadowBot Config Manager
Load, save, validate, dan setup wizard untuk config
"""
import json
import os
from pathlib import Path
from typing import Optional

DEFAULT_CONFIG = {
    "provider": "anthropic",
    "model": "claude-sonnet-4-6",
    "api_key": "",
    "base_url": "",
    "max_tokens": 8192,
    "temperature": 0.7,
    "memory_enabled": True,
    "rag_enabled": True,
    "web_search_enabled": True,
    "bash_enabled": True,
    "max_iterations": 20,
    "max_history": 50,
    "workspace_dir": "~/.shadowbot/workspace",
    "system_prompt": (
        "You are ShadowBot — a powerful AI agent running on this device. "
        "You can search the web, execute shell commands, read/write files, "
        "and search your local knowledge base. "
        "Be direct, precise, and efficient. When you need to do something, use tools. "
        "Always verify your actions by checking results."
    ),
    "providers": {
        "anthropic": {
            "api_key": "",
            "model": "claude-sonnet-4-6",
        },
        "openai": {
            "api_key": "",
            "model": "gpt-4o",
            "base_url": "",
        },
        "ollama": {
            "api_key": "ollama",
            "model": "llama3.1:8b",
            "base_url": "http://localhost:11434/v1",
        },
        "openrouter": {
            "api_key": "",
            "model": "anthropic/claude-sonnet-4-6",
            "base_url": "https://openrouter.ai/api/v1",
        },
        "deepseek": {
            "api_key": "",
            "model": "deepseek-chat",
            "base_url": "https://api.deepseek.com/v1",
        },
        "gemini": {
            "api_key": "",
            "model": "gemini-2.0-flash",
            "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        },
        "groq": {
            "api_key": "",
            "model": "llama-3.3-70b-versatile",
            "base_url": "https://api.groq.com/openai/v1",
        },
        "custom": {
            "api_key": "",
            "model": "",
            "base_url": "",
        },
    },
}

CONFIG_DIR = Path("~/.shadowbot").expanduser()
CONFIG_PATH = CONFIG_DIR / "config.json"


def load_config(path: Optional[str] = None) -> dict:
    """Load config — merge dengan defaults jika ada key yang hilang"""
    p = Path(path).expanduser() if path else CONFIG_PATH

    config = dict(DEFAULT_CONFIG)

    if p.exists():
        try:
            with open(p, "r", encoding="utf-8") as f:
                user_config = json.load(f)
            # Deep merge providers
            if "providers" in user_config:
                for k, v in user_config["providers"].items():
                    if k in config["providers"]:
                        config["providers"][k].update(v)
                    else:
                        config["providers"][k] = v
                del user_config["providers"]
            config.update(user_config)
        except (json.JSONDecodeError, IOError) as e:
            print(f"Warning: could not read config ({e}), using defaults")

    # Override dengan environment variables
    env_map = {
        "ANTHROPIC_API_KEY": ("providers", "anthropic", "api_key"),
        "OPENAI_API_KEY": ("providers", "openai", "api_key"),
        "OPENROUTER_API_KEY": ("providers", "openrouter", "api_key"),
        "DEEPSEEK_API_KEY": ("providers", "deepseek", "api_key"),
        "GEMINI_API_KEY": ("providers", "gemini", "api_key"),
        "GROQ_API_KEY": ("providers", "groq", "api_key"),
        "SHADOWBOT_PROVIDER": None,  # top-level
        "SHADOWBOT_MODEL": None,
    }

    for env_key, path_tuple in env_map.items():
        val = os.environ.get(env_key)
        if val:
            if path_tuple:
                config[path_tuple[0]][path_tuple[1]][path_tuple[2]] = val
            else:
                config_key = env_key.lower().replace("shadowbot_", "")
                config[config_key] = val

    return config


def save_config(config: dict, path: Optional[str] = None):
    """Save config to disk"""
    p = Path(path).expanduser() if path else CONFIG_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)


def get_active_api_key(config: dict) -> str:
    """Get API key for the active provider"""
    provider = config.get("provider", "anthropic")
    providers_cfg = config.get("providers", {})
    prov = providers_cfg.get(provider, {})
    return prov.get("api_key") or config.get("api_key", "")


def get_active_model(config: dict) -> str:
    """Get model for the active provider"""
    provider = config.get("provider", "anthropic")
    providers_cfg = config.get("providers", {})
    prov = providers_cfg.get(provider, {})
    return prov.get("model") or config.get("model", "")


def validate_config(config: dict) -> tuple[bool, str]:
    """Check if config is valid enough to run"""
    provider = config.get("provider", "")
    api_key = get_active_api_key(config)

    if provider == "ollama":
        return True, "OK (Ollama — no API key needed)"

    if not api_key or api_key.startswith("your-") or api_key == "":
        return False, f"API key not set for provider '{provider}'"

    model = get_active_model(config)
    if not model:
        return False, f"Model not set for provider '{provider}'"

    return True, "OK"
