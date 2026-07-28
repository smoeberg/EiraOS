from app.services.audit_service import AuditService
from app.services.journey_service import JourneyService

def test_audit_service_logging():
    service = AuditService()
    event = service.log_event("test_id_123", "TEST_EVENT", {"foo": "bar"})
    assert event.id == "test_id_123"
    assert event.event_type == "TEST_EVENT"

    events = service.get_recent_events(limit=5)
    assert any(e.id == "test_id_123" for e in events)

def test_journey_service():
    service = JourneyService()
    journeys = service.get_all_journeys()
    assert isinstance(journeys, list)
