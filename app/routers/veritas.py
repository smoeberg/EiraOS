"""
FastAPI Router for Veritas Shield & eira-veritasd Daemon
Endpoints:
  - POST /v1/veritas/evidence (Universal Evidence Validation)
  - POST /v1/veritas/validate-text
  - POST /v1/veritas/validate-image
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any
from app.daemons.veritasd import VeritasDaemon

router = APIRouter(prefix="/v1/veritas", tags=["Veritas Shield & Trust Engine"])
veritas_daemon = VeritasDaemon()

class UniversalEvidenceRequest(BaseModel):
    type: str  # 'text', 'image', 'pdf', 'video', 'audio'
    title: Optional[str] = ""
    text: Optional[str] = ""
    url: Optional[str] = ""
    issuer: Optional[str] = None

@router.post("/evidence")
def validate_evidence(req: UniversalEvidenceRequest):
    data = req.dict()
    return veritas_daemon.process_evidence(data)

@router.post("/validate-text")
def validate_text(req: UniversalEvidenceRequest):
    data = req.dict()
    data["type"] = "text"
    return veritas_daemon.process_evidence(data)

@router.post("/validate-image")
def validate_image(req: UniversalEvidenceRequest):
    data = req.dict()
    data["type"] = "image"
    return veritas_daemon.process_evidence(data)
