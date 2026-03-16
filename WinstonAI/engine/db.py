"""Supabase client wrapper with RLS-aware helpers."""

from __future__ import annotations

import json
import logging
from typing import Any
from uuid import UUID

from supabase import Client, create_client

from engine.config import settings

logger = logging.getLogger(__name__)

# ── Client singleton ──────────────────────────────────────────────────

_client: Client | None = None


def get_client() -> Client:
    """Return (and lazily create) the Supabase service-role client."""
    global _client
    if _client is None:
        _client = create_client(
            settings.SUPABASE_URL,
            settings.SUPABASE_SERVICE_ROLE_KEY,
        )
    return _client


# ── RLS helper ────────────────────────────────────────────────────────


async def set_rls_claims(client: Client, user_id: str) -> None:
    """Inject JWT claims so Postgres RLS policies see the calling user.

    This sets a session-local variable that our RLS policies reference via
    ``current_setting('request.jwt.claims', true)::json->>'sub'``.
    """
    claims = json.dumps({"sub": user_id})
    client.postgrest.auth(
        token=settings.SUPABASE_SERVICE_ROLE_KEY,
        headers={"x-supabase-claims": claims},
    )
    # For direct SQL via rpc, set the local variable explicitly.
    try:
        client.rpc(
            "set_claim",
            {"claim": json.dumps({"sub": user_id})},
        ).execute()
    except Exception:
        # If the RPC doesn't exist yet, RLS will rely on the service-role
        # bypass.  Log but don't crash.
        logger.debug("set_claim RPC unavailable — falling back to service-role")


# ── CRUD: user_profiles ──────────────────────────────────────────────


async def get_user_profile(clerk_user_id: str) -> dict[str, Any] | None:
    """Fetch a user profile by Clerk user ID."""
    resp = (
        get_client()
        .table("user_profiles")
        .select("*")
        .eq("clerk_user_id", clerk_user_id)
        .maybe_single()
        .execute()
    )
    return resp.data


async def upsert_user_profile(clerk_user_id: str, **fields: Any) -> dict[str, Any]:
    """Create or update a user profile."""
    payload = {"clerk_user_id": clerk_user_id, **fields}
    resp = (
        get_client()
        .table("user_profiles")
        .upsert(payload, on_conflict="clerk_user_id")
        .execute()
    )
    return resp.data[0]


# ── CRUD: agents ──────────────────────────────────────────────────────


async def create_agent(data: dict[str, Any]) -> dict[str, Any]:
    resp = get_client().table("agents").insert(data).execute()
    return resp.data[0]


async def list_agents(user_id: str, include_archived: bool = False) -> list[dict[str, Any]]:
    query = get_client().table("agents").select("*").eq("user_id", user_id)
    if not include_archived:
        query = query.eq("is_active", True)
    query = query.order("created_at", desc=True)
    return query.execute().data


async def get_agent(agent_id: UUID, user_id: str) -> dict[str, Any] | None:
    resp = (
        get_client()
        .table("agents")
        .select("*")
        .eq("id", str(agent_id))
        .eq("user_id", user_id)
        .maybe_single()
        .execute()
    )
    return resp.data


async def update_agent(agent_id: UUID, user_id: str, data: dict[str, Any]) -> dict[str, Any]:
    resp = (
        get_client()
        .table("agents")
        .update(data)
        .eq("id", str(agent_id))
        .eq("user_id", user_id)
        .execute()
    )
    if not resp.data:
        raise ValueError(f"Agent {agent_id} not found or not owned by user")
    return resp.data[0]


async def soft_delete_agent(agent_id: UUID, user_id: str) -> dict[str, Any]:
    return await update_agent(agent_id, user_id, {"is_active": False})


# ── CRUD: api_keys ────────────────────────────────────────────────────


async def store_api_key(user_id: str, service: str, encrypted: str, hint: str) -> dict[str, Any]:
    payload = {
        "user_id": user_id,
        "service": service,
        "encrypted_key": encrypted,
        "hint": hint,
    }
    resp = (
        get_client()
        .table("api_keys")
        .upsert(payload, on_conflict="user_id,service")
        .execute()
    )
    return resp.data[0]


async def list_api_keys(user_id: str) -> list[dict[str, Any]]:
    resp = (
        get_client()
        .table("api_keys")
        .select("id, service, hint, created_at")
        .eq("user_id", user_id)
        .execute()
    )
    return resp.data


async def get_api_key(user_id: str, service: str) -> dict[str, Any] | None:
    resp = (
        get_client()
        .table("api_keys")
        .select("*")
        .eq("user_id", user_id)
        .eq("service", service)
        .maybe_single()
        .execute()
    )
    return resp.data


async def delete_api_key(user_id: str, service: str) -> bool:
    resp = (
        get_client()
        .table("api_keys")
        .delete()
        .eq("user_id", user_id)
        .eq("service", service)
        .execute()
    )
    return len(resp.data) > 0


# ── CRUD: run_logs ────────────────────────────────────────────────────


async def create_run_log(data: dict[str, Any]) -> dict[str, Any]:
    resp = get_client().table("run_logs").insert(data).execute()
    return resp.data[0]


async def update_run_log(run_id: UUID, data: dict[str, Any]) -> dict[str, Any]:
    resp = (
        get_client()
        .table("run_logs")
        .update(data)
        .eq("id", str(run_id))
        .execute()
    )
    return resp.data[0]


async def list_run_logs(
    agent_id: UUID, user_id: str, limit: int = 50, offset: int = 0
) -> list[dict[str, Any]]:
    resp = (
        get_client()
        .table("run_logs")
        .select("*")
        .eq("agent_id", str(agent_id))
        .eq("user_id", user_id)
        .order("started_at", desc=True)
        .range(offset, offset + limit - 1)
        .execute()
    )
    return resp.data


async def get_run_log(run_id: UUID, user_id: str) -> dict[str, Any] | None:
    resp = (
        get_client()
        .table("run_logs")
        .select("*")
        .eq("id", str(run_id))
        .eq("user_id", user_id)
        .maybe_single()
        .execute()
    )
    return resp.data


async def count_runs_today(user_id: str) -> int:
    """Count how many runs the user has triggered today (UTC)."""
    from datetime import datetime, timezone

    today = datetime.now(timezone.utc).strftime("%Y-%m-%dT00:00:00+00:00")
    resp = (
        get_client()
        .table("run_logs")
        .select("id", count="exact")
        .eq("user_id", user_id)
        .gte("started_at", today)
        .execute()
    )
    return resp.count or 0


# ── CRUD: bot_connections ─────────────────────────────────────────────


async def get_bot_connections(user_id: str) -> list[dict[str, Any]]:
    resp = (
        get_client()
        .table("bot_connections")
        .select("*")
        .eq("user_id", user_id)
        .execute()
    )
    return resp.data


async def upsert_bot_connection(
    user_id: str, platform: str, config: dict[str, Any]
) -> dict[str, Any]:
    payload = {"user_id": user_id, "platform": platform, "config": config}
    resp = (
        get_client()
        .table("bot_connections")
        .upsert(payload, on_conflict="user_id,platform")
        .execute()
    )
    return resp.data[0]
