"""Context homes on S3 and WebDAV (EIRA-CONTEXT §6.1, H-1; UDVIKLINGSPLAN F2.2).

Both implement the same two operations as LocalHome: ``put_if_absent`` and
``get`` (plus ``exists``). Writing is always atomic create-if-absent:

- S3: ``PutObject`` with ``If-None-Match: *``. 200 = written, 412 = exists.
- WebDAV: ``PUT`` with ``If-None-Match: *`` (RFC 9110 §13.1.2), same meaning.
  Parent collections are created with MKCOL first.

A home that cannot guarantee this is not supported. :func:`attach` checks it
before a home is used: write A to a fresh probe path, write B to the same
path with ``If-None-Match: *``, and read back. Only "B refused" *and* "A read
back" accepts the home; anything else is ``E_CONTEXT_HOME_UNSUPPORTED``. The
read-back catches a server that answers 412 but overwrote anyway.

The S3 client signs with AWS Signature Version 4 itself (no SDK), path-style.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from datetime import datetime, timezone
from typing import Protocol
from urllib.parse import quote, urlsplit

import httpx

from app.context.errors import E_CONTEXT_HOME_UNSUPPORTED, ContextError


class Home(Protocol):
    def put_if_absent(self, name: str, data: bytes) -> bool: ...
    def get(self, name: str) -> bytes: ...
    def exists(self, name: str) -> bool: ...


class HomeError(OSError):
    """The home answered something other than success or "exists"."""


_RETRY_STATUSES = {409, 500, 502, 503, 504}  # 409: S3 conditional write in progress


def _retry(send, attempts: int = 5):
    for attempt in range(attempts):
        response = send()
        if response.status_code not in _RETRY_STATUSES or attempt == attempts - 1:
            return response
        time.sleep(0.05 * (2**attempt))
    return response


class S3Home:
    def __init__(self, endpoint: str, bucket: str, prefix: str, access_key: str, secret_key: str,
                 *, region: str = "us-east-1", client: httpx.Client | None = None) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.bucket = bucket
        self.prefix = prefix.strip("/")
        self.access_key = access_key
        self.secret_key = secret_key
        self.region = region
        self.client = client or httpx.Client(timeout=30)

    def _path(self, name: str) -> str:
        key = f"{self.prefix}/{name}" if self.prefix else name
        return "/" + quote(self.bucket) + "/" + quote(key, safe="/-_.~")

    def _signed(self, method: str, path: str, body: bytes = b"", headers: dict[str, str] | None = None) -> httpx.Response:
        now = datetime.now(timezone.utc)
        amz_date, date = now.strftime("%Y%m%dT%H%M%SZ"), now.strftime("%Y%m%d")
        host = urlsplit(self.endpoint).netloc
        payload_hash = hashlib.sha256(body).hexdigest()
        all_headers = {"host": host, "x-amz-date": amz_date, "x-amz-content-sha256": payload_hash,
                       **{k.lower(): v for k, v in (headers or {}).items()}}
        signed = ";".join(sorted(all_headers))
        canonical = "\n".join([
            method, path, "",
            "".join(f"{k}:{all_headers[k].strip()}\n" for k in sorted(all_headers)),
            signed, payload_hash,
        ])
        scope = f"{date}/{self.region}/s3/aws4_request"
        to_sign = "\n".join(["AWS4-HMAC-SHA256", amz_date, scope, hashlib.sha256(canonical.encode()).hexdigest()])
        key = ("AWS4" + self.secret_key).encode()
        for part in (date, self.region, "s3", "aws4_request"):
            key = hmac.new(key, part.encode(), hashlib.sha256).digest()
        signature = hmac.new(key, to_sign.encode(), hashlib.sha256).hexdigest()
        all_headers["authorization"] = (f"AWS4-HMAC-SHA256 Credential={self.access_key}/{scope}, "
                                        f"SignedHeaders={signed}, Signature={signature}")
        del all_headers["host"]
        return self.client.request(method, self.endpoint + path, content=body, headers=all_headers)

    def ensure_bucket(self) -> None:
        response = self._signed("PUT", "/" + quote(self.bucket))
        if response.status_code not in (200, 409):  # 409: already exists
            raise HomeError(f"create bucket: HTTP {response.status_code}")

    def put_if_absent(self, name: str, data: bytes) -> bool:
        response = _retry(lambda: self._signed("PUT", self._path(name), data, {"If-None-Match": "*"}))
        if response.status_code in (200, 201):
            return True
        if response.status_code == 412:
            return False
        raise HomeError(f"PUT {name}: HTTP {response.status_code}")

    def get(self, name: str) -> bytes:
        response = _retry(lambda: self._signed("GET", self._path(name)))
        if response.status_code != 200:
            raise HomeError(f"GET {name}: HTTP {response.status_code}")
        return response.content

    def exists(self, name: str) -> bool:
        return _retry(lambda: self._signed("HEAD", self._path(name))).status_code == 200


class WebDavHome:
    def __init__(self, base_url: str, *, auth: tuple[str, str] | None = None,
                 client: httpx.Client | None = None) -> None:
        self.base = base_url.rstrip("/")
        self.client = client or httpx.Client(timeout=30, auth=auth)
        self._collections: set[str] = set()

    def _url(self, name: str) -> str:
        return self.base + "/" + quote(name, safe="/-_.~")

    def _mkcols(self, name: str) -> None:
        parts = name.split("/")[:-1]
        for i in range(1, len(parts) + 1):
            collection = "/".join(parts[:i])
            if collection in self._collections:
                continue
            status = self.client.request("MKCOL", self._url(collection) + "/").status_code
            if status not in (201, 405):  # 405: the collection exists
                raise HomeError(f"MKCOL {collection}: HTTP {status}")
            self._collections.add(collection)

    def put_if_absent(self, name: str, data: bytes) -> bool:
        self._mkcols(name)
        response = _retry(lambda: self.client.put(self._url(name), content=data, headers={"If-None-Match": "*"}))
        if response.status_code in (200, 201, 204):
            return True
        if response.status_code == 412:
            return False
        raise HomeError(f"PUT {name}: HTTP {response.status_code}")

    def get(self, name: str) -> bytes:
        response = _retry(lambda: self.client.get(self._url(name)))
        if response.status_code != 200:
            raise HomeError(f"GET {name}: HTTP {response.status_code}")
        return response.content

    def exists(self, name: str) -> bool:
        return self.client.head(self._url(name)).status_code == 200


def attach(home: Home) -> Home:
    """The home, if it really is create-if-absent (§6.1). Otherwise
    ``E_CONTEXT_HOME_UNSUPPORTED``; nothing of the context is written."""
    probe = f"probe/{secrets.token_hex(16)}"
    first, second = b"eira-probe-A-" + secrets.token_bytes(16), b"eira-probe-B-" + secrets.token_bytes(16)
    try:
        if not home.put_if_absent(probe, first):
            raise ContextError(E_CONTEXT_HOME_UNSUPPORTED, "a fresh probe path already existed")
        if home.put_if_absent(probe, second):
            raise ContextError(E_CONTEXT_HOME_UNSUPPORTED, "an existing object was overwritten")
        if home.get(probe) != first:
            raise ContextError(E_CONTEXT_HOME_UNSUPPORTED, "the server refused, but overwrote anyway")
    except HomeError as exc:
        raise ContextError(E_CONTEXT_HOME_UNSUPPORTED, str(exc)) from exc
    return home
