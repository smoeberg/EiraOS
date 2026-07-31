"""
FastAPI Router for presenced (Object-Based Presence & Collaboration)
"""
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional
from app.daemons.presenced import PresenceDaemon

router = APIRouter(prefix="/v1/presence", tags=["Eira Presence & Object Collaboration"])
presence_daemon = PresenceDaemon()

class AnnotationRequest(BaseModel):
    object_id: str
    author: str
    comment: str
    decision_point: Optional[bool] = False

@router.post("/annotate")
def annotate_object(req: AnnotationRequest):
    return presence_daemon.annotate_object(req.object_id, req.author, req.comment, req.decision_point)

@router.get("/object/{object_id}")
def get_object_presence(object_id: str):
    return presence_daemon.get_object_presence(object_id)
