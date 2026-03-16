"""Run log endpoints — view execution history."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from engine.auth import get_current_user
from engine.models import RunLogResponse
from engine import db

router = APIRouter(tags=["runs"])


# ── GET /agents/{id}/runs — list runs for agent ──────────────────────


@router.get("/agents/{agent_id}/runs", response_model=list[RunLogResponse])
async def list_runs(
    agent_id: UUID,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user_id: str = Depends(get_current_user),
):
    """List execution history for a specific agent."""
    # Verify the agent belongs to the user
    agent = await db.get_agent(agent_id, user_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")

    return await db.list_run_logs(agent_id, user_id, limit=limit, offset=offset)


# ── GET /runs/{id} — run detail ──────────────────────────────────────


@router.get("/runs/{run_id}", response_model=RunLogResponse)
async def get_run(run_id: UUID, user_id: str = Depends(get_current_user)):
    """Get full details for a single run."""
    run = await db.get_run_log(run_id, user_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return run
