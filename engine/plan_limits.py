"""Plan-based quota enforcement."""

from __future__ import annotations

import logging

from fastapi import HTTPException, status

from engine import db
from engine.models import PlanInfo

logger = logging.getLogger(__name__)

# ── Plan definitions ──────────────────────────────────────────────────

PLAN_LIMITS: dict[str, PlanInfo] = {
    "free": PlanInfo(max_agents=2, max_runs_per_day=10),
    "starter": PlanInfo(max_agents=5, max_runs_per_day=50),
    "pro": PlanInfo(max_agents=20, max_runs_per_day=500),
    "agency": PlanInfo(max_agents=100, max_runs_per_day=5000),
    "enterprise": PlanInfo(max_agents=100, max_runs_per_day=5000),
}


async def _get_user_plan(user_id: str) -> str:
    """Look up the user's current billing plan, defaulting to 'free'."""
    profile = await db.get_user_profile(user_id)
    if profile is None:
        return "free"
    return profile.get("plan", "free")


async def check_agent_limit(user_id: str) -> None:
    """Raise 403 if the user has reached their plan's agent limit."""
    plan = await _get_user_plan(user_id)
    limits = PLAN_LIMITS.get(plan, PLAN_LIMITS["free"])

    agents = await db.list_agents(user_id)
    current = len(agents)

    if current >= limits.max_agents:
        logger.warning(
            "User %s hit agent limit: %d/%d (plan=%s)",
            user_id, current, limits.max_agents, plan,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "Agent limit reached",
                "current": current,
                "limit": limits.max_agents,
                "plan": plan,
            },
        )


async def check_run_limit(user_id: str) -> None:
    """Raise 403 if the user has exceeded today's run quota."""
    plan = await _get_user_plan(user_id)
    limits = PLAN_LIMITS.get(plan, PLAN_LIMITS["free"])

    current = await db.count_runs_today(user_id)

    if current >= limits.max_runs_per_day:
        logger.warning(
            "User %s hit daily run limit: %d/%d (plan=%s)",
            user_id, current, limits.max_runs_per_day, plan,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "Daily run limit reached",
                "current": current,
                "limit": limits.max_runs_per_day,
                "plan": plan,
            },
        )
