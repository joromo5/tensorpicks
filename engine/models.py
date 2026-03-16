"""Pydantic models for request / response validation."""

from __future__ import annotations

import datetime as dt
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


# ── Agents ────────────────────────────────────────────────────────────


class AgentCreate(BaseModel):
    """Payload for creating a new agent from a natural-language description."""

    description: str = Field(
        ..., min_length=10, max_length=2000,
        description="Plain-English description of what the agent should do",
    )
    schedule: str | None = Field(
        default=None,
        description="Optional cron expression (e.g. '0 */4 * * *')",
    )


class AgentUpdate(BaseModel):
    """Partial update for an existing agent."""

    name: str | None = None
    description: str | None = None
    system_prompt: str | None = None
    tools: list[str] | None = None
    schedule: str | None = None
    strategy_notes: str | None = None
    memory: dict[str, Any] | None = None
    is_active: bool | None = None


class AgentResponse(BaseModel):
    """Public representation of an agent."""

    id: UUID
    user_id: str
    name: str
    description: str
    system_prompt: str
    tools: list[str]
    schedule: str | None
    strategy_notes: str | None
    memory: dict[str, Any]
    is_active: bool
    created_at: dt.datetime
    updated_at: dt.datetime


# ── API Keys ──────────────────────────────────────────────────────────


class KeyCreate(BaseModel):
    """Payload for storing a new encrypted API key."""

    service: str = Field(
        ..., min_length=1, max_length=64,
        description="Service name, e.g. 'openai', 'anthropic', 'telegram'",
    )
    api_key: str = Field(
        ..., min_length=1,
        description="Raw API key (encrypted before storage, never logged)",
    )


class KeyResponse(BaseModel):
    """Public representation of a stored key — never includes the secret."""

    id: UUID
    service: str
    hint: str = Field(description="Last 4 chars of the key for identification")
    created_at: dt.datetime


# ── Run Logs ──────────────────────────────────────────────────────────


class RunLogResponse(BaseModel):
    """Public representation of a single agent run."""

    id: UUID
    agent_id: UUID
    status: str  # "running", "success", "error"
    started_at: dt.datetime
    finished_at: dt.datetime | None
    duration_ms: int | None
    output: str | None
    error: str | None
    tokens_used: int | None


# ── User Profile ──────────────────────────────────────────────────────


class UserProfile(BaseModel):
    """Mirrors the user_profiles table."""

    id: UUID
    clerk_user_id: str
    plan: str = "free"
    display_name: str | None = None
    created_at: dt.datetime


# ── Plan enforcement ─────────────────────────────────────────────────


class PlanInfo(BaseModel):
    """Describes the limits of a billing plan."""

    max_agents: int
    max_runs_per_day: int


class PlanLimitError(BaseModel):
    """Returned when a user exceeds their plan quota."""

    detail: str
    current: int
    limit: int
