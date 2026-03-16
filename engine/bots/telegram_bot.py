"""Telegram Bot API integration using httpx (no library dependency)."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from engine.key_vault import get_user_key
from engine import db

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.telegram.org/bot{token}/"
_MAX_MESSAGE_LENGTH = 4096


def _api_url(token: str, method: str) -> str:
    """Build the full Telegram API URL for a given method."""
    return f"{_BASE_URL.format(token=token)}{method}"


# ── Low-level API helpers ────────────────────────────────────────────


async def validate_token(token: str) -> dict[str, Any]:
    """Call getMe to validate the bot token and return bot info.

    Returns dict with keys: id, is_bot, first_name, username.
    Raises httpx.HTTPStatusError on invalid token.
    """
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(_api_url(token, "getMe"))

        if resp.status_code == 401:
            raise ValueError("Invalid Telegram bot token")

        resp.raise_for_status()
        data = resp.json()

        if not data.get("ok"):
            raise ValueError(f"Telegram API error: {data.get('description', 'Unknown')}")

        return data["result"]


async def send_message(
    token: str,
    chat_id: str,
    text: str,
    parse_mode: str = "Markdown",
) -> dict[str, Any]:
    """Send a message via Telegram sendMessage API.

    Handles rate limiting (429) with a single retry, and splits messages
    exceeding the 4096-char limit into multiple chunks.
    """
    chunks = _split_message(text, _MAX_MESSAGE_LENGTH)
    last_result: dict[str, Any] = {}

    async with httpx.AsyncClient(timeout=30) as client:
        for chunk in chunks:
            payload = {
                "chat_id": chat_id,
                "text": chunk,
                "parse_mode": parse_mode,
            }
            last_result = await _send_with_retry(client, token, payload)

    return last_result


async def _send_with_retry(
    client: httpx.AsyncClient,
    token: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Send a single message, retrying once on rate limit (429)."""
    for attempt in range(2):
        resp = await client.post(_api_url(token, "sendMessage"), json=payload)

        if resp.status_code == 429:
            retry_after = resp.json().get("parameters", {}).get("retry_after", 5)
            logger.warning("Telegram rate limited, retrying after %ds", retry_after)
            if attempt == 0:
                await asyncio.sleep(retry_after)
                continue
            raise ValueError(f"Telegram rate limited, retry after {retry_after}s")

        if resp.status_code == 401:
            raise ValueError("Invalid Telegram bot token")

        if resp.status_code == 400:
            description = resp.json().get("description", "")
            if "chat not found" in description.lower():
                raise ValueError(f"Chat not found: {payload.get('chat_id')}")
            raise ValueError(f"Telegram API error: {description}")

        resp.raise_for_status()
        data = resp.json()

        if not data.get("ok"):
            raise ValueError(f"Telegram API error: {data.get('description', 'Unknown')}")

        return data["result"]

    return {}


async def get_updates(token: str, offset: int = 0) -> list[dict[str, Any]]:
    """Get recent updates from the bot (useful for extracting chat_id)."""
    params: dict[str, Any] = {"timeout": 0}
    if offset:
        params["offset"] = offset

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(_api_url(token, "getUpdates"), params=params)

        if resp.status_code == 401:
            raise ValueError("Invalid Telegram bot token")

        resp.raise_for_status()
        data = resp.json()

        if not data.get("ok"):
            raise ValueError(f"Telegram API error: {data.get('description', 'Unknown')}")

        return data["result"]


async def set_webhook(token: str, url: str) -> bool:
    """Set a webhook URL for the bot (for future use)."""
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            _api_url(token, "setWebhook"),
            json={"url": url},
        )

        if resp.status_code == 401:
            raise ValueError("Invalid Telegram bot token")

        resp.raise_for_status()
        data = resp.json()
        return data.get("ok", False)


# ── High-level: send to a user by user_id ───────────────────────────


async def send_to_user(user_id: str, message: str) -> dict[str, Any]:
    """Look up user's Telegram token + chat_id from DB, then send.

    This is the function the agent_runner calls to deliver output.
    """
    # Get the bot token from api_keys
    token = await get_user_key(user_id, "telegram")

    # Get the chat_id from bot_connections
    connections = await db.get_bot_connections(user_id)
    connection = next(
        (c for c in connections if c["platform"] == "telegram"),
        None,
    )

    if connection is None:
        raise ValueError("No Telegram bot connection configured for this user")

    chat_id = connection.get("config", {}).get("chat_id")
    if not chat_id:
        raise ValueError(
            "Telegram connection exists but chat_id is not configured. "
            "Please complete setup by sending /start to your bot and "
            "calling the setup-chat endpoint."
        )

    return await send_message(token, chat_id, message)


# ── Utilities ────────────────────────────────────────────────────────


def _split_message(text: str, max_length: int) -> list[str]:
    """Split a message into chunks that fit within the max length.

    Tries to split on newlines first, then falls back to hard splits.
    """
    if len(text) <= max_length:
        return [text]

    chunks: list[str] = []
    remaining = text

    while remaining:
        if len(remaining) <= max_length:
            chunks.append(remaining)
            break

        # Try to split on a newline near the limit
        split_at = remaining.rfind("\n", 0, max_length)
        if split_at == -1 or split_at < max_length // 2:
            # No good newline found; hard split
            split_at = max_length

        chunks.append(remaining[:split_at])
        remaining = remaining[split_at:].lstrip("\n")

    return chunks
