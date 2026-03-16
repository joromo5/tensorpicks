"""Fernet-based encryption for user API keys.

Security notes:
- Raw keys are NEVER logged or included in error messages.
- The FERNET_KEY must be a valid 32-byte URL-safe base64 key.
"""

from __future__ import annotations

import logging
from uuid import UUID

from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException, status

from engine.config import settings

logger = logging.getLogger(__name__)

# ── Fernet instance (created once) ───────────────────────────────────

_fernet: Fernet | None = None


def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is None:
        _fernet = Fernet(settings.FERNET_KEY.encode())
    return _fernet


# ── Public API ────────────────────────────────────────────────────────


def encrypt_key(raw: str) -> str:
    """Encrypt a plaintext API key and return a base64-encoded ciphertext."""
    return _get_fernet().encrypt(raw.encode()).decode()


def decrypt_key(encrypted: str) -> str:
    """Decrypt a previously encrypted key back to plaintext."""
    try:
        return _get_fernet().decrypt(encrypted.encode()).decode()
    except InvalidToken:
        logger.error("Failed to decrypt key — invalid token or wrong FERNET_KEY")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not decrypt stored key",
        )


async def get_user_key(user_id: str, service: str) -> str:
    """Fetch the encrypted key from the DB, decrypt, and return it.

    Raises 404 if the user has no key stored for the given service.
    """
    from engine.db import get_api_key  # deferred to avoid circular import

    row = await get_api_key(user_id, service)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No API key stored for service '{service}'",
        )
    return decrypt_key(row["encrypted_key"])
