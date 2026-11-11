"""HTTPS + mTLS transport for the Fleet rights API (FLEET-RIGHTS-API §7).

Implements `FleetRightsClient` with the standard library only (ssl,
http.client): no new package dependency on the endpoint.

What the transport guarantees, and nothing more — whether a rights set may be
used is still decided by `contract.verify`:

- Only the enrolled Fleet: the URL comes from enrollment, the host must match
  it, redirects are never followed (Fleet Agent Protocol v0.1 §2.1 pinning).
- Only Fleet's own CA: the system trust store is not loaded, so a public CA
  cannot vouch for an impostor.
- Mutual TLS with the device certificate issued at enroll, TLS 1.2 or newer,
  plus the tenant token when Fleet issued one.
- Bounded: timeouts and a response size limit; anything outside the API is a
  ProtocolViolation, an unreachable Fleet a FleetError (offline).
"""

from __future__ import annotations

import http.client
import json
import os
import ssl
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.rights.fleet_api import (
    ApplyReport,
    DesiredRights,
    Enrollment,
    FleetError,
    ProtocolViolation,
    RightsHeartbeat,
    parse_desired_state,
)

FLEET_DIR = Path(os.environ.get("EIRA_FLEET_DIR", "/etc/eira/fleet"))
# Set + 16 key certificates + revocations, base64url, plus the rest of desired state.
MAX_RESPONSE_BYTES = 4 * 1024 * 1024
TIMEOUT_SECONDS = 15.0
USER_AGENT = "eira-rights-agent/1"


@dataclass(frozen=True)
class TlsFiles:
    """Left on the device by enroll (FLEET-RIGHTS-API §7)."""

    ca: Path            # Fleet's server CA, the only trusted root (root, 0644)
    certificate: Path   # device certificate (root, 0644)
    key: Path           # device private key (root:eira, 0640)
    token: Path         # tenant token, optional (root:eira, 0640)

    @classmethod
    def default(cls, directory: Path | None = None) -> "TlsFiles":
        d = directory or FLEET_DIR
        return cls(d / "ca.pem", d / "device.crt", d / "device.key", d / "tenant.token")


def tls_context(files: TlsFiles) -> ssl.SSLContext:
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)  # check_hostname + CERT_REQUIRED
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.load_verify_locations(cafile=str(files.ca))  # Fleet's CA only, no system store
    ctx.load_cert_chain(certfile=str(files.certificate), keyfile=str(files.key))
    return ctx


class HttpsFleetRightsClient:
    def __init__(
        self,
        enrollment: Enrollment,
        files: TlsFiles | None = None,
        *,
        context: ssl.SSLContext | None = None,
        timeout: float = TIMEOUT_SECONDS,
    ) -> None:
        url = urllib.parse.urlsplit(enrollment.fleet_url)
        if url.scheme != "https" or not url.hostname or url.username or url.password:
            raise ValueError("fleet_url must be https://host[:port][/base]")
        if url.query or url.fragment:
            raise ValueError("fleet_url must not carry a query or fragment")
        self._host = url.hostname
        self._port = url.port or 443
        self._base = url.path.rstrip("/")
        self._device_id = enrollment.device_id
        self._files = files or TlsFiles.default()
        self._context = context or tls_context(self._files)
        self._timeout = timeout

    # --- FleetRightsClient ----------------------------------------------------

    def desired_rights(self, active_version: int | None) -> DesiredRights:
        query = "" if active_version is None else "?" + urllib.parse.urlencode({"rights_version": active_version})
        status, body = self._request("GET", "/v1/desired-state" + query)
        if status != 200:
            raise FleetError(f"desired-state: HTTP {status}")
        return parse_desired_state(_json(body))

    def report_apply(self, report: ApplyReport) -> None:
        self._post("/v1/report/apply-result", report.to_json())

    # --- heartbeat (rights fields; FLEET-RIGHTS-API §3.3) ---------------------

    def heartbeat(self, rights: RightsHeartbeat, audit: dict | None = None, seal: dict | None = None) -> None:
        body = {"device_id": self._device_id, "rights": rights.to_json()}
        if audit is not None:
            body["audit"] = audit  # Fleet witnesses the audit chain (§3.3)
        if seal is not None:
            # The journal's FSS verification key, once (§3.3): Fleet keeps it
            # off the machine; the caller deletes it here after a 2xx.
            body["audit_seal"] = seal
        self._post("/v1/heartbeat", body)

    # --- plumbing -------------------------------------------------------------

    def _post(self, path: str, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, sort_keys=True).encode()
        status, _ = self._request("POST", path, body)
        if status not in (200, 202, 204):
            raise FleetError(f"{path}: HTTP {status}")

    def _headers(self, has_body: bool) -> dict[str, str]:
        headers = {"Accept": "application/json", "User-Agent": USER_AGENT, "X-EIRA-Device-Id": self._device_id}
        if has_body:
            headers["Content-Type"] = "application/json"
        try:
            token = self._files.token.read_text(encoding="ascii").strip()
        except FileNotFoundError:
            token = ""
        except (OSError, UnicodeDecodeError) as exc:
            raise FleetError(f"tenant token unreadable: {exc}") from None
        if token:
            if any(c in token for c in "\r\n"):
                raise FleetError("tenant token is malformed")
            headers["Authorization"] = f"Bearer {token}"
        return headers

    def _request(self, method: str, path: str, body: bytes | None = None) -> tuple[int, bytes]:
        conn = http.client.HTTPSConnection(
            self._host, self._port, context=self._context, timeout=self._timeout
        )
        try:
            conn.request(method, self._base + path, body=body, headers=self._headers(body is not None))
            response = conn.getresponse()
            if 300 <= response.status < 400:
                # Pinning: never follow a redirect away from the enrolled Fleet.
                raise FleetError(f"{path}: redirect refused (HTTP {response.status})")
            declared = response.getheader("Content-Length")
            if declared is not None and declared.isdigit() and int(declared) > MAX_RESPONSE_BYTES:
                raise ProtocolViolation("response too large")
            data = response.read(MAX_RESPONSE_BYTES + 1)
            if len(data) > MAX_RESPONSE_BYTES:
                raise ProtocolViolation("response too large")
            return response.status, data
        except (ssl.SSLError, ssl.CertificateError) as exc:
            raise FleetError(f"TLS: {exc}") from None
        except (OSError, http.client.HTTPException) as exc:
            raise FleetError(f"{type(exc).__name__}: {exc}") from None
        finally:
            conn.close()


def _json(body: bytes) -> Any:
    try:
        return json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise ProtocolViolation("response is not JSON") from None
