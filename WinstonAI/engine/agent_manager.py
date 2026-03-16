"""Scheduling layer — register and manage cron-based agent runs."""

from __future__ import annotations

import datetime as dt
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

    # Update next_run_at in the DB (fire-and-forget style)
    import asyncio

    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_update_next_run_at(agent_id, user_id))
    except RuntimeError:
        # No running loop — skip async update
        pass


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
    finally:
        # Update next_run_at after each scheduled run
        try:
            await _update_next_run_at(agent_id, user_id)
        except Exception:
            logger.warning("Failed to update next_run_at for agent %s", agent_id)


# ── Next run tracking ────────────────────────────────────────────────


async def _update_next_run_at(agent_id: UUID, user_id: str) -> None:
    """Get the next fire time from APScheduler and persist it to the DB."""
    from engine import db

    scheduler = get_scheduler()
    job_id = _job_id(agent_id)
    job = scheduler.get_job(job_id)

    if job is None:
        return

    next_fire = job.next_run_time
    if next_fire is not None:
        next_run_iso = next_fire.isoformat()
    else:
        next_run_iso = None

    try:
        await db.update_agent(agent_id, user_id, {"next_run_at": next_run_iso})
        logger.debug(
            "Updated next_run_at for agent %s: %s", agent_id, next_run_iso,
        )
    except Exception:
        logger.warning("Failed to update next_run_at for agent %s", agent_id)


async def update_next_run_at(agent_id: UUID, user_id: str) -> None:
    """Public wrapper — update next_run_at for an agent in the DB."""
    await _update_next_run_at(agent_id, user_id)


# ── Rehydration ──────────────────────────────────────────────────────


async def rehydrate_schedules() -> None:
    """Re-register all active agents with schedules from the DB.

    Called once at startup to restore cron jobs that were lost when the
    process was last shut down.
    """
    from engine import db

    client = db.get_client()

    try:
        resp = (
            client.table("agents")
            .select("id, user_id, schedule")
            .eq("is_active", True)
            .neq("schedule", "null")
            .execute()
        )
        agents = resp.data or []
    except Exception:
        logger.exception("Failed to query agents for schedule rehydration")
        return

    restored = 0
    for agent_row in agents:
        schedule = agent_row.get("schedule")
        if not schedule or not isinstance(schedule, str) or not schedule.strip():
            continue

        agent_id_str = agent_row["id"]
        user_id = agent_row["user_id"]

        try:
            agent_id = UUID(agent_id_str)
            register_agent(agent_id, user_id, schedule.strip())
            restored += 1
        except Exception:
            logger.warning(
                "Failed to rehydrate schedule for agent %s: %r",
                agent_id_str, schedule,
            )

    logger.info("Rehydrated %d agent schedule(s) from the database", restored)


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
