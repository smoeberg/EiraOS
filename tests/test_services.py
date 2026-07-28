import uuid
from app.services.audit_service import AuditService
from app.services.journey_service import JourneyService

def test_audit_service_logging():
    service = AuditService()
    test_id = f"test_id_{uuid.uuid4().hex[:8]}"
    event = service.log_event(test_id, "TEST_EVENT", {"foo": "bar"})
    assert event.id == test_id
    assert event.event_type == "TEST_EVENT"

    events = service.get_recent_events(limit=10)
    assert any(e.id == test_id for e in events)

def test_journey_service():
    service = JourneyService()
    journeys = service.get_all_journeys()
    assert isinstance(journeys, list)
