"""Core agent execution — load, run, tool-loop, log, reflect."""

from __future__ import annotations

import datetime as dt
import logging
import time
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status

from engine import db
from engine.key_vault import get_user_key
from engine.llm import run as llm_run
from engine.memory import get_memory, update_memory
from engine.plan_limits import check_run_limit
from engine.reflection import run_reflection, should_reflect
from engine.tool_layer import execute as execute_tool

logger = logging.getLogger(__name__)

# Maximum tool-call iterations per run to prevent runaway loops.
MAX_TOOL_ITERATIONS: int = 10


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

        # ── 5. Build context ──────────────────────────────────────────
        memory = await get_memory(agent_id, user_id)
        strategy = agent.get("strategy_notes") or ""

        system_prompt = agent["system_prompt"]
        if strategy:
            system_prompt += f"\n\n## Strategy Notes\n{strategy}"
        if memory:
            import json
            system_prompt += f"\n\n## Memory\n{json.dumps(memory, indent=2)}"

        messages: list[dict[str, str]] = [
            {"role": "user", "content": "Execute your task now."},
        ]

        # Build tool definitions from agent config
        tool_defs = _build_tool_defs(agent.get("tools") or [])

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
                    tc["name"], tc["arguments"], agent_config=agent
                )

                # If the tool stores data, persist to memory
                if tc["name"] == "store_data" and "error" not in tool_result:
                    key = tc["arguments"].get("key", "")
                    value = tc["arguments"].get("value")
                    if key:
                        await update_memory(agent_id, user_id, {key: value})

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
    """Convert a list of tool names into LLM-compatible tool definitions."""
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
            "description": "Store a key-value pair in agent memory",
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {"type": "string"},
                    "value": {"type": "string"},
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
                    "key": {"type": "string"},
                },
                "required": ["key"],
            },
        },
        "telegram_notify": {
            "name": "telegram_notify",
            "description": "Send a Telegram notification",
            "parameters": {
                "type": "object",
                "properties": {
                    "chat_id": {"type": "string"},
                    "message": {"type": "string"},
                },
                "required": ["chat_id", "message"],
            },
        },
        "slack_notify": {
            "name": "slack_notify",
            "description": "Send a Slack notification",
            "parameters": {
                "type": "object",
                "properties": {
                    "channel": {"type": "string"},
                    "message": {"type": "string"},
                },
                "required": ["channel", "message"],
            },
        },
        "discord_notify": {
            "name": "discord_notify",
            "description": "Send a Discord notification via webhook",
            "parameters": {
                "type": "object",
                "properties": {
                    "webhook_url": {"type": "string"},
                    "message": {"type": "string"},
                },
                "required": ["webhook_url", "message"],
            },
        },
    }

    return [tool_schemas[name] for name in tool_names if name in tool_schemas]
