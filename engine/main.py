"""FastAPI application — entry point for the TensorPicks engine."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from engine.agent_manager import shutdown_scheduler, start_scheduler
from engine.config import settings
from engine.routers import agents, keys, runs

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


# ── Lifespan ──────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Startup and shutdown hooks."""
    logger.info("Engine starting up")
    start_scheduler()
    # TODO: re-register scheduled agents from DB on startup
    yield
    logger.info("Engine shutting down")
    shutdown_scheduler()


# ── App ───────────────────────────────────────────────────────────────

app = FastAPI(
    title="TensorPicks Engine",
    description="AI agent microservice — manages, schedules, and runs autonomous agents.",
    version="0.1.0",
    lifespan=lifespan,
)

# ── CORS ──────────────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────

app.include_router(agents.router)
app.include_router(keys.router)
app.include_router(runs.router)


# ── Health check ──────────────────────────────────────────────────────


@app.get("/health", tags=["infra"])
async def health_check():
    """Lightweight liveness probe."""
    return {"status": "ok", "service": "tensorpicks-engine"}
