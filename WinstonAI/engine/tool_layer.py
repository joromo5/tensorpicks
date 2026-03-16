"""Tool execution layer — registry of tools an agent can invoke."""

from __future__ import annotations

import logging
import re
import urllib.parse
from typing import Any, Callable, Coroutine

import httpx

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
    user_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Execute a named tool with the given parameters.

    Args:
        tool_name: Registered tool name.
        params: Arguments forwarded to the tool function.
        agent_config: Optional agent configuration (for tools that need it).
        user_context: Optional dict carrying decrypted user keys/bot connections.

    Returns:
        A dict with at least a ``result`` key.
    """
    fn = _registry.get(tool_name)
    if fn is None:
        return {"error": f"Unknown tool: {tool_name}", "available": available_tools()}

    try:
        result = await fn(
            params=params,
            agent_config=agent_config or {},
            user_context=user_context or {},
        )
        logger.info("Tool '%s' executed successfully", tool_name)
        return result
    except Exception as exc:
        logger.exception("Tool '%s' raised an error", tool_name)
        return {"error": str(exc)}


# ── Shared helpers ────────────────────────────────────────────────────

_USER_AGENT = (
    "Mozilla/5.0 (compatible; WinstonAIBot/1.0; +https://winstonai.com)"
)


def _strip_html(html: str) -> str:
    """Remove HTML tags and collapse whitespace using regex."""
    # Remove script and style blocks entirely
    text = re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style[^>]*>.*?</style>", " ", text, flags=re.DOTALL | re.IGNORECASE)
    # Remove all remaining tags
    text = re.sub(r"<[^>]+>", " ", text)
    # Decode common HTML entities
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    text = text.replace("&quot;", '"').replace("&#39;", "'").replace("&nbsp;", " ")
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text


# ── Data tools ────────────────────────────────────────────────────────


@register("web_search")
async def web_search(
    params: dict[str, Any],
    agent_config: dict[str, Any],
    user_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Search the web using DuckDuckGo HTML search (no API key needed)."""
    query = params.get("query", "").strip()
    if not query:
        return {"error": "Missing 'query' parameter"}

    try:
        encoded_q = urllib.parse.quote_plus(query)
        url = f"https://html.duckduckgo.com/html/?q={encoded_q}"

        async with httpx.AsyncClient(
            timeout=10.0,
            follow_redirects=True,
            headers={"User-Agent": _USER_AGENT},
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()

        html = resp.text
        results: list[dict[str, str]] = []

        # Parse DuckDuckGo HTML results.
        # Each result is in a div with class "result". We extract links and snippets.
        # Pattern: <a class="result__a" href="...">title</a>
        # Snippet: <a class="result__snippet" ...>snippet text</a>
        result_blocks = re.split(r'class="result\s', html)

        for block in result_blocks[1:]:  # skip first (before any result)
            if len(results) >= 5:
                break

            # Extract URL from result__a or result__url
            url_match = re.search(
                r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
                block,
                re.DOTALL,
            )
            if not url_match:
                continue

            raw_url = url_match.group(1)
            title_html = url_match.group(2)

            # DuckDuckGo wraps URLs in a redirect; extract the real URL
            if "uddg=" in raw_url:
                uddg_match = re.search(r"uddg=([^&]+)", raw_url)
                if uddg_match:
                    raw_url = urllib.parse.unquote(uddg_match.group(1))

            title = _strip_html(title_html).strip()

            # Extract snippet
            snippet = ""
            snippet_match = re.search(
                r'class="result__snippet"[^>]*>(.*?)</a>',
                block,
                re.DOTALL,
            )
            if snippet_match:
                snippet = _strip_html(snippet_match.group(1)).strip()

            if title and raw_url:
                results.append({
                    "title": title,
                    "url": raw_url,
                    "snippet": snippet,
                })

        return {"result": results}

    except httpx.TimeoutException:
        return {
            "error": "DuckDuckGo search timed out. Consider adding a Serper API key for more reliable search."
        }
    except Exception as exc:
        logger.warning("DuckDuckGo search failed: %s", exc)
        return {
            "error": f"Web search failed: {exc}. Consider adding a Serper API key for more reliable search."
        }


@register("web_fetch")
async def web_fetch(
    params: dict[str, Any],
    agent_config: dict[str, Any],
    user_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Fetch the content of a URL and return plain text."""
    url = params.get("url", "").strip()
    if not url:
        return {"error": "Missing 'url' parameter"}

    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    try:
        async with httpx.AsyncClient(
            timeout=15.0,
            follow_redirects=True,
            max_redirects=3,
            headers={"User-Agent": _USER_AGENT},
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()

        content_type = resp.headers.get("content-type", "")

        if "text/html" in content_type or "text/xml" in content_type:
            text = _strip_html(resp.text)
        elif "text/" in content_type or "json" in content_type:
            text = resp.text
        else:
            text = resp.text

        # Truncate to 8000 chars to stay within LLM context limits
        if len(text) > 8000:
            text = text[:8000] + "\n\n[... truncated at 8000 chars]"

        return {"result": text, "url": str(resp.url), "status_code": resp.status_code}

    except httpx.TimeoutException:
        return {"error": f"Request timed out fetching {url}"}
    except httpx.ConnectError:
        return {"error": f"DNS or connection error for {url}"}
    except httpx.TooManyRedirects:
        return {"error": f"Too many redirects for {url}"}
    except httpx.HTTPStatusError as exc:
        return {"error": f"HTTP {exc.response.status_code} fetching {url}"}
    except Exception as exc:
        return {"error": f"Failed to fetch {url}: {exc}"}


@register("store_data")
async def store_data(
    params: dict[str, Any],
    agent_config: dict[str, Any],
    user_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Persist a key/value pair in the agent's memory.

    The actual persistence is handled by the agent_runner after this returns.
    """
    key = params.get("key", "")
    value = params.get("value")
    if not key:
        return {"error": "Missing 'key' parameter"}

    return {"result": f"Stored key '{key}' successfully."}


@register("read_data")
async def read_data(
    params: dict[str, Any],
    agent_config: dict[str, Any],
    user_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Read a value from the agent's memory by key."""
    key = params.get("key", "")
    if not key:
        return {"error": "Missing 'key' parameter"}

    memory = agent_config.get("memory") or {}
    value = memory.get(key)
    if value is None:
        return {"result": None, "message": f"Key '{key}' not found in memory"}

    return {"result": value}


# ── Notification tools ────────────────────────────────────────────────


@register("telegram_notify")
async def telegram_notify(
    params: dict[str, Any],
    agent_config: dict[str, Any],
    user_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Send a Telegram message via the Bot API."""
    user_context = user_context or {}
    message = params.get("message", "").strip()
    if not message:
        return {"error": "Missing 'message' parameter"}

    # Resolve bot token and chat_id from user_context (bot_connections)
    telegram_config = user_context.get("telegram", {})
    bot_token = telegram_config.get("bot_token", "")
    chat_id = params.get("chat_id") or telegram_config.get("chat_id", "")

    if not bot_token:
        return {"error": "Telegram bot token not configured. Add it in Bot Connections."}
    if not chat_id:
        return {"error": "Telegram chat_id not configured. Add it in Bot Connections."}

    api_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "Markdown",
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(api_url, json=payload)
            data = resp.json()

        if not data.get("ok"):
            error_desc = data.get("description", "Unknown Telegram error")
            error_code = data.get("error_code", resp.status_code)
            logger.warning(
                "Telegram API error %s: %s (chat_id=%s)",
                error_code, error_desc, chat_id,
            )
            return {"error": f"Telegram error {error_code}: {error_desc}"}

        return {
            "result": "Message sent to Telegram",
            "chat_id": chat_id,
            "message_id": data.get("result", {}).get("message_id"),
        }

    except httpx.TimeoutException:
        return {"error": "Telegram API request timed out"}
    except Exception as exc:
        return {"error": f"Telegram send failed: {exc}"}


@register("slack_notify")
async def slack_notify(
    params: dict[str, Any],
    agent_config: dict[str, Any],
    user_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Send a Slack message via the Web API."""
    user_context = user_context or {}
    message = params.get("message", "").strip()
    if not message:
        return {"error": "Missing 'message' parameter"}

    # Resolve bot token and channel from user_context (bot_connections)
    slack_config = user_context.get("slack", {})
    bot_token = slack_config.get("bot_token", "")
    channel = params.get("channel") or slack_config.get("channel", "")

    if not bot_token:
        return {"error": "Slack bot token not configured. Add it in Bot Connections."}
    if not channel:
        return {"error": "Slack channel not configured. Add it in Bot Connections."}

    api_url = "https://slack.com/api/chat.postMessage"
    headers = {
        "Authorization": f"Bearer {bot_token}",
        "Content-Type": "application/json; charset=utf-8",
    }
    payload = {
        "channel": channel,
        "text": message,
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(api_url, json=payload, headers=headers)
            data = resp.json()

        if not data.get("ok"):
            error_msg = data.get("error", "Unknown Slack error")
            logger.warning("Slack API error: %s (channel=%s)", error_msg, channel)
            return {"error": f"Slack error: {error_msg}"}

        return {
            "result": "Message sent to Slack",
            "channel": data.get("channel", channel),
            "ts": data.get("ts"),
        }

    except httpx.TimeoutException:
        return {"error": "Slack API request timed out"}
    except Exception as exc:
        return {"error": f"Slack send failed: {exc}"}


@register("discord_notify")
async def discord_notify(
    params: dict[str, Any],
    agent_config: dict[str, Any],
    user_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Send a Discord message via webhook or bot token + channel."""
    user_context = user_context or {}
    message = params.get("message", "").strip()
    if not message:
        return {"error": "Missing 'message' parameter"}

    discord_config = user_context.get("discord", {})
    webhook_url = discord_config.get("webhook_url", "")
    bot_token = discord_config.get("bot_token", "")
    channel_id = params.get("channel_id") or discord_config.get("channel_id", "")

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Prefer webhook if available
            if webhook_url:
                payload = {"content": message}
                resp = await client.post(webhook_url, json=payload)

                if resp.status_code == 204:
                    return {"result": "Message sent to Discord via webhook"}
                if resp.status_code >= 400:
                    detail = resp.text[:200]
                    logger.warning(
                        "Discord webhook error %s: %s", resp.status_code, detail,
                    )
                    return {"error": f"Discord webhook error {resp.status_code}: {detail}"}

                return {"result": "Message sent to Discord via webhook"}

            # Fallback to bot token + channel_id
            if bot_token and channel_id:
                api_url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
                headers = {
                    "Authorization": f"Bot {bot_token}",
                    "Content-Type": "application/json",
                }
                payload = {"content": message}
                resp = await client.post(api_url, json=payload, headers=headers)

                if resp.status_code in (200, 201):
                    data = resp.json()
                    return {
                        "result": "Message sent to Discord",
                        "channel_id": channel_id,
                        "message_id": data.get("id"),
                    }
                else:
                    detail = resp.text[:200]
                    logger.warning(
                        "Discord API error %s: %s", resp.status_code, detail,
                    )
                    return {"error": f"Discord API error {resp.status_code}: {detail}"}

            return {
                "error": "Discord not configured. Add a webhook URL or bot token + channel in Bot Connections."
            }

    except httpx.TimeoutException:
        return {"error": "Discord API request timed out"}
    except Exception as exc:
        return {"error": f"Discord send failed: {exc}"}
