"""Agent memory operations — read and update the per-agent memory blob."""

from __future__ import annotations

import json
import logging
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status

from engine import db

logger = logging.getLogger(__name__)

# Hard cap on serialised memory size (bytes).
MAX_MEMORY_BYTES: int = 256 * 1024  # 256 KB


async def get_memory(agent_id: UUID, user_id: str) -> dict[str, Any]:
    """Return the agent's current memory dict.

    Returns an empty dict if the agent has no stored memory yet.
    """
    agent = await db.get_agent(agent_id, user_id)
    if agent is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent {agent_id} not found",
        )
    return agent.get("memory") or {}


async def update_memory(
    agent_id: UUID, user_id: str, updates: dict[str, Any]
) -> dict[str, Any]:
    """Merge *updates* into the agent's existing memory and persist.

    Raises 413 if the resulting memory exceeds ``MAX_MEMORY_BYTES``.
    """
    current = await get_memory(agent_id, user_id)
    merged = {**current, **updates}

    serialised = json.dumps(merged)
    if len(serialised.encode()) > MAX_MEMORY_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Memory exceeds limit of {MAX_MEMORY_BYTES} bytes",
        )

    await db.update_agent(agent_id, user_id, {"memory": merged})
    logger.info("Updated memory for agent %s (%d bytes)", agent_id, len(serialised))
    return merged
