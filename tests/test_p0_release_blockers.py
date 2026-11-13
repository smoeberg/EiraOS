from __future__ import annotations

import pytest

from app.daemons.identityd import identity_step_up
from app.ipc.jsonrpc import ASSURANCE_REQUIRED, JsonRpcError


@pytest.mark.parametrize(
    "params",
    [
        {},
        {"step_up_token": "arbitrary-non-empty-string"},
        {"challenge_response": "forged-assertion", "required_assurance": "org_acting"},
        {"step_up_token": "expired-or-replayed-token", "required_assurance": "admin"},
    ],
)
def test_identity_step_up_fails_closed_without_provider_verifier(params: dict) -> None:
    with pytest.raises(JsonRpcError) as rejected:
        identity_step_up(params)

    assert rejected.value.code == ASSURANCE_REQUIRED
    assert rejected.value.message == "step_up_provider_unavailable"


def test_identity_step_up_rejects_unsupported_method() -> None:
    with pytest.raises(JsonRpcError) as rejected:
        identity_step_up({"method": "unknown_provider", "step_up_token": "anything"})

    assert rejected.value.code == ASSURANCE_REQUIRED
    assert rejected.value.message == "unsupported_step_up"

