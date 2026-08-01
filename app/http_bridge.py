"""
HTTP dev bridge — translates REST to IPC (dev only).

Production: eira-shell (Tauri) calls Unix sockets directly.
See EIRA_Desktop_Architecture_v1.0.md §6.1 anti-pattern.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from app.daemons.runner import start_daemons
from app.routers import (
    audit,
    auth,
    capability,
    context,
    dashboard,
    fleet,
    graph,
    health,
    intent,
    presence,
    veritas,
    wallet,
)

limiter = Limiter(key_func=get_remote_address, default_limits=["100/minute"])

@asynccontextmanager
async def lifespan(app: FastAPI):
    if os.environ.get("EIRA_DISABLE_DAEMONS") != "1":
        start_daemons()
    yield

app = FastAPI(
    title="EIRA HTTP Dev Bridge",
    description="REST → IPC bridge for React UI during development. Not for production.",
    version="0.3.0",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

allowed_origins = os.environ.get("ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(dashboard.router)
app.include_router(intent.router)
app.include_router(auth.router)
app.include_router(fleet.router)
app.include_router(graph.router)
app.include_router(audit.router)
app.include_router(veritas.router)
app.include_router(wallet.router)
app.include_router(presence.router)
app.include_router(capability.router)
app.include_router(context.router)
