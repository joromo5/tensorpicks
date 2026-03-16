"""Core agent execution — load, run, tool-loop, log, reflect."""

from __future__ import annotations

import datetime as dt
import json
import logging
import time
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status

from engine import db
from engine.key_vault import decrypt_key, get_user_key
from engine.llm import run as llm_run
from engine.memory import get_memory, update_memory
from engine.plan_limits import check_run_limit
from engine.reflection import run_reflection, should_reflect
from engine.tool_layer import execute as execute_tool

logger = logging.getLogger(__name__)

# Maximum tool-call iterations per run to prevent runaway loops.
MAX_TOOL_ITERATIONS: int = 10

# Notification tool names
_NOTIFICATION_TOOLS = {"telegram_notify", "slack_notify", "discord_notify"}

# Mapping from output_channel name to platform key in bot_connections
_CHANNEL_TO_PLATFORM = {
    "telegram": "telegram",
    "slack": "slack",
    "discord": "discord",
}


async def _build_user_context(user_id: str, tool_names: list[str]) -> dict[str, Any]:
    """Pre-decrypt bot tokens for notification tools the agent uses.

    Returns a dict keyed by platform (telegram, slack, discord) with
    the decrypted connection config for each.
    """
    needs_bots = bool(_NOTIFICATION_TOOLS & set(tool_names))
    if not needs_bots:
        return {}

    try:
        connections = await db.get_bot_connections(user_id)
    except Exception:
        logger.warning("Failed to fetch bot_connections for user %s", user_id)
        return {}

    ctx: dict[str, Any] = {}
    for conn in connections:
        platform = conn.get("platform", "")
        config = conn.get("config") or {}

        decrypted_config: dict[str, Any] = {}
        for key, value in config.items():
            # Attempt to decrypt values that look like Fernet tokens
            if isinstance(value, str) and len(value) > 50 and value.startswith("gAAAAA"):
                try:
                    decrypted_config[key] = decrypt_key(value)
                except Exception:
                    decrypted_config[key] = value
            else:
                decrypted_config[key] = value

        if platform in _CHANNEL_TO_PLATFORM:
            ctx[platform] = decrypted_config

    return ctx


async def send_to_channel(
    output_channel: str,
    message: str,
    user_context: dict[str, Any],
) -> dict[str, Any] | None:
    """Send the agent's final output to its configured output channel.

    Returns the tool result dict, or None if no channel is configured.
    """
    if not output_channel or output_channel not in _CHANNEL_TO_PLATFORM:
        return None

    tool_name = f"{output_channel}_notify"
    params = {"message": message}

    result = await execute_tool(
        tool_name, params, agent_config={}, user_context=user_context,
    )

    if "error" in result:
        logger.warning(
            "Auto-send to %s failed: %s", output_channel, result["error"],
        )
    else:
        logger.info("Auto-sent output to %s", output_channel)

    return result


