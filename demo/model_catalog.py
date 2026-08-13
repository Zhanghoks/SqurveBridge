"""Provider → model ID catalog for the Configure LLM pickers.

Model IDs come from the embedded Pi SDK wherever the SDK targets the same API
endpoint the Squrve LLM client calls, so upgrading the pinned SDK also refreshes
the picker instead of leaving a hand-maintained list to rot.

Two providers are curated instead: the SDK reaches Alibaba through the Token
Plan MaaS host and Zhipu through Z.AI's coding-plan host, while this demo calls
DashScope and the Zhipu open platform. Their model IDs are therefore tracked
against those official catalogs rather than borrowed from the SDK.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
from pathlib import Path
from typing import Callable, Mapping, Sequence

# Demo provider id → Pi SDK provider id, for providers that share an endpoint.
SDK_PROVIDER_IDS: Mapping[str, str] = {
    "deepseek": "deepseek",
    "openai": "openai",
    "claude": "anthropic",
    "gemini": "google",
}

# Providers whose official endpoint differs from the SDK's; tracked by hand.
CURATED_MODELS: Mapping[str, tuple[str, ...]] = {
    # DashScope (Model Studio) text models.
    "qwen": (
        "qwen3.8-max",
        "qwen3.7-max",
        "qwen3.7-plus",
        "qwen3.7-flash",
        "qwen3.6-plus",
        "qwen3.6-flash",
        "qwen-plus",
        "qwen-flash",
        "qwen-turbo",
    ),
    # Zhipu open platform (open.bigmodel.cn) text models.
    "zhipu": (
        "glm-5.2",
        "glm-5.1",
        "glm-5",
        "glm-5-turbo",
        "glm-4.7",
        "glm-4.7-flashx",
        "glm-4.6",
    ),
}

# Used when Node or the SDK is unavailable, so the pickers never come back
# empty. Deliberately short: the SDK is the real source for these providers.
FALLBACK_SDK_MODELS: Mapping[str, tuple[str, ...]] = {
    "deepseek": ("deepseek-v4-flash", "deepseek-v4-pro"),
    "openai": ("gpt-5-mini", "gpt-4.1-mini"),
    "claude": ("claude-sonnet-4-5", "claude-haiku-4-5"),
    "gemini": ("gemini-2.5-flash", "gemini-2.0-flash"),
}

PROVIDER_ORDER: tuple[str, ...] = ("qwen", "deepseek", "zhipu", "openai", "claude", "gemini")

# The SDK lists models alphabetically, which would leave the picker defaulting
# to whatever sorts first (gpt-4, a research preview). Name the model each
# provider should open with instead; a demo runs many generations, so these are
# the fast, low-cost tiers. Ignored when the catalog no longer carries the ID.
DEFAULT_MODELS: Mapping[str, str] = {
    "qwen": "qwen3.7-flash",
    "deepseek": "deepseek-v4-flash",
    "zhipu": "glm-4.7-flashx",
    "openai": "gpt-5-mini",
    "claude": "claude-haiku-4-5",
    "gemini": "gemini-2.5-flash",
}

_CATALOG_TIMEOUT_SECONDS = 20.0
_cache: dict[str, list[str]] | None = None
_cache_lock = threading.Lock()


def _catalog_script(project_root: Path) -> Path:
    return project_root / "demo" / "pi_model_catalog.mjs"


def read_sdk_models(
    project_root: Path,
    node_binary: str = "node",
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> dict[str, list[str]]:
    """Ask the embedded Pi SDK for its model IDs, keyed by demo provider id.

    Returns an empty mapping when Node or the SDK is missing; callers fall back
    to `FALLBACK_SDK_MODELS` so a partial install never empties the picker.
    """
    script = _catalog_script(project_root)
    if not script.is_file() or not shutil.which(node_binary):
        return {}
    sdk_ids = list(dict.fromkeys(SDK_PROVIDER_IDS.values()))
    try:
        completed = runner(
            [node_binary, str(script), *sdk_ids],
            cwd=str(project_root),
            capture_output=True,
            text=True,
            timeout=_CATALOG_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return {}
    if completed.returncode != 0 or not (completed.stdout or "").strip():
        return {}
    try:
        payload = json.loads(completed.stdout)
    except (TypeError, ValueError):
        return {}
    if not isinstance(payload, dict):
        return {}
    resolved: dict[str, list[str]] = {}
    for provider, sdk_id in SDK_PROVIDER_IDS.items():
        models = payload.get(sdk_id)
        if isinstance(models, list):
            clean = [str(item) for item in models if isinstance(item, str) and item.strip()]
            if clean:
                resolved[provider] = clean
    return resolved


def _default_first(provider: str, models: list[str]) -> list[str]:
    preferred = DEFAULT_MODELS.get(provider)
    if not preferred or preferred not in models:
        return models
    return [preferred, *(item for item in models if item != preferred)]


def build_catalog(sdk_models: Mapping[str, Sequence[str]] | None = None) -> dict[str, list[str]]:
    """Merge SDK-sourced and curated model IDs into the demo provider order."""
    sourced = sdk_models or {}
    catalog: dict[str, list[str]] = {}
    for provider in PROVIDER_ORDER:
        if provider in CURATED_MODELS:
            models = list(CURATED_MODELS[provider])
        else:
            models = list(sourced.get(provider) or ()) or list(FALLBACK_SDK_MODELS.get(provider, ()))
        catalog[provider] = _default_first(provider, models)
    return catalog


def provider_models(project_root: Path, node_binary: str | None = None) -> dict[str, list[str]]:
    """Cached provider → model IDs. The SDK catalog is static per install."""
    global _cache
    with _cache_lock:
        if _cache is None:
            binary = node_binary or os.environ.get("PI_NODE_BINARY", "node")
            _cache = build_catalog(read_sdk_models(project_root, binary))
        return {provider: list(models) for provider, models in _cache.items()}


def reset_cache() -> None:
    """Drop the memoized catalog; used by tests and after an SDK upgrade."""
    global _cache
    with _cache_lock:
        _cache = None
