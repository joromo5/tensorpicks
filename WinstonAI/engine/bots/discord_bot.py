"""Discord Bot API integration using httpx."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from engine.key_vault import get_user_key
from engine import db

logger = logging.getLogger(__name__)

_BASE_URL = "https://discord.com/api/v10/"
_MAX_MESSAGE_LENGTH = 2000


def _api_url(path: str) -> str:
    """Build the full Discord API URL for a given path."""
    return f"{_BASE_URL}{path}"


def _auth_headers(token: str) -> dict[str, str]:
    """Build authorization headers for Discord API requests."""
    return {
        "Authorization": f"Bot {token}",
        "Content-Type": "application/json",
    }


# ── Low-level API helpers ────────────────────────────────────────────


async def validate_token(token: str) -> dict[str, Any]:
    """Call /users/@me to validate the bot token and return bot info.

    Returns dict with keys: id, username, discriminator, bot.
    Raises ValueError on invalid token.
    """
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            _api_url("users/@me"),
            headers=_auth_headers(token),
        )

        if resp.status_code == 401:
            raise ValueError("Invalid Discord bot token")

        if resp.status_code == 403:
            raise ValueError("Discord bot token lacks required permissions")

        resp.raise_for_status()
        data = resp.json()

        return {
            "id": data.get("id"),
            "username": data.get("username"),
            "discriminator": data.get("discriminator"),
            "bot": data.get("bot", False),
        }


async def send_message(
    token: str,
    channel_id: str,
    content: str,
) -> dict[str, Any]:
    """Post a message to a Discord channel.

    Handles rate limiting (X-RateLimit headers) with a single retry, and
    splits messages exceeding the 2000-char limit into multiple chunks.
    """
    chunks = _split_message(content, _MAX_MESSAGE_LENGTH)
    last_result: dict[str, Any] = {}

    async with httpx.AsyncClient(timeout=30) as client:
        for chunk in chunks:
            payload = {"content": chunk}
            last_result = await _send_with_retry(client, token, channel_id, payload)

    return last_result


async def _send_with_retry(
    client: httpx.AsyncClient,
    token: str,
    channel_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Send a single message, retrying once on rate limit."""
    url = _api_url(f"channels/{channel_id}/messages")

    for attempt in range(2):
        resp = await client.post(url, headers=_auth_headers(token), json=payload)

        if resp.status_code == 429:
            data = resp.json()
            retry_after = data.get("retry_after", 5)
            logger.warning("Discord rate limited, retrying after %.1fs", retry_after)
            if attempt == 0:
                await asyncio.sleep(float(retry_after))
                continue
            raise ValueError(f"Discord rate limited, retry after {retry_after}s")

        if resp.status_code == 401:
            raise ValueError("Invalid Discord bot token")

        if resp.status_code == 403:
            raise ValueError(
                "Discord bot lacks permission to post in this channel. "
                "Ensure the bot has Send Messages permission."
            )

        if resp.status_code == 404:
            raise ValueError(f"Discord channel not found: {channel_id}")

        resp.raise_for_status()
        return resp.json()

    return {}


# ── High-level: send to a user by user_id ───────────────────────────


async def send_to_user(user_id: str, message: str) -> dict[str, Any]:
    """Look up user's Discord token + channel_id from DB, then send.

    This is the function the agent_runner calls to deliver output.
    """
    token = await get_user_key(user_id, "discord")

    connections = await db.get_bot_connections(user_id)
    connection = next(
        (c for c in connections if c["platform"] == "discord"),
        None,
    )

    if connection is None:
        raise ValueError("No Discord bot connection configured for this user")

    channel_id = connection.get("config", {}).get("channel_id")
    if not channel_id:
        raise ValueError(
            "Discord connection exists but channel_id is not configured. "
            "Please set a default channel in your Discord bot settings."
        )

    return await send_message(token, channel_id, message)


# ── Utilities ────────────────────────────────────────────────────────


def _split_message(text: str, max_length: int) -> list[str]:
    """Split a message into chunks that fit within the max length."""
    if len(text) <= max_length:
        return [text]

    chunks: list[str] = []
    remaining = text

    while remaining:
        if len(remaining) <= max_length:
            chunks.append(remaining)
            break

        split_at = remaining.rfind("\n", 0, max_length)
        if split_at == -1 or split_at < max_length // 2:
            split_at = max_length

        chunks.append(remaining[:split_at])
        remaining = remaining[split_at:].lstrip("\n")

    return chunks
