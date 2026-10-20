import uuid

import pytest

from app.auth.oidc import mock_login
from app.daemons import identityd
from app.ipc.jsonrpc import JsonRpcError
from app.session_store import ensure_session, get_session, init_db


def test_cp_oidc_session_isolation_after_sso():
    init_db()
    login_a = mock_login({"email": "a@kommune.dk", "name": "A"})
    sid_b = ensure_session(str(uuid.uuid4()), "b@kommune.dk")

    assurance_a_before = get_session(login_a["session_id"])["assurance_level"]
    assurance_b_before = get_session(sid_b)["assurance_level"]

    with pytest.raises(JsonRpcError, match="step_up_provider_unavailable"):
        identityd.identity_step_up({"session_id": login_a["session_id"], "step_up_token": "mock_token"})

    session_a = get_session(login_a["session_id"])
    session_b = get_session(sid_b)
    assert session_a["assurance_level"] == assurance_a_before
    assert session_b["assurance_level"] == assurance_b_before
