"""Level N2 (EIRA-CONTEXT testplan §1): real storage servers.

Servers come from the environment (CI job ``context-home`` starts them):

    EIRA_TEST_S3_ENDPOINT, EIRA_TEST_S3_ACCESS_KEY, EIRA_TEST_S3_SECRET_KEY,
    EIRA_TEST_S3_NAME (shown in test ids, e.g. "minio")
    EIRA_TEST_WEBDAV_URL, EIRA_TEST_WEBDAV_USER, EIRA_TEST_WEBDAV_PASSWORD,
    EIRA_TEST_WEBDAV_NAME (e.g. "apache-mod_dav")

Without them, the tests start moto (S3) and WsgiDAV (WebDAV) locally if
they are installed, and skip the server otherwise. With
EIRA_TEST_REQUIRE_SERVERS=1 (CI) a missing server is an error, not a skip. The faulty test servers
(faulty_server.py) always run.
"""

from __future__ import annotations

import os
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time

import httpx
import pytest

from app.context.remote import S3Home, WebDavHome


def pytest_configure(config):
    config.addinivalue_line("markers", "home: needs a storage server (EIRA-CONTEXT N2)")


def _missing(reason: str):
    if os.environ.get("EIRA_TEST_REQUIRE_SERVERS") == "1":
        pytest.fail(reason)
    pytest.skip(reason)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait(url: str) -> None:
    for _ in range(100):
        try:
            httpx.get(url, timeout=1)
            return
        except httpx.HTTPError:
            time.sleep(0.1)
    raise RuntimeError(f"server at {url} did not start")


@pytest.fixture(scope="session")
def s3_server():
    if os.environ.get("EIRA_TEST_S3_ENDPOINT"):
        yield (os.environ.get("EIRA_TEST_S3_NAME", "s3"), os.environ["EIRA_TEST_S3_ENDPOINT"],
               os.environ.get("EIRA_TEST_S3_ACCESS_KEY", ""), os.environ.get("EIRA_TEST_S3_SECRET_KEY", ""))
        return
    try:
        import moto.server  # noqa: F401
    except ImportError:
        _missing("no S3 server: set EIRA_TEST_S3_ENDPOINT or install moto[server]")
    port = _free_port()
    proc = subprocess.Popen([sys.executable, "-m", "moto.server", "-p", str(port)],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        _wait(f"http://127.0.0.1:{port}/")
        yield ("moto", f"http://127.0.0.1:{port}", "testing", "testing")
    finally:
        proc.terminate()


@pytest.fixture(scope="session")
def webdav_server():
    if os.environ.get("EIRA_TEST_WEBDAV_URL"):
        user = os.environ.get("EIRA_TEST_WEBDAV_USER")
        auth = (user, os.environ.get("EIRA_TEST_WEBDAV_PASSWORD", "")) if user else None
        yield (os.environ.get("EIRA_TEST_WEBDAV_NAME", "webdav"), os.environ["EIRA_TEST_WEBDAV_URL"], auth)
        return
    if not shutil.which("wsgidav"):
        _missing("no WebDAV server: set EIRA_TEST_WEBDAV_URL or install wsgidav")
    root = tempfile.mkdtemp()
    port = _free_port()
    proc = subprocess.Popen(["wsgidav", "--host", "127.0.0.1", "--port", str(port), "--root", root,
                             "--auth", "anonymous"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        _wait(f"http://127.0.0.1:{port}/")
        yield ("wsgidav", f"http://127.0.0.1:{port}", None)
    finally:
        proc.terminate()
        shutil.rmtree(root, ignore_errors=True)


# Servers whose If-None-Match is a check followed by a separate write: one
# request at a time they comply (attach accepts them), but concurrent
# uploads can both win. Found by T-H1-b; testplan finding 6.
RACY = {"wsgidav", "apache-mod_dav"}


def _new_s3_home(server) -> S3Home:
    _name, endpoint, access, secret = server
    home = S3Home(endpoint, "eira-ctx-test", secrets.token_hex(8), access, secret)
    home.ensure_bucket()
    home.server_name = server[0]
    return home


def _new_webdav_home(server) -> WebDavHome:
    _name, url, auth = server
    base = f"{url.rstrip('/')}/{secrets.token_hex(8)}"
    status = httpx.request("MKCOL", base + "/", auth=auth).status_code
    assert status in (201, 405), status
    home = WebDavHome(base, auth=auth)
    home.server_name = server[0]
    return home


@pytest.fixture(params=["s3", "webdav"])
def remote_home(request):
    """A fresh, empty home on each kind of compliant server (T-H1-e: S3 and WebDAV)."""
    if request.param == "s3":
        return _new_s3_home(request.getfixturevalue("s3_server"))
    return _new_webdav_home(request.getfixturevalue("webdav_server"))
