"""Unified LLM router — call any supported provider through one interface."""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# ── Provider endpoints ────────────────────────────────────────────────

_PROVIDER_CONFIG: dict[str, dict[str, str]] = {
    "anthropic": {
        "url": "https://api.anthropic.com/v1/messages",
        "model_default": "claude-sonnet-4-20250514",
        "auth_header": "x-api-key",
        "version_header": "anthropic-version",
        "version": "2023-06-01",
    },
    "openai": {
        "url": "https://api.openai.com/v1/chat/completions",
        "model_default": "gpt-4o",
        "auth_header": "Authorization",
    },
    "groq": {
        "url": "https://api.groq.com/openai/v1/chat/completions",
        "model_default": "llama-3.3-70b-versatile",
        "auth_header": "Authorization",
    },
}


# ── Standardised response ────────────────────────────────────────────


class LLMResponse:
    """Normalised response from any LLM provider."""

    __slots__ = ("content", "tool_calls", "usage", "raw")

    def __init__(
        self,
        content: str,
        tool_calls: list[dict[str, Any]],
        usage: dict[str, int],
        raw: dict[str, Any],
    ) -> None:
        self.content = content
        self.tool_calls = tool_calls
        self.usage = usage
        self.raw = raw

    def to_dict(self) -> dict[str, Any]:
        return {
            "content": self.content,
            "tool_calls": self.tool_calls,
            "usage": self.usage,
        }


# ── Anthropic adapter ────────────────────────────────────────────────


def _build_anthropic_request(
    system: str,
    messages: list[dict[str, str]],
    tools: list[dict[str, Any]] | None,
    model: str,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "model": model,
        "max_tokens": 4096,
        "system": system,
        "messages": messages,
    }
    if tools:
        body["tools"] = tools
    return body


def _parse_anthropic_response(data: dict[str, Any]) -> LLMResponse:
    content_blocks = data.get("content", [])
    text_parts: list[str] = []
    tool_calls: list[dict[str, Any]] = []

    for block in content_blocks:
        if block["type"] == "text":
            text_parts.append(block["text"])
        elif block["type"] == "tool_use":
            tool_calls.append({
                "id": block["id"],
                "name": block["name"],
                "arguments": block["input"],
            })

    usage_raw = data.get("usage", {})
    usage = {
        "prompt_tokens": usage_raw.get("input_tokens", 0),
        "completion_tokens": usage_raw.get("output_tokens", 0),
        "total_tokens": usage_raw.get("input_tokens", 0) + usage_raw.get("output_tokens", 0),
    }
    return LLMResponse(
        content="\n".join(text_parts),
        tool_calls=tool_calls,
        usage=usage,
        raw=data,
    )


# ── OpenAI-compatible adapter (OpenAI / Groq) ────────────────────────


def _build_openai_request(
    system: str,
    messages: list[dict[str, str]],
    tools: list[dict[str, Any]] | None,
    model: str,
) -> dict[str, Any]:
    full_messages = [{"role": "system", "content": system}, *messages]
    body: dict[str, Any] = {"model": model, "messages": full_messages}
    if tools:
        body["tools"] = [
            {"type": "function", "function": t} for t in tools
        ]
    return body


def _parse_openai_response(data: dict[str, Any]) -> LLMResponse:
    choice = data["choices"][0]["message"]
    content = choice.get("content") or ""
    tool_calls: list[dict[str, Any]] = []

    for tc in choice.get("tool_calls") or []:
        import json

        tool_calls.append({
            "id": tc["id"],
            "name": tc["function"]["name"],
            "arguments": json.loads(tc["function"]["arguments"]),
        })

    usage_raw = data.get("usage", {})
    usage = {
        "prompt_tokens": usage_raw.get("prompt_tokens", 0),
        "completion_tokens": usage_raw.get("completion_tokens", 0),
        "total_tokens": usage_raw.get("total_tokens", 0),
    }
    return LLMResponse(content=content, tool_calls=tool_calls, usage=usage, raw=data)


# ── Public API ────────────────────────────────────────────────────────


async def run(
    api_key: str,
    provider: str,
    system: str,
    messages: list[dict[str, str]],
    tools: list[dict[str, Any]] | None = None,
    model: str | None = None,
    timeout: float = 120.0,
) -> LLMResponse:
    """Send a chat request to the specified LLM provider.

    Args:
        api_key: The user's decrypted API key for this provider.
        provider: One of 'anthropic', 'openai', 'groq'.
        system: System prompt.
        messages: Conversation messages in [{role, content}] format.
        tools: Optional tool definitions.
        model: Override the default model for the provider.
        timeout: HTTP timeout in seconds.

    Returns:
        A normalised ``LLMResponse``.
    """
    cfg = _PROVIDER_CONFIG.get(provider)
    if cfg is None:
        raise ValueError(f"Unsupported LLM provider: {provider}")

    resolved_model = model or cfg["model_default"]

    # Build provider-specific request
    if provider == "anthropic":
        body = _build_anthropic_request(system, messages, tools, resolved_model)
    else:
        body = _build_openai_request(system, messages, tools, resolved_model)

    # Build headers
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if cfg["auth_header"] == "Authorization":
        headers["Authorization"] = f"Bearer {api_key}"
    else:
        headers[cfg["auth_header"]] = api_key

    if "version_header" in cfg:
        headers[cfg["version_header"]] = cfg["version"]

    logger.info("LLM request: provider=%s model=%s", provider, resolved_model)

    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(cfg["url"], json=body, headers=headers)
        resp.raise_for_status()
        data = resp.json()

    # Parse response
    if provider == "anthropic":
        return _parse_anthropic_response(data)
    else:
        return _parse_openai_response(data)
