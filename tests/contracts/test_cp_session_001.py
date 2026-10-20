import uuid

import pytest

from app.daemons import identityd
from app.ipc.jsonrpc import JsonRpcError
from app.session_store import ensure_session, get_session, init_db


def test_cp_session_s1_step_up_isolation():
    init_db()
    sid_a = ensure_session(str(uuid.uuid4()), "a@test.dk")
    sid_b = ensure_session(str(uuid.uuid4()), "b@test.dk")

    with pytest.raises(JsonRpcError, match="step_up_provider_unavailable"):
        identityd.identity_step_up({"session_id": sid_a, "step_up_token": "mock_token"})
    session_a = get_session(sid_a)
    session_b = get_session(sid_b)
    assert session_a["assurance_level"] == "eid_low"
    assert session_b["assurance_level"] == "eid_low"

def test_cp_identity_s1_isolated_step_up():
    init_db()
    sid_a = str(uuid.uuid4())
    sid_b = str(uuid.uuid4())
    ensure_session(sid_a)
    ensure_session(sid_b)

    with pytest.raises(JsonRpcError, match="step_up_provider_unavailable"):
        identityd.identity_step_up({"session_id": sid_a, "step_up_token": "mock_token"})
    session_a = get_session(sid_a)
    session_b = get_session(sid_b)
    assert session_a["assurance_level"] == "eid_low"
    assert session_b["assurance_level"] == "eid_low"
