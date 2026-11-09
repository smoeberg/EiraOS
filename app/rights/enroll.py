"""Enroll this device with Fleet (FLEET-RIGHTS-API §8).

    eira-enroll INVITATION.json        (as root)

The invitation comes from IT over their own channel (USB, provisioning
image): Fleet's URL, Fleet's CA and a single-use enroll token. The device

1. generates its key pair locally — the private key never leaves the device,
   only a certificate signing request does;
2. calls POST /v1/enroll over TLS that trusts only the invitation's CA;
3. checks the answer: same Fleet, a certificate issued by that CA for *this*
   key, a valid enrollment (roots with not_after);
4. writes /etc/eira/fleet/* first and /etc/eira/enrollment.json last, each
   atomically. The enrollment file is what makes the device managed, so a
   crash before it leaves the device unmanaged, never half-managed.

An already enrolled device is refused: re-enrolling is an explicit operator
decision (remove the enrollment first).
"""

from __future__ import annotations

import datetime as dt
import grp
import hashlib
import http.client
import json
import os
import socket
import ssl
import sys
import tempfile
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from app.rights import fleet_api
from app.rights.transport import MAX_RESPONSE_BYTES, TIMEOUT_SECONDS, TlsFiles

INVITE_VERSION = "1"
MACHINE_ID = Path("/etc/machine-id")


class EnrollError(Exception):
    """Enrollment failed; nothing that makes the device managed was written."""


@dataclass(frozen=True)
class Invitation:
    fleet_url: str
    ca_pem: bytes
    enroll_token: str
    expires_at: dt.datetime


def parse_invitation(data: Any, now: dt.datetime) -> Invitation:
    try:
        if data["eira_enroll_invite"] != INVITE_VERSION:
            raise EnrollError("unsupported invitation version")
        url = data["fleet_url"]
        parts = urllib.parse.urlsplit(url)
        if parts.scheme != "https" or not parts.hostname or parts.username or parts.query or parts.fragment:
            raise EnrollError("fleet_url must be https://host[:port][/base]")
        ca = data["ca"].encode("ascii")
        x509.load_pem_x509_certificate(ca)
        token = data["enroll_token"]
        if not isinstance(token, str) or not 16 <= len(token) <= 512 or not token.isascii() or any(
            c in token for c in "\r\n "
        ):
            raise EnrollError("enroll_token is malformed")
        expires = dt.datetime.strptime(data["expires_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)
    except EnrollError:
        raise
    except (KeyError, TypeError, AttributeError, ValueError) as exc:
        raise EnrollError(f"malformed invitation: {exc}") from None
    if now >= expires:
        raise EnrollError("invitation has expired")
    return Invitation(url, ca, token, expires)


def machine_hash(path: Path | None = None) -> str:
    """Hardware binding for Fleet, without sending the raw machine-id.
    The path is read at call time (a default bound at definition time made
    tests read the host's real /etc/machine-id)."""
    path = path if path is not None else MACHINE_ID
    try:
        raw = path.read_text(encoding="ascii").strip()
    except OSError as exc:
        raise EnrollError(f"cannot read machine-id: {exc}") from None
    return "sha256:" + hashlib.sha256(b"eira-enroll:" + raw.encode()).hexdigest()


def new_key_and_csr() -> tuple[ec.EllipticCurvePrivateKey, bytes]:
    key = ec.generate_private_key(ec.SECP256R1())
    csr = (
        x509.CertificateSigningRequestBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, socket.gethostname()[:64] or "eira")]))
        .sign(key, hashes.SHA256())
    )
    return key, csr.public_bytes(serialization.Encoding.PEM)


def check_answer(answer: Any, invitation: Invitation, key, now: dt.datetime) -> tuple[dict, bytes, str | None]:
    """Everything Fleet returns is checked before anything is written."""
    if not isinstance(answer, dict):
        raise EnrollError("enroll answer is not an object")
    if answer.get("fleet_url") != invitation.fleet_url:
        raise EnrollError("enroll answer names another Fleet")
    try:
        enrollment = {
            "eira_enrollment": fleet_api.ENROLLMENT_VERSION,
            "tenant_id": answer["tenant_id"],
            "device_id": answer["device_id"],
            "fleet_url": invitation.fleet_url,
            "rights_roots": answer["rights_roots"],
        }
        fleet_api.parse_enrollment(enrollment)
        cert_pem = answer["device_certificate"].encode("ascii")
        cert = x509.load_pem_x509_certificate(cert_pem)
    except (KeyError, AttributeError, ValueError) as exc:
        raise EnrollError(f"malformed enroll answer: {exc}") from None
    ca = x509.load_pem_x509_certificate(invitation.ca_pem)
    try:
        cert.verify_directly_issued_by(ca)
    except Exception:  # noqa: BLE001 - any failure means "not issued by this CA"
        raise EnrollError("device certificate is not issued by the invitation's CA") from None
    ours = key.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    theirs = cert.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    if ours != theirs:
        raise EnrollError("device certificate is for another key")
    if not cert.not_valid_before_utc <= now < cert.not_valid_after_utc:
        raise EnrollError("device certificate is not valid now")
    try:
        usages = cert.extensions.get_extension_for_class(x509.ExtendedKeyUsage).value
        if ExtendedKeyUsageOID.CLIENT_AUTH not in usages:
            raise EnrollError("device certificate is not for client authentication")
    except x509.ExtensionNotFound:
        pass
    token = answer.get("tenant_token")
    if token is not None and (not isinstance(token, str) or not token.isascii() or any(c in token for c in "\r\n")):
        raise EnrollError("tenant_token is malformed")
    return enrollment, cert_pem, token


