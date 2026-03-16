"""Self-improvement: periodically review recent runs and refine strategy."""

from __future__ import annotations

import logging
from uuid import UUID

from engine import db
from engine.key_vault import get_user_key
from engine.llm import run as llm_run

logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────

REFLECTION_EVERY_N_RUNS: int = 5
MAX_RECENT_LOGS: int = 10

REFLECTION_SYSTEM_PROMPT = """\
You are a meta-cognitive assistant.  You will be given:
1. An agent's current strategy notes.
2. Summaries of its recent runs (outputs + errors).

Your job: produce updated strategy notes that help the agent perform better.
Be concise and actionable.  Output ONLY the new strategy notes — no preamble.
"""


# ── Public API ────────────────────────────────────────────────────────


async def should_reflect(agent_id: UUID, user_id: str) -> bool:
    """Return True if enough runs have accumulated since last reflection."""
    logs = await db.list_run_logs(agent_id, user_id, limit=REFLECTION_EVERY_N_RUNS)
    if len(logs) < REFLECTION_EVERY_N_RUNS:
        return False

    # Reflect if there's at least one error in the recent batch, or every N runs.
    return True


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

    new_notes = response.content.strip()
    if new_notes:
        await db.update_agent(agent_id, user_id, {"strategy_notes": new_notes})
        logger.info("Reflection complete for agent %s — notes updated", agent_id)

    return new_notes
