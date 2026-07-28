from __future__ import annotations

import os

from app.ipc.jsonrpc import JsonRpcError

AUTH_FAILED = -32010
EIRA_META_KEY = "_eira"


def expected_ipc_token() -> str | None:
    token = os.environ.get("EIRA_IPC_TOKEN", "").strip()
    return token or None


def strip_and_validate_ipc_auth(params: dict) -> dict:
    """Validate optional IPC token; return params without _eira metadata."""
    meta = params.pop(EIRA_META_KEY, None) or {}
    expected = expected_ipc_token()
    if expected:
        provided = meta.get("ipc_token", "")
        if provided != expected:
            raise JsonRpcError(
                AUTH_FAILED,
                "ipc_auth_failed",
                {"user_message": "Ugyldig IPC-token"},
            )
    return params
