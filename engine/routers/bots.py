"""Bot management endpoints — connect, configure, test, disconnect."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from engine.auth import get_current_user
from engine.bots import telegram_bot, slack_bot, discord_bot
from engine.bots.router import get_connection_status
from engine.key_vault import encrypt_key, get_user_key
from engine import db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/bots", tags=["bots"])


# ── Request models ───────────────────────────────────────────────────


class TelegramConnectRequest(BaseModel):
    """Payload for connecting a Telegram bot."""

    token: str = Field(..., min_length=10, description="Telegram bot token from @BotFather")


class TelegramSetupChatRequest(BaseModel):
    """Payload for setting the Telegram chat_id."""

    chat_id: str = Field(..., min_length=1, description="Telegram chat ID to send messages to")


class SlackConnectRequest(BaseModel):
    """Payload for connecting a Slack bot."""

    token: str = Field(..., min_length=10, description="Slack bot OAuth token (xoxb-...)")
    channel: str = Field(..., min_length=1, description="Default Slack channel ID")


class DiscordConnectRequest(BaseModel):
    """Payload for connecting a Discord bot."""

    token: str = Field(..., min_length=10, description="Discord bot token")
    channel_id: str = Field(..., min_length=1, description="Default Discord channel ID")


# ── POST /bots/telegram/connect ─────────────────────────────────────


@router.post("/telegram/connect")
async def connect_telegram(
    body: TelegramConnectRequest,
    user_id: str = Depends(get_current_user),
) -> dict[str, Any]:
    """Validate a Telegram bot token and store the connection.

    After connecting, the user must send /start to their bot and then
    call /bots/telegram/setup-chat with the chat_id.
    """
    try:
        bot_info = await telegram_bot.validate_token(body.token)
    except (ValueError, Exception) as exc:
        logger.warning("Telegram token validation failed for user %s: %s", user_id, exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid Telegram bot token: {exc}",
        )

    # Store the token as an encrypted API key
    encrypted = encrypt_key(body.token)
    hint = body.token[-4:]
    await db.store_api_key(user_id, "telegram", encrypted, hint)

    # Create bot_connection with instructions for chat_id discovery
    config = {
        "bot_id": bot_info.get("id"),
        "bot_username": bot_info.get("username"),
        "bot_name": bot_info.get("first_name"),
        "chat_id": None,  # Must be set via /bots/telegram/setup-chat
    }
    await db.upsert_bot_connection(user_id, "telegram", config)

    logger.info("Telegram bot connected for user %s: @%s", user_id, bot_info.get("username"))

    return {
        "connected": True,
        "bot": {
            "id": bot_info.get("id"),
            "username": bot_info.get("username"),
            "first_name": bot_info.get("first_name"),
        },
        "next_step": (
            f"Send /start to @{bot_info.get('username')} in Telegram, "
            "then call POST /bots/telegram/setup-chat with your chat_id."
        ),
    }


# ── POST /bots/telegram/setup-chat ──────────────────────────────────


@router.post("/telegram/setup-chat")
async def setup_telegram_chat(
    body: TelegramSetupChatRequest,
    user_id: str = Depends(get_current_user),
) -> dict[str, Any]:
    """Store the chat_id for Telegram message delivery."""
    connections = await db.get_bot_connections(user_id)
    connection = next(
        (c for c in connections if c["platform"] == "telegram"),
        None,
    )

    if connection is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No Telegram bot connected. Call /bots/telegram/connect first.",
        )

    config = connection.get("config", {})
    config["chat_id"] = body.chat_id

    await db.upsert_bot_connection(user_id, "telegram", config)

    logger.info("Telegram chat_id set for user %s", user_id)

    return {
        "configured": True,
        "chat_id": body.chat_id,
        "message": "Telegram bot is fully configured. You can now send test messages.",
    }


# ── POST /bots/telegram/test ────────────────────────────────────────


@router.post("/telegram/test")
async def test_telegram(
    user_id: str = Depends(get_current_user),
) -> dict[str, Any]:
    """Send a test message to verify the Telegram integration works."""
    try:
        result = await telegram_bot.send_to_user(
            user_id,
            "TensorPicks test message — your Telegram bot is working!",
        )
        return {"ok": True, "message": "Test message sent successfully", "result": result}
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
    except Exception as exc:
        logger.error("Telegram test failed for user %s: %s", user_id, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to send test message: {exc}",
        )


# ── POST /bots/slack/connect ────────────────────────────────────────


@router.post("/slack/connect")
async def connect_slack(
    body: SlackConnectRequest,
    user_id: str = Depends(get_current_user),
) -> dict[str, Any]:
    """Validate a Slack bot token and store the connection."""
    try:
        team_info = await slack_bot.validate_token(body.token)
    except (ValueError, Exception) as exc:
        logger.warning("Slack token validation failed for user %s: %s", user_id, exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid Slack token: {exc}",
        )

    encrypted = encrypt_key(body.token)
    hint = body.token[-4:]
    await db.store_api_key(user_id, "slack", encrypted, hint)

    config = {
        "team": team_info.get("team"),
        "team_id": team_info.get("team_id"),
        "channel": body.channel,
    }
    await db.upsert_bot_connection(user_id, "slack", config)

    logger.info("Slack bot connected for user %s: team %s", user_id, team_info.get("team"))

    return {
        "connected": True,
        "team": team_info,
        "channel": body.channel,
    }


# ── POST /bots/discord/connect ──────────────────────────────────────


@router.post("/discord/connect")
async def connect_discord(
    body: DiscordConnectRequest,
    user_id: str = Depends(get_current_user),
) -> dict[str, Any]:
    """Validate a Discord bot token and store the connection."""
    try:
        bot_info = await discord_bot.validate_token(body.token)
    except (ValueError, Exception) as exc:
        logger.warning("Discord token validation failed for user %s: %s", user_id, exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid Discord token: {exc}",
        )

    encrypted = encrypt_key(body.token)
    hint = body.token[-4:]
    await db.store_api_key(user_id, "discord", encrypted, hint)

    config = {
        "bot_id": bot_info.get("id"),
        "bot_username": bot_info.get("username"),
        "channel_id": body.channel_id,
    }
    await db.upsert_bot_connection(user_id, "discord", config)

    logger.info("Discord bot connected for user %s: %s", user_id, bot_info.get("username"))

    return {
        "connected": True,
        "bot": bot_info,
        "channel_id": body.channel_id,
    }


# ── GET /bots/status ────────────────────────────────────────────────


@router.get("/status")
async def bot_status(
    user_id: str = Depends(get_current_user),
) -> dict[str, Any]:
    """Return connection status for all platforms."""
    return await get_connection_status(user_id)


# ── POST /bots/{platform}/disconnect ────────────────────────────────


@router.post("/{platform}/disconnect")
async def disconnect_bot(
    platform: str,
    user_id: str = Depends(get_current_user),
) -> dict[str, Any]:
    """Remove a bot connection and its associated API key."""
    if platform not in ("telegram", "slack", "discord"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported platform '{platform}'. Use: telegram, slack, discord.",
        )

    # Delete the bot_connection
    connections = await db.get_bot_connections(user_id)
    connection = next(
        (c for c in connections if c["platform"] == platform),
        None,
    )

    if connection is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No {platform} bot connection found.",
        )

    # Remove the API key
    await db.delete_api_key(user_id, platform)

    # Remove the bot_connection by upserting with empty config
    # (Supabase doesn't have a direct delete by composite key easily,
    # so we delete via the client)
    try:
        db.get_client().table("bot_connections").delete().eq(
            "user_id", user_id
        ).eq("platform", platform).execute()
    except Exception as exc:
        logger.error("Failed to delete bot_connection for %s/%s: %s", user_id, platform, exc)

    logger.info("Disconnected %s bot for user %s", platform, user_id)

    return {"disconnected": True, "platform": platform}
