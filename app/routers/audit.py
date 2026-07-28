import json
from fastapi import APIRouter
from app.database import get_connection
from app.models import AuditEvent

router = APIRouter(prefix="/v1/audit", tags=["Audit Log"])

@router.get("", response_model=list[AuditEvent])
def audit_log(limit: int = 20) -> list[AuditEvent]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM audit_events ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [
        AuditEvent(
            id=row["id"],
            event_type=row["event_type"],
            payload=json.loads(row["payload"]),
            created_at=row["created_at"],
        )
        for row in rows
    ]
