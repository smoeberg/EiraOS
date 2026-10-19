from __future__ import annotations

import json

import pytest

from app.daemons.base import JsonRpcServer
from app.daemons.runner import DAEMON_NAMES, REGISTRARS
from app.ipc.jsonrpc import JsonRpcError
from app.ipc.paths import canonical_daemon, socket_path
from app.ipc.socket_security import socket_access_allowed


@pytest.fixture
def server() -> JsonRpcServer:
    instance = JsonRpcServer(name="test-jsonrpc", daemon="stated")
    instance.register("test.echo", lambda params: params)
    return instance


def _response(server: JsonRpcServer, payload: str) -> dict:
    return json.loads(server.handle_line(payload))


@pytest.mark.parametrize(
    "request_payload",
    [
        '{"id":1,"method":"test.echo","params":{}}',
        '{"jsonrpc":"1.0","id":1,"method":"test.echo","params":{}}',
        '{"jsonrpc":"2.0","method":"test.echo","params":{}}',
        '{"jsonrpc":"2.0","id":null,"method":"test.echo","params":{}}',
        '{"jsonrpc":"2.0","id":true,"method":"test.echo","params":{}}',
        '{"jsonrpc":"2.0","id":[],"method":"test.echo","params":{}}',
        '{"jsonrpc":"2.0","id":{},"method":"test.echo","params":{}}',
    ],
)
def test_invalid_jsonrpc_requests_are_rejected_with_user_message(
    server: JsonRpcServer, request_payload: str
) -> None:
    response = _response(server, request_payload)
    assert "error" in response
    assert response["error"]["data"]["user_message"]


@pytest.mark.parametrize("request_id", ["request-1", 0, 12.5])
def test_string_and_numeric_request_ids_are_accepted(
    server: JsonRpcServer, request_id: str | int | float
) -> None:
    response = _response(
        server,
        json.dumps(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": "test.echo",
                "params": {"ok": True},
            }
        ),
    )
    assert response["id"] == request_id
    assert response["result"] == {"ok": True}


@pytest.mark.parametrize(
    "payload",
    [
        "{not-json",
        '{"jsonrpc":"2.0","id":2,"method":"missing.method","params":{}}',
        '{"jsonrpc":"2.0","id":2,"method":"test.echo","params":[]}',
    ],
)
def test_every_error_response_has_user_message(
    server: JsonRpcServer, payload: str
) -> None:
    response = _response(server, payload)
    assert response["error"]["data"]["user_message"].strip()


def test_runner_registers_nine_daemons_and_socket_names() -> None:
    assert len(DAEMON_NAMES) == 9
    assert set(DAEMON_NAMES) == set(REGISTRARS)
    for daemon in ("walletd", "presenced", "contextd"):
        assert canonical_daemon(daemon) == daemon
        assert socket_path(daemon).name == f"{daemon}.sock"


def test_non_allowlisted_non_root_peer_is_denied() -> None:
    assert socket_access_allowed(
        object(), allowed_uids={1001}, allowed_gids={2001}, uid=1001, gids={3001}
    )
    assert socket_access_allowed(
        object(), allowed_uids={1001}, allowed_gids={2001}, uid=3001, gids={2001}
    )
    assert not socket_access_allowed(
        object(), allowed_uids={1001}, allowed_gids={2001}, uid=3001, gids={3001}
    )



def test_all_nine_daemons_answer_health_over_ipc(tmp_path, monkeypatch) -> None:
    from app.daemons.runner import start_daemons, stop_daemons
    from app.ipc.client import IpcClient

    stop_daemons()
    monkeypatch.setenv("EIRA_RUN_DIR", str(tmp_path))
    try:
        started = start_daemons("all", socket_dir=tmp_path)
        assert set(started) == set(DAEMON_NAMES)
        for daemon in DAEMON_NAMES:
            health = IpcClient(daemon).call("health")
            assert health["ok"] is True

        with pytest.raises(JsonRpcError) as exc_info:
            IpcClient("identity").call(
                "identity.step_up", {"required_assurance": "org_acting"}
            )
        assert exc_info.value.data["user_message"]
    finally:
        stop_daemons()
