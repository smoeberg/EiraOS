#!/usr/bin/env python3
"""EIRA OS: IPC Unix Socket Smoke Test CLI Tool.

Verifies connectivity and health status of EiraOS daemons over Unix Domain Sockets.
"""

import sys
import os
import socket
import json
import argparse
from typing import List, Tuple

GREEN = "\033[92m"
RED = "\033[91m"
RESET = "\033[0m"


def test_socket(socket_path: str) -> Tuple[bool, str]:
    if not os.path.exists(socket_path):
        return False, f"Socket file does not exist: {socket_path}"

    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(3.0)
        sock.connect(socket_path)

        request_payload = json.dumps({"jsonrpc": "2.0", "method": "health", "params": {}, "id": 1}) + "\n"
        sock.sendall(request_payload.encode("utf-8"))

        raw_response = b""
        while True:
            chunk = sock.recv(1024)
            if not chunk:
                break
            raw_response += chunk
            if b"\n" in chunk:
                break

        sock.close()

        if not raw_response:
            return False, "Empty response received from socket"

        data = json.loads(raw_response.decode("utf-8"))
        if "result" in data and isinstance(data["result"], dict) and data["result"].get("ok") is True:
            daemon_name = data["result"].get("daemon", os.path.basename(socket_path))
            return True, f"Daemon '{daemon_name}' is healthy (ok: True)"
        elif "error" in data:
            return False, f"RPC Error: {data['error'].get('message', 'Unknown error')}"
        else:
            return False, f"Invalid JSON-RPC response payload: {data}"

    except Exception as exc:
        return False, f"Socket connection failed: {str(exc)}"


def discover_sockets(target_path: str) -> List[str]:
    if os.path.isfile(target_path):
        return [target_path]
    elif os.path.isdir(target_path):
        sockets = []
        for entry in os.listdir(target_path):
            if entry.endswith(".sock"):
                sockets.append(os.path.join(target_path, entry))
        return sorted(sockets)
    return []


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke test EiraOS Unix Domain Socket daemons.")
    parser.add_argument("target", nargs="?", default="/run/eira", help="Socket directory or file path (default: /run/eira)")
    args = parser.parse_args()

    sockets = discover_sockets(args.target)
    if not sockets:
        print(f"{RED}[FAIL]{RESET} No socket files (.sock) found in target: {args.target}")
        return 1

    print(f"🔍 Testing {len(sockets)} socket daemon(s) in '{args.target}'...\n")
    all_passed = True

    for sock_path in sockets:
        success, message = test_socket(sock_path)
        socket_name = os.path.basename(sock_path)
        if success:
            print(f"  {GREEN}[OK]{RESET}   {socket_name:<20} - {message}")
        else:
            print(f"  {RED}[FAIL]{RESET} {socket_name:<20} - {message}")
            all_passed = False

    print()
    if all_passed:
        print(f"{GREEN}SUCCESS:{RESET} All IPC socket daemons are operating normally.")
        return 0
    else:
        print(f"{RED}FAILURE:{RESET} One or more socket daemons failed smoke test.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
