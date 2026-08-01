import uuid
from app.session_store import ensure_session, get_session
from app.daemons import identityd
from app.auth.oidc import mock_login

def test_cp_oidc_session_isolation_after_sso():
    login_a = mock_login({"email": "a@kommune.dk", "name": "A"})
    sid_b = ensure_session(str(uuid.uuid4()), "b@kommune.dk")

    identityd.identity_step_up({"session_id": login_a["session_id"], "step_up_token": "mock_token"})
    session_b = get_session(sid_b)
    assert session_b["assurance_level"] == "eid_low"