def call_enroll(invitation: Invitation, body: dict, *, context: ssl.SSLContext | None = None) -> Any:
    parts = urllib.parse.urlsplit(invitation.fleet_url)
    if context is None:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.load_verify_locations(cadata=invitation.ca_pem.decode("ascii"))  # the invitation's CA only
    conn = http.client.HTTPSConnection(parts.hostname, parts.port or 443, context=context, timeout=TIMEOUT_SECONDS)
    try:
        conn.request("POST", parts.path.rstrip("/") + "/v1/enroll", body=json.dumps(body).encode(),
                     headers={"Content-Type": "application/json", "Accept": "application/json",
                              "User-Agent": "eira-enroll/1"})
        response = conn.getresponse()
        data = response.read(MAX_RESPONSE_BYTES + 1)
        if response.status not in (200, 201):
            raise EnrollError(f"Fleet refused enrollment: HTTP {response.status}")
        if len(data) > MAX_RESPONSE_BYTES:
            raise EnrollError("enroll answer too large")
        return json.loads(data.decode("utf-8"))
    except (OSError, http.client.HTTPException, UnicodeDecodeError, ValueError) as exc:
        raise EnrollError(f"cannot reach Fleet: {exc}") from None
    finally:
        conn.close()


def _write(path: Path, data: bytes, mode: int, gid: int | None) -> None:
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        if gid is not None:
            os.chown(tmp, 0, gid)
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def enroll(
    invitation: Invitation,
    *,
    enrollment_path: Path,
    files: TlsFiles,
    group: str | None = "eira",
    context: ssl.SSLContext | None = None,
    now: dt.datetime | None = None,
) -> dict:
    now = now or dt.datetime.now(dt.timezone.utc)
    if enrollment_path.exists():
        raise EnrollError("device is already enrolled; remove the enrollment to re-enroll")
    key, csr = new_key_and_csr()
    answer = call_enroll(invitation, {
        "enroll_token": invitation.enroll_token,
        "csr": csr.decode("ascii"),
        "machine_hash": machine_hash(),
        "hostname": socket.gethostname(),
    }, context=context)
    enrollment, cert_pem, token = check_answer(answer, invitation, key, now)

    gid = grp.getgrnam(group).gr_gid if group else None
    directory = files.key.parent
    directory.mkdir(mode=0o750, parents=True, exist_ok=True)
    if gid is not None:
        os.chown(directory, 0, gid)
    os.chmod(directory, 0o750)
    key_pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                serialization.NoEncryption())
    _write(files.ca, invitation.ca_pem, 0o644, None)
    _write(files.certificate, cert_pem, 0o644, None)
    _write(files.key, key_pem, 0o640, gid)
    if token:
        _write(files.token, token.encode("ascii"), 0o640, gid)
    else:
        files.token.unlink(missing_ok=True)
    # Last: this file is what makes the device managed.
    _write(enrollment_path, json.dumps(enrollment, indent=2, sort_keys=True).encode() + b"\n", 0o644, None)
    return enrollment


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print("usage: eira-enroll INVITATION.json", file=sys.stderr)
        return 64
    if os.geteuid() != 0:
        print("eira-enroll must run as root", file=sys.stderr)
        return 77
    now = dt.datetime.now(dt.timezone.utc)
    try:
        invitation = parse_invitation(json.loads(Path(args[0]).read_text(encoding="utf-8")), now)
        enrollment = enroll(invitation, enrollment_path=fleet_api.ENROLLMENT_PATH, files=TlsFiles.default())
    except (OSError, ValueError, EnrollError) as exc:
        print(f"eira-enroll: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({"event": "enrolled", "tenant_id": enrollment["tenant_id"],
                      "device_id": enrollment["device_id"]}))
    # First sync now rather than at the next timer tick; failure is harmless.
    import subprocess

    subprocess.run(["systemctl", "start", "--no-block", "eira-rights-sync.service"], check=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
