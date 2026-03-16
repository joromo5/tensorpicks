"""Slack Web API integration using httpx."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from engine.key_vault import get_user_key
from engine import db

logger = logging.getLogger(__name__)

_BASE_URL = "https://slack.com/api/"
_MAX_MESSAGE_LENGTH = 4000


def _api_url(method: str) -> str:
    """Build the full Slack API URL for a given method."""
    return f"{_BASE_URL}{method}"


def _auth_headers(token: str) -> dict[str, str]:
    """Build authorization headers for Slack API requests."""
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=utf-8",
    }


# ── Low-level API helpers ────────────────────────────────────────────


async def validate_token(token: str) -> dict[str, Any]:
    """Call auth.test to validate the Slack token and return team/user info.

    Returns dict with keys: ok, url, team, team_id, user, user_id.
    Raises ValueError on invalid token.
    """
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            _api_url("auth.test"),
            headers=_auth_headers(token),
        )
        resp.raise_for_status()
        data = resp.json()

        if not data.get("ok"):
            error = data.get("error", "unknown_error")
            if error in ("invalid_auth", "not_authed", "token_revoked"):
                raise ValueError(f"Invalid Slack token: {error}")
            raise ValueError(f"Slack API error: {error}")

        return {
            "team": data.get("team"),
            "team_id": data.get("team_id"),
            "user": data.get("user"),
            "user_id": data.get("user_id"),
            "url": data.get("url"),
        }


async def send_message(
    token: str,
    channel: str,
    text: str,
    blocks: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Post a message via chat.postMessage.

    Handles rate limiting (Retry-After header) with a single retry, and
    splits messages exceeding the 4000-char limit into multiple chunks.
    """
    chunks = _split_message(text, _MAX_MESSAGE_LENGTH)
    last_result: dict[str, Any] = {}

    async with httpx.AsyncClient(timeout=30) as client:
        for i, chunk in enumerate(chunks):
            payload: dict[str, Any] = {
                "channel": channel,
                "text": chunk,
            }
            # Only include blocks on the first chunk
            if blocks and i == 0:
                payload["blocks"] = blocks

            last_result = await _send_with_retry(client, token, payload)

    return last_result


async def _send_with_retry(
    client: httpx.AsyncClient,
    token: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Send a single message, retrying once on rate limit."""
    for attempt in range(2):
        resp = await client.post(
            _api_url("chat.postMessage"),
            headers=_auth_headers(token),
            json=payload,
        )

        if resp.status_code == 429:
            retry_after = int(resp.headers.get("Retry-After", "5"))
            logger.warning("Slack rate limited, retrying after %ds", retry_after)
            if attempt == 0:
                await asyncio.sleep(retry_after)
                continue
            raise ValueError(f"Slack rate limited, retry after {retry_after}s")

        resp.raise_for_status()
        data = resp.json()

        if not data.get("ok"):
            error = data.get("error", "unknown_error")
            if error == "channel_not_found":
                raise ValueError(f"Slack channel not found: {payload.get('channel')}")
            if error in ("invalid_auth", "not_authed", "token_revoked"):
                raise ValueError(f"Invalid Slack token: {error}")
            raise ValueError(f"Slack API error: {error}")

        return data

    return {}


async def list_channels(token: str) -> list[dict[str, Any]]:
    """List channels the bot is a member of."""
    channels: list[dict[str, Any]] = []
    cursor: str | None = None

    async with httpx.AsyncClient(timeout=15) as client:
        while True:
            params: dict[str, Any] = {
                "types": "public_channel,private_channel",
                "exclude_archived": "true",
                "limit": 200,
            }
            if cursor:
                params["cursor"] = cursor

            resp = await client.get(
                _api_url("conversations.list"),
                headers=_auth_headers(token),
                params=params,
            )
            resp.raise_for_status()
            data = resp.json()

            if not data.get("ok"):
                error = data.get("error", "unknown_error")
                raise ValueError(f"Slack API error: {error}")

            channels.extend(data.get("channels", []))

            cursor = data.get("response_metadata", {}).get("next_cursor")
            if not cursor:
                break

    return channels


# ── High-level: send to a user by user_id ───────────────────────────


async def send_to_user(user_id: str, message: str) -> dict[str, Any]:
    """Look up user's Slack token + channel from DB, then send.

    This is the function the agent_runner calls to deliver output.
    """
    token = await get_user_key(user_id, "slack")

    connections = await db.get_bot_connections(user_id)
    connection = next(
        (c for c in connections if c["platform"] == "slack"),
        None,
    )

    if connection is None:
        raise ValueError("No Slack bot connection configured for this user")

    channel = connection.get("config", {}).get("channel")
    if not channel:
        raise ValueError(
            "Slack connection exists but channel is not configured. "
            "Please set a default channel in your Slack bot settings."
        )

    return await send_message(token, channel, message)


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
