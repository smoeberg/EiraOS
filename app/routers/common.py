from __future__ import annotations

from fastapi import HTTPException
from app.ipc.client import IpcClient
from app.ipc.jsonrpc import JsonRpcError

intent_ipc = IpcClient("intent")
identity_ipc = IpcClient("identity")
graph_ipc = IpcClient("graph")
fleet_ipc = IpcClient("fleet")

def sid(header: str | None) -> str | None:
    return header.strip() if header else None

def ipc_http(exc: Exception) -> HTTPException:
    if isinstance(exc, JsonRpcError):
        return HTTPException(
            status_code=400,
            detail={
                "code": exc.code,
                "message": exc.message,
                "data": exc.data,
            },
        )
    if isinstance(exc, ConnectionError):
        return HTTPException(status_code=503, detail=str(exc))
    raise exc
