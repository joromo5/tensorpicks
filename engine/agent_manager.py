"""Scheduling layer — register and manage cron-based agent runs."""

from __future__ import annotations

import logging
from uuid import UUID

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from engine.agent_runner import run_agent

logger = logging.getLogger(__name__)

# ── Scheduler singleton ──────────────────────────────────────────────

_scheduler: AsyncIOScheduler | None = None


def get_scheduler() -> AsyncIOScheduler:
    """Return (and lazily create) the global async scheduler."""
    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncIOScheduler()
    return _scheduler


def start_scheduler() -> None:
    """Start the scheduler if it isn't already running."""
    scheduler = get_scheduler()
    if not scheduler.running:
        scheduler.start()
        logger.info("APScheduler started")


def shutdown_scheduler() -> None:
    """Gracefully shut down the scheduler."""
    if _scheduler is not None and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("APScheduler shut down")


# ── Job ID convention ─────────────────────────────────────────────────


def _job_id(agent_id: UUID) -> str:
    return f"agent-{agent_id}"


# ── Registration ──────────────────────────────────────────────────────


def register_agent(agent_id: UUID, user_id: str, cron_expr: str) -> None:
    """Register (or replace) a cron job for an agent.

    Args:
        agent_id: The agent's UUID.
        user_id: Owner's Clerk user ID (needed to run the agent).
        cron_expr: Standard 5-field cron expression (minute hour day month dow).
    """
    scheduler = get_scheduler()
    job_id = _job_id(agent_id)

    # Parse the cron expression into APScheduler fields.
    trigger = _parse_cron(cron_expr)

    # Remove existing job if present (idempotent replace).
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)

    scheduler.add_job(
        _scheduled_run,
        trigger=trigger,
        id=job_id,
        kwargs={"agent_id": agent_id, "user_id": user_id},
        replace_existing=True,
        misfire_grace_time=300,  # allow 5 min late
    )
    logger.info("Registered schedule for agent %s: %s", agent_id, cron_expr)


def unregister_agent(agent_id: UUID) -> None:
    """Remove the cron job for an agent."""
    scheduler = get_scheduler()
    job_id = _job_id(agent_id)
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)
        logger.info("Unregistered schedule for agent %s", agent_id)


async def _scheduled_run(agent_id: UUID, user_id: str) -> None:
    """Callback invoked by APScheduler — runs the agent and logs errors."""
    try:
        logger.info("Scheduled run starting for agent %s", agent_id)
        await run_agent(agent_id, user_id)
    except Exception:
        logger.exception("Scheduled run failed for agent %s", agent_id)


# ── Cron parsing ──────────────────────────────────────────────────────


def _parse_cron(expr: str) -> CronTrigger:
    """Parse a standard 5-field cron expression into an APScheduler trigger.

    Format: minute hour day_of_month month day_of_week
    Example: '0 */4 * * *' -> every 4 hours at minute 0
    """
    parts = expr.strip().split()
    if len(parts) != 5:
        raise ValueError(
            f"Expected 5-field cron expression, got {len(parts)} fields: '{expr}'"
        )

    minute, hour, day, month, day_of_week = parts
    return CronTrigger(
        minute=minute,
        hour=hour,
        day=day,
        month=month,
        day_of_week=day_of_week,
    )
