"""Load repo-root ``.env`` and resolve reproduce config ``api_key`` values."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from reproduce.lib.paths import PROJECT_ROOT

PLACEHOLDER_KEYS = {"", None, "your_api_key_here", "your_zhipu_key_here"}

PROVIDER_ENV_VARS = {
    "qwen": "QWEN_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "zhipu": "ZHIPU_API_KEY",
    "openai": "OPENAI_API_KEY",
    "claude": "ANTHROPIC_API_KEY",
    "gemini": "GOOGLE_API_KEY",
}

_ENV_REF_PATTERN = re.compile(r"^\$\{ENV:([A-Za-z_][A-Za-z0-9_]*)\}$")


def load_dotenv(path: Path | None = None) -> bool:
    """Load KEY=VALUE pairs from ``.env`` into ``os.environ`` (no overwrite)."""
    env_path = path or (PROJECT_ROOT / ".env")
    if not env_path.is_file():
        return False

    loaded = False
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        if (value.startswith('"') and value.endswith('"')) or (
            value.startswith("'") and value.endswith("'")
        ):
            value = value[1:-1]
        if key not in os.environ:
            os.environ[key] = value
            loaded = True
    return loaded


def resolve_env_reference(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    match = _ENV_REF_PATTERN.match(value.strip())
    if not match:
        return value
    return os.environ.get(match.group(1), "")


def resolve_api_key(provider: str, configured: Any) -> str | None:
    """Return a usable API key for *provider*, preferring explicit config then ``.env``."""
    value = resolve_env_reference(configured)
    if isinstance(value, str) and value.strip() and value not in PLACEHOLDER_KEYS:
        return value.strip()

    env_name = PROVIDER_ENV_VARS.get(provider)
    if env_name:
        env_value = os.environ.get(env_name, "").strip()
        if env_value and env_value not in PLACEHOLDER_KEYS:
            return env_value
    return None


def resolve_config_api_keys(config: dict) -> dict:
    """Return a shallow copy of *config* with ``api_key`` filled from ``.env`` when needed."""
    load_dotenv()
    resolved = dict(config)
    api_keys = dict(resolved.get("api_key") or {})
    for provider, configured in list(api_keys.items()):
        key = resolve_api_key(provider, configured)
        if key:
            api_keys[provider] = key
    resolved["api_key"] = api_keys
    return resolved


def api_key_ready(config: dict) -> tuple[bool, str | None]:
    """Check whether the active ``llm.use`` provider has a non-placeholder key."""
    load_dotenv()
    provider = (config.get("llm") or {}).get("use")
    if not provider:
        return False, "llm.use is missing"
    key = resolve_api_key(provider, (config.get("api_key") or {}).get(provider))
    if not key:
        env_hint = PROVIDER_ENV_VARS.get(provider, f"{provider.upper()}_API_KEY")
        return False, (
            f"{provider} api_key is placeholder; set reproduce config api_key.{provider} "
            f"or {env_hint} in repo-root .env"
        )
    return True, None
