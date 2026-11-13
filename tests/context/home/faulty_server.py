"""Faulty test servers for H-1 (EIRA-CONTEXT testplan §4, H-1).

A minimal WebDAV-style object server on a local port, in three modes:

- ``honest``: ``If-None-Match: *`` on an existing object gives 412 and
  changes nothing (a reference for the tests themselves).
- ``ignores``: test server 1 ignores ``If-None-Match`` and overwrites.
- ``lies``: test server 2 answers 412 but has overwritten anyway.
"""

from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def serve(mode: str) -> tuple[ThreadingHTTPServer, str]:
    objects: dict[str, bytes] = {}
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args) -> None:  # quiet
            pass

        def _reply(self, status: int, body: bytes = b"") -> None:
            self.send_response(status)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def do_MKCOL(self) -> None:  # noqa: N802
            self._reply(201)

        def do_PUT(self) -> None:  # noqa: N802
            data = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            conditional = self.headers.get("If-None-Match") == "*"
            with lock:
                existed = self.path in objects
                if mode == "honest" and existed and conditional:
                    return self._reply(412)
                objects[self.path] = data
            self._reply(412 if mode == "lies" and existed and conditional else 201)

        def do_GET(self) -> None:  # noqa: N802
            with lock:
                data = objects.get(self.path)
            self._reply(404) if data is None else self._reply(200, data)

        do_HEAD = do_GET  # noqa: N815

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"
