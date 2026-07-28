"""
HTTP dev bridge — translates REST to IPC (dev only).

Production: eira-shell (Tauri) calls Unix sockets directly.
See EIRA_Desktop_Architecture_v1.0.md §6.1 anti-pattern.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.daemons.runner import start_daemons
from app.routers import audit, auth, dashboard, fleet, graph, health, intent

@asynccontextmanager
async def lifespan(app: FastAPI):
    start_daemons()
    yield

app = FastAPI(
    title="EIRA HTTP Dev Bridge",
    description="REST → IPC bridge for React UI during development. Not for production.",
    version="0.3.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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
