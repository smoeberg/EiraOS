from __future__ import annotations

import json
import os
from typing import Any

from app.ipc.jsonrpc import JsonRpcError
from app.ipc.transport import connect_socket, use_unix_sockets
from app.ipc.paths import socket_path


class IpcClient:
    def __init__(self, daemon: str, timeout: float = 10.0):
        self.daemon = daemon
        self.timeout = timeout

    def call(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        *,
        session_id: str | None = None,
    ) -> Any:
        payload_params = dict(params or {})
        if session_id and "session_id" not in payload_params:
            payload_params["session_id"] = session_id

        token = os.environ.get("EIRA_IPC_TOKEN", "").strip()
        if token:
            payload_params["_eira"] = {"ipc_token": token}

        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": method,
            "params": payload_params,
        }
        body = (json.dumps(request) + "\n").encode("utf-8")

        with connect_socket(self.daemon, self.timeout) as sock:
            sock.sendall(body)
            chunks: list[bytes] = []
            while True:
                chunk = sock.recv(65536)
                if not chunk:
                    break
                chunks.append(chunk)
                if b"\n" in chunk:
                    break

        line = b"".join(chunks).split(b"\n", 1)[0]
        response = json.loads(line.decode("utf-8"))

        if "error" in response:
            err = response["error"]
            raise JsonRpcError(
                err.get("code", -32603),
                err.get("message", "unknown"),
                err.get("data"),
            )
        return response.get("result")
