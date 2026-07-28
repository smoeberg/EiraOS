"""EIRA IPC — JSON-RPC 2.0 over Unix domain sockets."""

from app.ipc.client import IpcClient
from app.ipc.jsonrpc import JsonRpcError, error_response, success_response
from app.ipc.paths import socket_path

__all__ = [
    "IpcClient",
    "JsonRpcError",
    "error_response",
    "success_response",
    "socket_path",
]
