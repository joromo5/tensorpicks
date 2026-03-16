"""Agent CRUD and manual-run endpoints."""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from engine.agent_manager import register_agent, unregister_agent
from engine.agent_runner import run_agent
from engine.auth import get_current_user
from engine.key_vault import get_user_key
from engine.llm import run as llm_run
from engine.models import AgentCreate, AgentResponse, AgentUpdate
from engine.plan_limits import check_agent_limit
from engine.reflection import run_reflection
from engine import db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agents", tags=["agents"])

# ── Config generation prompt ──────────────────────────────────────────

_CONFIG_SYSTEM_PROMPT = """\
You are an AI-agent configuration generator.  Given a plain-English description
of what an agent should do, produce a JSON object with these keys:

- name (string): short agent name
- system_prompt (string): the system prompt the agent will use
- tools (list[string]): which tools the agent needs, chosen from:
  web_search, web_fetch, store_data, read_data,
  telegram_notify, slack_notify, discord_notify
- schedule (string|null): suggested cron expression, or null if on-demand only

Output ONLY valid JSON — no markdown fences, no explanation.
"""


# ── POST /agents — create agent ──────────────────────────────────────


@router.post("", status_code=status.HTTP_201_CREATED, response_model=AgentResponse)
async def create_agent(
    body: AgentCreate,
    user_id: str = Depends(get_current_user),
):
    """Create a new agent from a natural-language description.

    An LLM generates the structured config (name, system prompt, tools,
    schedule) from the description.
    """
    await check_agent_limit(user_id)

    # Try to generate config via LLM; fall back to sensible defaults.
    config = await _generate_config(user_id, body.description)

    agent_data = {
        "user_id": user_id,
        "name": config.get("name", "New Agent"),
        "description": body.description,
        "system_prompt": config.get("system_prompt", body.description),
        "tools": config.get("tools", []),
        "schedule": body.schedule or config.get("schedule"),
        "strategy_notes": None,
        "memory": {},
        "is_active": True,
    }

    agent = await db.create_agent(agent_data)

    # Register schedule if present
    if agent.get("schedule"):
        try:
            register_agent(UUID(agent["id"]), user_id, agent["schedule"])
        except ValueError as exc:
            logger.warning("Invalid cron for agent %s: %s", agent["id"], exc)

    return agent


# ── GET /agents — list agents ────────────────────────────────────────


@router.get("", response_model=list[AgentResponse])
async def list_agents(user_id: str = Depends(get_current_user)):
    """List all active agents for the authenticated user."""
    return await db.list_agents(user_id)


# ── GET /agents/{id} — detail ────────────────────────────────────────


@router.get("/{agent_id}", response_model=AgentResponse)
async def get_agent(agent_id: UUID, user_id: str = Depends(get_current_user)):
    """Get full details for a single agent."""
    agent = await db.get_agent(agent_id, user_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


# ── PATCH /agents/{id} — update ──────────────────────────────────────


@router.patch("/{agent_id}", response_model=AgentResponse)
async def update_agent(
    agent_id: UUID,
    body: AgentUpdate,
    user_id: str = Depends(get_current_user),
):
    """Partially update an agent's configuration."""
    updates = body.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    agent = await db.update_agent(agent_id, user_id, updates)

    # Re-register schedule if it changed
    schedule = agent.get("schedule")
    if "schedule" in updates:
        if schedule:
            try:
                register_agent(UUID(agent["id"]), user_id, schedule)
            except ValueError:
                pass
        else:
            unregister_agent(agent_id)

    return agent


# ── DELETE /agents/{id} — soft delete ─────────────────────────────────


@router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent(agent_id: UUID, user_id: str = Depends(get_current_user)):
    """Soft-delete (archive) an agent and remove its schedule."""
    await db.soft_delete_agent(agent_id, user_id)
    unregister_agent(agent_id)


# ── POST /agents/{id}/run — manual trigger ───────────────────────────


@router.post("/{agent_id}/run")
async def trigger_run(agent_id: UUID, user_id: str = Depends(get_current_user)):
    """Manually trigger an agent run."""
    result = await run_agent(agent_id, user_id)
    return result


# ── POST /agents/{id}/reflect — manual reflection trigger ────────────


@router.post("/{agent_id}/reflect")
async def trigger_reflection(
    agent_id: UUID, user_id: str = Depends(get_current_user)
):
    """Manually trigger a reflection cycle for the given agent.

    Useful for testing and debugging the self-improvement loop.
    """
    agent = await db.get_agent(agent_id, user_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")

    new_notes = await run_reflection(agent_id, user_id)
    if new_notes is None:
        return {
            "reflected": False,
            "message": "Reflection skipped — not enough data or missing LLM key.",
        }

    return {
        "reflected": True,
        "strategy_notes": new_notes,
    }


# ── Helpers ───────────────────────────────────────────────────────────


async def _generate_config(user_id: str, description: str) -> dict:
    """Ask an LLM to generate agent config from a description."""
    import json

    # Try each provider in order of preference
    for provider in ("openai", "anthropic", "groq"):
        try:
            api_key = await get_user_key(user_id, provider)
        except HTTPException:
            continue

        try:
            response = await llm_run(
                api_key=api_key,
                provider=provider,
                system=_CONFIG_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": description}],
            )
            return json.loads(response.content)
        except (json.JSONDecodeError, Exception) as exc:
            logger.warning("Config generation with %s failed: %s", provider, exc)
            continue

    # If no LLM is available, return minimal defaults
    logger.info("No LLM available for config generation — using defaults")
    return {
        "name": "New Agent",
        "system_prompt": description,
        "tools": [],
        "schedule": None,
    }