async def run_agent(agent_id: UUID, user_id: str) -> dict[str, Any]:
    """Execute a single agent run end-to-end.

    Steps:
      1. Load agent config from DB.
      2. Check plan limits.
      3. Create a run_log entry (status=running).
      4. Decrypt the user's LLM API key.
      5. Build context (system prompt + memory + strategy notes).
      6. Call the LLM (with tool loop).
      7. Persist output, update run_log (status=success|error).
      8. Trigger reflection if warranted.
      9. Auto-send output to configured channel.

    Returns:
        The completed run_log record.
    """
    # ── 1. Load agent ─────────────────────────────────────────────────
    agent = await db.get_agent(agent_id, user_id)
    if agent is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent {agent_id} not found",
        )

    if not agent.get("is_active", True):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Agent is archived",
        )

    # ── 2. Plan limits ────────────────────────────────────────────────
    await check_run_limit(user_id)

    # ── 3. Create run log ─────────────────────────────────────────────
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    run_log = await db.create_run_log({
        "agent_id": str(agent_id),
        "user_id": user_id,
        "status": "running",
        "started_at": now,
    })
    run_id = UUID(run_log["id"])
    t_start = time.monotonic()

    try:
        # ── 4. Decrypt API key ────────────────────────────────────────
        provider = agent.get("llm_provider", "openai")
        api_key = await get_user_key(user_id, provider)

        # Pre-decrypt bot tokens for notification tools
        tool_names = agent.get("tools") or []
        user_context = await _build_user_context(user_id, tool_names)

        # ── 5. Build context ──────────────────────────────────────────
        memory = await get_memory(agent_id, user_id)
        strategy = agent.get("strategy_notes") or ""

        # Inject memory into agent_config so read_data can access it
        agent_with_memory = {**agent, "memory": memory}

        system_prompt = agent["system_prompt"]
        if strategy:
            system_prompt += f"\n\n## Strategy Notes\n{strategy}"
        if memory:
            system_prompt += f"\n\n## Memory\n{json.dumps(memory, indent=2)}"

        messages: list[dict[str, str]] = [
            {"role": "user", "content": "Execute your task now."},
        ]

        # Build tool definitions from agent config
        tool_defs = _build_tool_defs(tool_names)

        # ── 6. LLM call + tool loop ──────────────────────────────────
        final_content = ""
        total_tokens = 0

        for iteration in range(MAX_TOOL_ITERATIONS):
            response = await llm_run(
                api_key=api_key,
                provider=provider,
                system=system_prompt,
                messages=messages,
                tools=tool_defs if tool_defs else None,
            )
            total_tokens += response.usage.get("total_tokens", 0)

            if not response.tool_calls:
                final_content = response.content
                break

            # Append assistant message with tool calls
            messages.append({"role": "assistant", "content": response.content})

            # Execute each tool call
            for tc in response.tool_calls:
                tool_result = await execute_tool(
                    tc["name"],
                    tc["arguments"],
                    agent_config=agent_with_memory,
                    user_context=user_context,
                )

                # If the tool stores data, persist to memory
                if tc["name"] == "store_data" and "error" not in tool_result:
                    key = tc["arguments"].get("key", "")
                    value = tc["arguments"].get("value")
                    if key:
                        await update_memory(agent_id, user_id, {key: value})
                        # Keep the in-memory copy fresh for subsequent read_data calls
                        agent_with_memory.setdefault("memory", {})[key] = value

                messages.append({
                    "role": "user",
                    "content": f"Tool '{tc['name']}' returned: {tool_result}",
                })
        else:
            final_content = (
                f"Agent hit max tool iterations ({MAX_TOOL_ITERATIONS}). "
                f"Last response: {response.content}"
            )

        # ── 7. Update run log ─────────────────────────────────────────
        duration_ms = int((time.monotonic() - t_start) * 1000)
        finished_at = dt.datetime.now(dt.timezone.utc).isoformat()

        run_log = await db.update_run_log(run_id, {
            "status": "success",
            "finished_at": finished_at,
            "duration_ms": duration_ms,
            "output": final_content[:10_000],  # cap stored output
            "tokens_used": total_tokens,
        })

        # ── 8. Reflection ─────────────────────────────────────────────
        try:
            if await should_reflect(agent_id, user_id):
                await run_reflection(agent_id, user_id)
        except Exception:
            logger.exception("Reflection failed for agent %s (non-fatal)", agent_id)

        # ── 9. Auto-send to output channel ────────────────────────────
        output_channel = agent.get("output_channel", "")
        if output_channel and final_content:
            try:
                await send_to_channel(output_channel, final_content, user_context)
            except Exception:
                logger.exception(
                    "Auto-send to %s failed for agent %s (non-fatal)",
                    output_channel, agent_id,
                )

        return run_log

    except HTTPException:
        # Re-raise HTTP errors (plan limits, missing keys, etc.)
        duration_ms = int((time.monotonic() - t_start) * 1000)
        await db.update_run_log(run_id, {
            "status": "error",
            "finished_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "duration_ms": duration_ms,
            "error": "HTTP error during run",
        })
        raise

    except Exception as exc:
        duration_ms = int((time.monotonic() - t_start) * 1000)
        error_msg = f"{type(exc).__name__}: {exc}"
        logger.exception("Agent %s run failed", agent_id)
        await db.update_run_log(run_id, {
            "status": "error",
            "finished_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "duration_ms": duration_ms,
            "error": error_msg[:2000],
        })
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Agent run failed: {error_msg}",
        ) from exc


def _build_tool_defs(tool_names: list[str]) -> list[dict[str, Any]]:
    """Convert a list of tool names into LLM-compatible tool definitions.

    Notification tools do NOT require chat_id/channel/webhook_url params —
    the platform auto-resolves those from bot_connections.
    """
    tool_schemas: dict[str, dict[str, Any]] = {
        "web_search": {
            "name": "web_search",
            "description": "Search the web for information",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                },
                "required": ["query"],
            },
        },
        "web_fetch": {
            "name": "web_fetch",
            "description": "Fetch content from a URL",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to fetch"},
                },
                "required": ["url"],
            },
        },
        "store_data": {
            "name": "store_data",
            "description": "Store a key-value pair in agent memory for later retrieval",
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {"type": "string", "description": "The key to store under"},
                    "value": {"type": "string", "description": "The value to store"},
                },
                "required": ["key", "value"],
            },
        },
        "read_data": {
            "name": "read_data",
            "description": "Read a value from agent memory by key",
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {"type": "string", "description": "The key to read"},
                },
                "required": ["key"],
            },
        },
        "telegram_notify": {
            "name": "telegram_notify",
            "description": "Send a Telegram notification message",
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {"type": "string", "description": "Message text to send"},
                },
                "required": ["message"],
            },
        },
        "slack_notify": {
            "name": "slack_notify",
            "description": "Send a Slack notification message",
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {"type": "string", "description": "Message text to send"},
                },
                "required": ["message"],
            },
        },
        "discord_notify": {
            "name": "discord_notify",
            "description": "Send a Discord notification message",
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {"type": "string", "description": "Message text to send"},
                },
                "required": ["message"],
            },
        },
    }

    return [tool_schemas[name] for name in tool_names if name in tool_schemas]
