"""API key management endpoints — store, list, delete, validate."""

from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException, status

from engine.auth import get_current_user
from engine.key_vault import decrypt_key, encrypt_key
from engine.models import KeyCreate, KeyResponse
from engine import db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/keys", tags=["keys"])

# ── Validation endpoints per provider ─────────────────────────────────

_VALIDATION_URLS: dict[str, dict] = {
    "openai": {
        "url": "https://api.openai.com/v1/models",
        "auth": "Bearer",
    },
    "anthropic": {
        "url": "https://api.anthropic.com/v1/messages",
        "auth_header": "x-api-key",
        # A HEAD / lightweight call; we just check for auth errors.
    },
    "groq": {
        "url": "https://api.groq.com/openai/v1/models",
        "auth": "Bearer",
    },
}


# ── POST /keys — store key ───────────────────────────────────────────


@router.post("", status_code=status.HTTP_201_CREATED, response_model=KeyResponse)
async def add_key(body: KeyCreate, user_id: str = Depends(get_current_user)):
    """Encrypt and store an API key for a service."""
    encrypted = encrypt_key(body.api_key)
    hint = body.api_key[-4:]

    row = await db.store_api_key(user_id, body.service, encrypted, hint)
    return row


# ── GET /keys — list keys (hints only) ───────────────────────────────


@router.get("", response_model=list[KeyResponse])
async def list_keys(user_id: str = Depends(get_current_user)):
    """List stored API keys (hints only — never plaintext)."""
    return await db.list_api_keys(user_id)


# ── DELETE /keys/{service} — remove key ──────────────────────────────


@router.delete("/{service}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_key(service: str, user_id: str = Depends(get_current_user)):
    """Remove an API key for a service."""
    deleted = await db.delete_api_key(user_id, service)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"No key found for '{service}'")


# ── POST /keys/{service}/validate — test key ─────────────────────────


@router.post("/{service}/validate")
async def validate_key(service: str, user_id: str = Depends(get_current_user)):
    """Test whether a stored API key is valid by making a lightweight API call."""
    row = await db.get_api_key(user_id, service)
    if row is None:
        raise HTTPException(status_code=404, detail=f"No key found for '{service}'")

    raw_key = decrypt_key(row["encrypted_key"])

    config = _VALIDATION_URLS.get(service)
    if config is None:
        return {"valid": True, "note": f"No validation endpoint configured for '{service}'"}

    headers: dict[str, str] = {}
    if "auth" in config:
        headers["Authorization"] = f"{config['auth']} {raw_key}"
    if "auth_header" in config:
        headers[config["auth_header"]] = raw_key

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(config["url"], headers=headers)

        if resp.status_code in (200, 201):
            return {"valid": True, "service": service}
        elif resp.status_code in (401, 403):
            return {"valid": False, "service": service, "detail": "Authentication failed"}
        else:
            return {
                "valid": False,
                "service": service,
                "detail": f"Unexpected status {resp.status_code}",
            }
    except httpx.HTTPError as exc:
        logger.warning("Key validation request failed for %s: %s", service, exc)
        return {"valid": False, "service": service, "detail": str(exc)}
