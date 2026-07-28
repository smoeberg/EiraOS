from fastapi import APIRouter
from app.models import AuditEvent
from app.services.audit_service import AuditService

router = APIRouter(prefix="/v1/audit", tags=["Audit Log"])
audit_service = AuditService()

@router.get("", response_model=list[AuditEvent])
def audit_log(limit: int = 20) -> list[AuditEvent]:
    return audit_service.get_recent_events(limit=limit)
