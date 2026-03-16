"""Application configuration loaded from environment variables."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Central configuration for the engine microservice.

    All values are read from environment variables (or a .env file at the
    project root).  Secrets should NEVER be committed — use .env.local or
    a vault in production.
    """

    # ── Supabase ──────────────────────────────────────────────────────
    SUPABASE_URL: str = Field(..., description="Supabase project URL")
    SUPABASE_SERVICE_ROLE_KEY: str = Field(
        ..., description="Supabase service-role key (bypasses RLS)"
    )

    # ── Encryption ────────────────────────────────────────────────────
    FERNET_KEY: str = Field(
        ..., description="Fernet symmetric key for encrypting user API keys"
    )

    # ── Clerk (JWT auth) ──────────────────────────────────────────────
    CLERK_ISSUER: str = Field(
        default="https://clerk.your-domain.com",
        description="Clerk JWT issuer URL (used to fetch JWKS)",
    )

    # ── Stripe ─────────────────────────────────────────────────────────
    STRIPE_SECRET_KEY: str = Field(
        default="",
        description="Stripe secret API key (sk_live_... or sk_test_...)",
    )
    STRIPE_WEBHOOK_SECRET: str = Field(
        default="",
        description="Stripe webhook signing secret (whsec_...)",
    )
    STRIPE_PRICE_IDS: dict[str, str] = Field(
        default={
            "starter": "price_starter_placeholder",
            "pro": "price_pro_placeholder",
            "agency": "price_agency_placeholder",
        },
        description="Mapping of plan names to Stripe Price IDs",
    )

    # ── CORS ──────────────────────────────────────────────────────────
    CORS_ORIGINS: list[str] = Field(
        default=["http://localhost:3000"],
        description="Allowed CORS origins (Next.js frontend)",
    )

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": True,
    }


# Singleton — import this everywhere instead of re-instantiating.
settings = Settings()  # type: ignore[call-arg]
