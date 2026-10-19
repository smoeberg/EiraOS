from __future__ import annotations

from typing import Any


class JsonRpcError(Exception):
    def __init__(
        self, code: int, message: str, data: dict[str, Any] | None = None
    ) -> None:
        self.code = code
        self.message = message
        self.data = data or {}
        super().__init__(message)


def success_response(req_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _default_user_message(code: int, message: str) -> str:
    if code == -32600:
        return "Forespørgslen er ugyldig."
    if code == -32601:
        return "Handlingen findes ikke."
    if code == -32602:
        return "Forespørgslen indeholder ugyldige oplysninger."
    if code == -32603:
        return "Der opstod en intern fejl. Prøv igen senere."
    return message or "Handlingen kunne ikke gennemføres."


def error_response(
    req_id: Any,
    code: int,
    message: str,
    data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    error_data = dict(data or {})
    if not isinstance(error_data.get("user_message"), str) or not error_data["user_message"].strip():
        error_data["user_message"] = _default_user_message(code, message)
    payload: dict[str, Any] = {
        "code": code,
        "message": message,
        "data": error_data,
    }
    return {"jsonrpc": "2.0", "id": req_id, "error": payload}


METHOD_NOT_FOUND = -32601
INVALID_REQUEST = -32600
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603
ASSURANCE_REQUIRED = -32001
CONSTRAINT_VIOLATION = -32001
PEER_AUTH_FAILED = -32011
