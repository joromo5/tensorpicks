"""JWT validation against Clerk's JWKS endpoint."""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from engine.config import settings

logger = logging.getLogger(__name__)

_bearer_scheme = HTTPBearer()

# ── JWKS cache ────────────────────────────────────────────────────────

_jwks_cache: dict[str, Any] | None = None
_jwks_fetched_at: float = 0.0
_JWKS_TTL_SECONDS: int = 3600  # re-fetch once per hour


async def _fetch_jwks() -> dict[str, Any]:
    """Fetch the JSON Web Key Set from Clerk's well-known endpoint."""
    global _jwks_cache, _jwks_fetched_at

    now = time.monotonic()
    if _jwks_cache is not None and (now - _jwks_fetched_at) < _JWKS_TTL_SECONDS:
        return _jwks_cache

    url = f"{settings.CLERK_ISSUER}/.well-known/jwks.json"
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        _jwks_cache = resp.json()
        _jwks_fetched_at = now
        logger.info("Refreshed JWKS from %s", url)
        return _jwks_cache


def _get_signing_key(jwks: dict[str, Any], token: str) -> dict[str, Any]:
    """Find the key in the JWKS that matches the token's kid header."""
    unverified_header = jwt.get_unverified_header(token)
    kid = unverified_header.get("kid")
    if not kid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="JWT missing kid header",
        )

    for key in jwks.get("keys", []):
        if key.get("kid") == kid:
            return key

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=f"No matching JWKS key for kid={kid}",
    )


async def validate_token(token: str) -> dict[str, Any]:
    """Validate a Clerk-issued JWT and return its decoded claims."""
    jwks = await _fetch_jwks()
    signing_key = _get_signing_key(jwks, token)

    try:
        payload = jwt.decode(
            token,
            signing_key,
            algorithms=["RS256"],
            issuer=settings.CLERK_ISSUER,
            options={"verify_aud": False},  # Clerk tokens may omit audience
        )
    except JWTError as exc:
        logger.warning("JWT validation failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        ) from exc

    return payload


# ── FastAPI dependency ────────────────────────────────────────────────


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
) -> str:
    """Dependency that extracts and validates the Clerk user ID.

    Returns the ``sub`` claim (clerk_user_id) from a valid JWT.
    """
    payload = await validate_token(credentials.credentials)
    user_id: str | None = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing sub claim",
        )
    return user_id
