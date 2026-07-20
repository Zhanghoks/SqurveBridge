"""Provider limits for OpenAI-compatible chat.completions parameters."""

from __future__ import annotations

from typing import Any


def _llm_base_url(llm: Any) -> str:
    client = getattr(llm, "client", None)
    if client is None:
        return ""
    return str(getattr(client, "base_url", "") or "")


def max_chat_completion_n(llm: Any, *, default: int = 4) -> int:
    """Return the largest supported ``n`` for ``chat.completions.create``.

    DeepSeek (and several non-OpenAI hosts) only accept ``n=1``. Qwen /
    DashScope historically allow up to 4, which is the C3SQL default chunk size.
    """
    class_name = type(llm).__name__.lower()
    base_url = _llm_base_url(llm).lower()

    if any(token in class_name for token in ("deepseek", "zhipu", "claude", "gemini", "anthropic")):
        return 1
    if any(token in base_url for token in ("deepseek.com", "anthropic.com", "generativelanguage.googleapis", "bigmodel.cn")):
        return 1
    if "qwen" in class_name or "dashscope" in base_url or "aliyuncs.com" in base_url:
        return min(4, default)
    if "openai" in class_name or "api.openai.com" in base_url:
        return default
    return default


def chat_extra_body_for_llm(llm: Any) -> dict[str, Any] | None:
    """Provider-specific ``extra_body`` knobs (e.g. Qwen thinking switch)."""
    class_name = type(llm).__name__.lower()
    base_url = _llm_base_url(llm).lower()
    if "qwen" in class_name or "dashscope" in base_url or "aliyuncs.com" in base_url:
        return {"enable_thinking": False}
    return None
