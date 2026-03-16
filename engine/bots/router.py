"""Routes agent output to the correct messaging platform."""

from __future__ import annotations

import logging
from typing import Any

from engine.bots import telegram_bot, slack_bot, discord_bot
from engine import db

logger = logging.getLogger(__name__)

_PLATFORM_SENDERS = {
    "telegram": telegram_bot.send_to_user,
    "slack": slack_bot.send_to_user,
    "discord": discord_bot.send_to_user,
}


async def send_output(user_id: str, channel: str, message: str) -> dict[str, Any]:
    """Route a message to the correct messaging platform.

    Args:
        user_id: The TensorPicks user ID (clerk_user_id).
        channel: One of "telegram", "slack", "discord".
        message: The message text to send.

    Returns:
        Platform-specific response dict.

    Raises:
        ValueError: If the channel is not supported or not configured.
    """
    sender = _PLATFORM_SENDERS.get(channel)
    if sender is None:
        raise ValueError(
            f"Unsupported channel '{channel}'. "
            f"Supported: {', '.join(_PLATFORM_SENDERS.keys())}"
        )

    logger.info("Routing message to %s for user %s", channel, user_id)

    try:
        result = await sender(user_id, message)
        logger.info("Message delivered via %s for user %s", channel, user_id)
        return {"ok": True, "channel": channel, "result": result}
    except Exception as exc:
        logger.error("Failed to send via %s for user %s: %s", channel, user_id, exc)
        return {"ok": False, "channel": channel, "error": str(exc)}


async def get_connection_status(user_id: str) -> dict[str, Any]:
    """Return connection status for all platforms.

    Returns a dict keyed by platform name, each containing:
    - connected: bool
    - config: sanitized config (no tokens/secrets)
    """
    connections = await db.get_bot_connections(user_id)

    # Build a lookup by platform
    by_platform: dict[str, dict[str, Any]] = {}
    for conn in connections:
        by_platform[conn["platform"]] = conn

    status: dict[str, Any] = {}
    for platform in ("telegram", "slack", "discord"):
        conn = by_platform.get(platform)
        if conn:
            config = conn.get("config", {})
            # Sanitize: never expose tokens in status responses
            safe_config = {
                k: v for k, v in config.items()
                if k not in ("token", "api_key", "secret", "bot_token")
            }
            status[platform] = {
                "connected": True,
                "config": safe_config,
                "created_at": conn.get("created_at"),
            }
        else:
            status[platform] = {
                "connected": False,
                "config": {},
            }

    return status
