"""Desktop login → a session the gate accepts (GATE-KERNEL bilag A pkt. 1).

    identity.login_start      → authorize URL (Entra, PKCE + nonce)
    identity.login_complete   → verified claims → session bound to the OS user

Who is logging in is taken from two sources that must agree:

- the kernel's `loginuid` of the calling process — set by PAM when the
  user's login session began, inherited by everything in it, and not
  changeable by an unprivileged process; and
- `SO_PEERCRED` of the IPC connection.

The peer alone is not enough: a greeter, a PAM helper or a setuid tool would
be the peer, not the user. `loginuid` alone is not enough either: it says
whose login session a process belongs to, not who is on the socket.

Only these two methods create sessions the gate accepts. A login is bound
to the uid that started it: another user can neither complete nor consume
it. Mock login exists only off an installed system.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.auth import oidc
from app.ipc.auth import PEER_KEY
from app.ipc.jsonrpc import JsonRpcError
from app.session_store import create_session_from_claims, get_session

LOGIN_FAILED = -32021
UNSET_LOGINUID = 4294967295


def login_uid(pid: int, proc: Path = Path("/proc")) -> int | None:
    try:
        value = int((proc / str(pid) / "loginuid").read_text().strip())
    except (OSError, ValueError):
        return None
    return None if value == UNSET_LOGINUID else value


def caller_uid(params: dict[str, Any]) -> int:
    """The uid of the user on the socket, proven by peer and loginuid."""
    peer = params.pop(PEER_KEY, None)
    if peer is None:
        raise JsonRpcError(LOGIN_FAILED, "login_requires_socket_peer")
    loginuid = login_uid(peer.pid)
    if loginuid is None:
        raise JsonRpcError(LOGIN_FAILED, "caller_not_in_a_login_session")
    if loginuid != peer.uid:
        raise JsonRpcError(LOGIN_FAILED, "loginuid_does_not_match_peer")
    if peer.uid < 1000:
        raise JsonRpcError(LOGIN_FAILED, "system_users_do_not_log_in")
    return peer.uid


def login_start(params: dict[str, Any]) -> dict[str, Any]:
    """The desktop app passes its loopback redirect (RFC 8252); it is
    validated, stored with the state and reused for the token exchange."""
    uid = caller_uid(params)
    redirect_uri = params.get("redirect_uri")
    if not isinstance(redirect_uri, str):
        raise JsonRpcError(-32602, "redirect_uri is required")
    try:
        return oidc.start_oidc_login(os_uid=uid, redirect_uri=redirect_uri)
    except ValueError as exc:
        raise JsonRpcError(-32602, str(exc)) from None
    except PermissionError as exc:  # mock mode on an installed system
        raise JsonRpcError(LOGIN_FAILED, "live_login_unavailable", {"detail": str(exc)}) from None


def login_complete(params: dict[str, Any]) -> dict[str, Any]:
    uid = caller_uid(params)
    state, code = params.get("state"), params.get("code")
    if not isinstance(state, str) or not isinstance(code, str) or not state or not code:
        raise JsonRpcError(-32602, "state and code are required")
    found = oidc.pop_login_state(state, os_uid=uid)
    if found is None:
        oidc.fail_oidc_login("invalid_state", detail={"mode": "desktop"})
        raise JsonRpcError(LOGIN_FAILED, "invalid_or_expired_state")
    verifier, nonce = found["code_verifier"], found["nonce"]
    if not nonce:
        raise JsonRpcError(LOGIN_FAILED, "login_without_nonce")
    try:
        tokens = oidc.exchange_code_for_tokens(code, verifier, redirect_uri=found["redirect_uri"])
        id_token = tokens.get("id_token")
        if not id_token:
            raise ValueError("token response missing id_token")
        claims = oidc.claims_from_id_token(id_token, nonce=nonce)
    except (ValueError, OSError) as exc:
        oidc.fail_oidc_login(str(exc), detail={"mode": "desktop"})
        raise JsonRpcError(LOGIN_FAILED, "login_failed", {"detail": str(exc)}) from None
    sid = create_session_from_claims(claims, os_uid=uid)
    oidc.record_auth_event("auth.login.success", {
        "session_id": sid, "identity": claims["identity"], "os_uid": uid, "mode": "desktop",
        "tenant_id": claims.get("tenant_id"),
    })
    session = get_session(sid) or {}
    return {"session_id": sid, "identity": claims["identity"], "expires_at": session.get("expires_at")}


def wants_peer(handler):
    handler.wants_peer = True
    return handler
