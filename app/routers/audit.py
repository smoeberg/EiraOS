from fastapi import APIRouter, HTTPException
from app.models import AuditEvent
from app.services.audit_service import AuditService

router = APIRouter(prefix="/v1/audit", tags=["Audit Log"])
audit_service = AuditService()

@router.get("", response_model=list[AuditEvent])
def audit_log(limit: int = 20) -> list[AuditEvent]:
    return audit_service.get_recent_events(limit=limit)

@router.delete("/{event_id}")
def delete_audit_log(event_id: str):
    raise HTTPException(status_code=405, detail="Audit log is append-only. Deletion not allowed.")
