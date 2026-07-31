"""
FastAPI Router for contextd (Life Context Management)
"""
from fastapi import APIRouter
from pydantic import BaseModel
from app.daemons.contextd import ContextDaemon

router = APIRouter(prefix="/v1/context", tags=["EiraOS Life Context (contextd)"])
context_daemon = ContextDaemon()

class ContextRequest(BaseModel):
    context: str

@router.post("/set")
def set_context(req: ContextRequest):
    return context_daemon.set_context(req.context)

@router.get("/current")
def get_current_context():
    return context_daemon.get_context()
