"""Tool execution layer — registry of tools an agent can invoke."""

from __future__ import annotations

import logging
from typing import Any, Callable, Coroutine

logger = logging.getLogger(__name__)

# Type alias for an async tool function.
ToolFn = Callable[..., Coroutine[Any, Any, dict[str, Any]]]

# ── Tool registry ─────────────────────────────────────────────────────

_registry: dict[str, ToolFn] = {}


def register(name: str):
    """Decorator to register an async function as a named tool."""

    def decorator(fn: ToolFn) -> ToolFn:
        _registry[name] = fn
        return fn

    return decorator


def available_tools() -> list[str]:
    """Return names of all registered tools."""
    return sorted(_registry.keys())


async def execute(
    tool_name: str,
    params: dict[str, Any],
    agent_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Execute a named tool with the given parameters.

    Args:
        tool_name: Registered tool name.
        params: Arguments forwarded to the tool function.
        agent_config: Optional agent configuration (for tools that need it).

    Returns:
        A dict with at least a ``result`` key.
    """
    fn = _registry.get(tool_name)
    if fn is None:
        return {"error": f"Unknown tool: {tool_name}", "available": available_tools()}

    try:
        result = await fn(params=params, agent_config=agent_config or {})
        logger.info("Tool '%s' executed successfully", tool_name)
        return result
    except Exception as exc:
        logger.exception("Tool '%s' raised an error", tool_name)
        return {"error": str(exc)}


# ── Data tools ────────────────────────────────────────────────────────


@register("web_search")
async def web_search(
    params: dict[str, Any], agent_config: dict[str, Any]
) -> dict[str, Any]:
    """Search the web for a query. (Stub — integrate a search API.)"""
    query = params.get("query", "")
    logger.info("web_search stub called with query=%s", query)
    return {
        "result": [],
        "note": "web_search is a stub — wire up SerpAPI / Brave / Tavily here",
    }


@register("web_fetch")
async def web_fetch(
    params: dict[str, Any], agent_config: dict[str, Any]
) -> dict[str, Any]:
    """Fetch the content of a URL. (Stub — add readability parsing.)"""
    url = params.get("url", "")
    logger.info("web_fetch stub called with url=%s", url)
    return {
        "result": "",
        "note": "web_fetch is a stub — add httpx fetch + html-to-text here",
    }


@register("store_data")
async def store_data(
    params: dict[str, Any], agent_config: dict[str, Any]
) -> dict[str, Any]:
    """Persist a key/value pair in the agent's memory."""
    key = params.get("key", "")
    value = params.get("value")
    if not key:
        return {"error": "Missing 'key' parameter"}

    # This will be wired to memory.update_memory by the agent_runner.
    return {"result": f"Stored '{key}' (to be wired via agent_runner)"}


@register("read_data")
async def read_data(
    params: dict[str, Any], agent_config: dict[str, Any]
) -> dict[str, Any]:
    """Read a value from the agent's memory by key."""
    key = params.get("key", "")
    if not key:
        return {"error": "Missing 'key' parameter"}

    return {"result": None, "note": "read_data is a stub — wire via agent_runner"}


# ── Notification tools ────────────────────────────────────────────────


@register("telegram_notify")
async def telegram_notify(
    params: dict[str, Any], agent_config: dict[str, Any]
) -> dict[str, Any]:
    """Send a Telegram message. (Stub — integrate Bot API.)"""
    message = params.get("message", "")
    chat_id = params.get("chat_id", "")
    logger.info("telegram_notify stub: chat_id=%s message=%s", chat_id, message[:80])
    return {"result": "sent (stub)", "chat_id": chat_id}


@register("slack_notify")
async def slack_notify(
    params: dict[str, Any], agent_config: dict[str, Any]
) -> dict[str, Any]:
    """Send a Slack message. (Stub — integrate Slack Web API.)"""
    channel = params.get("channel", "")
    message = params.get("message", "")
    logger.info("slack_notify stub: channel=%s message=%s", channel, message[:80])
    return {"result": "sent (stub)", "channel": channel}


@register("discord_notify")
async def discord_notify(
    params: dict[str, Any], agent_config: dict[str, Any]
) -> dict[str, Any]:
    """Send a Discord message via webhook. (Stub.)"""
    webhook_url = params.get("webhook_url", "")
    message = params.get("message", "")
    logger.info("discord_notify stub: message=%s", message[:80])
    return {"result": "sent (stub)", "webhook_url": webhook_url}
