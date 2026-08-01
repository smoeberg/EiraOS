from __future__ import annotations

import hmac
import os

from app.ipc.jsonrpc import JsonRpcError

AUTH_FAILED = -32010
EIRA_META_KEY = "_eira"


def expected_ipc_token() -> str | None:
    token = os.environ.get("EIRA_IPC_TOKEN", "").strip()
    return token or None


def strip_and_validate_ipc_auth(params: dict) -> dict:
    meta = params.pop(EIRA_META_KEY, None) or {}
    if not isinstance(meta, dict):
        raise JsonRpcError(
            AUTH_FAILED,
            "ipc_auth_failed",
            {"user_message": "Ugyldig IPC-metadata"},
        )
    expected = expected_ipc_token()
    supplied = meta.get("ipc_token", "")
    if not isinstance(supplied, str):
        supplied = ""
    if expected and not hmac.compare_digest(supplied.encode(), expected.encode()):
        raise JsonRpcError(
            AUTH_FAILED,
            "ipc_auth_failed",
            {"user_message": "Ugyldig IPC-token"},
        )
    return params
