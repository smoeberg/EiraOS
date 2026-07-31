"""
FastAPI Router for capabilityd (Capability & Policy Routing)
"""
from fastapi import APIRouter
from pydantic import BaseModel
from app.daemons.capabilityd import CapabilityDaemon

router = APIRouter(prefix="/v1/capability", tags=["EiraOS Capability Engine (capabilityd)"])
capability_daemon = CapabilityDaemon()

class ResolveCapabilityRequest(BaseModel):
    capability: str  # e.g., 'capability:reasoning', 'capability:translation'
    security_level: str  # 'public', 'internal', 'confidential', 'restricted'

@router.post("/resolve")
def resolve_capability(req: ResolveCapabilityRequest):
    return capability_daemon.resolve_and_dispatch(req.capability, req.security_level)
