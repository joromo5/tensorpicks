"""Self-improvement: periodically review recent runs and refine strategy."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from engine import db
from engine.key_vault import get_user_key
from engine.llm import run as llm_run
from engine.memory import get_memory, update_memory

logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────

DEFAULT_REFLECT_EVERY: int = 5
MAX_RECENT_LOGS: int = 10
ERROR_THRESHOLD: int = 2  # trigger early reflection if this many errors in batch
MAX_LESSONS: int = 20  # FIFO cap on lessons list

REFLECTION_SYSTEM_PROMPT = """\
You are a meta-cognitive assistant.  You will be given:
1. An agent's current strategy notes.
2. Summaries of its recent runs (outputs + errors).

Your job: analyse what went well and what didn't, then produce updated strategy
notes and 1-2 concise key lessons learned.

You MUST respond with valid JSON in this exact format — no markdown fences,
no preamble:

{
  "strategy_notes": "Updated strategy notes here — be concise and actionable.",
  "lessons": ["Lesson one.", "Lesson two."]
}
"""


# ── Public API ────────────────────────────────────────────────────────


async def should_reflect(agent_id: UUID, user_id: str) -> bool:
    """Return True if enough runs have accumulated since last reflection."""
    agent = await db.get_agent(agent_id, user_id)
    if agent is None:
        return False

    # Read the agent's configured reflection interval (default 5)
    memory = agent.get("memory") or {}
    reflect_every = agent.get("reflect_every") or memory.get("reflect_every") or DEFAULT_REFLECT_EVERY

    # Determine runs since last reflection
    last_reflection = memory.get("last_reflection")

    if last_reflection:
        # Count runs with started_at > last_reflection
        logs = await db.list_run_logs(agent_id, user_id, limit=reflect_every + ERROR_THRESHOLD)
        runs_since = [
            log for log in logs
            if (log.get("started_at") or "") > last_reflection
        ]
    else:
        # No prior reflection — count total runs
        runs_since = await db.list_run_logs(agent_id, user_id, limit=reflect_every + ERROR_THRESHOLD)

    if not runs_since:
        return False

    # Early intervention: trigger if 2+ errors in the recent batch
    error_count = sum(
        1 for log in runs_since
        if log.get("status") == "error"
    )
    if error_count >= ERROR_THRESHOLD:
        logger.info(
            "Early reflection trigger for agent %s: %d errors in %d recent runs",
            agent_id, error_count, len(runs_since),
        )
        return True

    # Normal trigger: enough runs accumulated
    if len(runs_since) >= reflect_every:
        return True

    return False


async def run_reflection(agent_id: UUID, user_id: str) -> str | None:
    """Build a reflection prompt from recent logs and update strategy notes.

    Returns the new strategy notes, or None if reflection was skipped.
    """
    agent = await db.get_agent(agent_id, user_id)
    if agent is None:
        logger.warning("Reflection skipped — agent %s not found", agent_id)
        return None

    logs = await db.list_run_logs(agent_id, user_id, limit=MAX_RECENT_LOGS)
    if not logs:
        return None

    # Build the user message with run summaries
    summaries: list[str] = []
    for log in logs:
        status_text = log.get("status", "unknown")
        output = (log.get("output") or "")[:500]
        error = (log.get("error") or "")[:300]
        summaries.append(
            f"- [{status_text}] output: {output}"
            + (f" | error: {error}" if error else "")
        )

    current_notes = agent.get("strategy_notes") or "(none)"
    user_message = (
        f"## Current strategy notes\n{current_notes}\n\n"
        f"## Recent run summaries\n" + "\n".join(summaries)
    )

    # Use the same LLM provider the agent is configured for, falling back to openai.
    provider = agent.get("llm_provider", "openai")
    try:
        api_key = await get_user_key(user_id, provider)
    except Exception:
        logger.warning("Reflection skipped — no %s key for user", provider)
        return None

    try:
        response = await llm_run(
            api_key=api_key,
            provider=provider,
            system=REFLECTION_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )
    except Exception:
        logger.exception("Reflection LLM call failed for agent %s", agent_id)
        return None

    # ── Token counting ────────────────────────────────────────────────
    reflection_tokens = response.usage.get("total_tokens", 0)

    # ── Parse structured JSON response ────────────────────────────────
    raw_content = response.content.strip()
    new_notes: str
    new_lessons: list[str] = []

    try:
        parsed = json.loads(raw_content)
        new_notes = parsed.get("strategy_notes", raw_content)
        new_lessons = parsed.get("lessons", [])
        if not isinstance(new_lessons, list):
            new_lessons = [str(new_lessons)]
    except (json.JSONDecodeError, TypeError):
        # Fall back to treating entire response as plain-text strategy notes
        new_notes = raw_content
        new_lessons = []

    if not new_notes:
        return None

    # ── Update strategy notes on the agent ────────────────────────────
    await db.update_agent(agent_id, user_id, {"strategy_notes": new_notes})

    # ── Update memory with reflection metadata ────────────────────────
    memory = await get_memory(agent_id, user_id)

    # Increment reflection count
    reflection_count = (memory.get("reflection_count") or 0) + 1

    # Cumulative token tracking
    total_reflection_tokens = (memory.get("total_reflection_tokens") or 0) + reflection_tokens

    # Append lessons (FIFO — cap at MAX_LESSONS)
    existing_lessons: list[str] = memory.get("lessons") or []
    if not isinstance(existing_lessons, list):
        existing_lessons = []
    updated_lessons = existing_lessons + new_lessons
    if len(updated_lessons) > MAX_LESSONS:
        updated_lessons = updated_lessons[-MAX_LESSONS:]

    await update_memory(agent_id, user_id, {
        "reflection_count": reflection_count,
        "last_reflection": datetime.now(timezone.utc).isoformat(),
        "total_reflection_tokens": total_reflection_tokens,
        "lessons": updated_lessons,
    })

    logger.info(
        "Reflection complete for agent %s — notes updated, tokens=%d, total_reflections=%d",
        agent_id, reflection_tokens, reflection_count,
    )

    return new_notes
