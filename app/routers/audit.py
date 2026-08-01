from fastapi import APIRouter, Header, HTTPException
from app.models import AuditEvent
from app.services.audit_service import AuditService
from app.session_store import get_session

router = APIRouter(prefix="/v1/audit", tags=["Audit Log"])
audit_service = AuditService()


@router.get("", response_model=list[AuditEvent])
def audit_log(
    limit: int = 20,
    x_eira_session_id: str | None = Header(default=None, alias="X-EIRA-Session-Id")
) -> list[AuditEvent]:
    if not x_eira_session_id or not get_session(x_eira_session_id):
        raise HTTPException(status_code=401, detail="Session header X-EIRA-Session-Id is missing or invalid.")
    return audit_service.get_recent_events(limit=limit)


@router.delete("/{event_id}")
def delete_audit_log(event_id: str):
    raise HTTPException(status_code=405, detail="Audit log is append-only. Deletion not allowed.")
