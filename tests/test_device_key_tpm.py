"""The device key is made in the TPM and cannot leave it (EIRA-CONTEXT §5.0,
FLEET-RIGHTS-API §8 step 1, invariant A-1). Level N1 with swtpm; the VM test
with a cloned disk (T-A1-a … e) is N3.

A cloned disk is modelled as the same key blob on a *different* TPM.
"""

from __future__ import annotations

import datetime as dt
import ssl
import threading
from datetime import timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from app.rights import devicekey, enroll
from tests.test_fleet_transport import _ca, _leaf


def test_t_a1_f_the_key_is_a_tpm_blob_that_cannot_be_exported(tpm, tmp_path):
    key = tmp_path / "device.key"
    devicekey.create(key)
    blob = key.read_bytes()
    assert blob.startswith(b"-----BEGIN TSS2 PRIVATE KEY-----")
    with pytest.raises((ValueError, TypeError)):
        serialization.load_pem_private_key(blob, password=None)  # not an ordinary key
    assert {"fixedTPM", "fixedParent", "sensitiveDataOrigin"} <= devicekey.attributes(key)


def test_the_csr_is_signed_by_the_tpm_key(tpm, tmp_path):
    key = tmp_path / "device.key"
    devicekey.create(key)
    request = x509.load_pem_x509_csr(devicekey.csr(key, "laptop-7"))
    assert request.is_signature_valid
    assert request.public_key().public_bytes(serialization.Encoding.DER,
                                             serialization.PublicFormat.SubjectPublicKeyInfo) \
        == devicekey.public_key_der(key)
    assert request.public_key().curve.name == "secp256r1"


def test_t_a1_b_a_cloned_disk_cannot_sign_on_other_hardware(tpm, other_tpm, tmp_path, monkeypatch):
    key = tmp_path / "device.key"
    devicekey.create(key)
    monkeypatch.setenv("TPM2OPENSSL_TCTI", other_tpm.tcti)  # same disk, new machine
    with pytest.raises(devicekey.DeviceKeyError):
        devicekey.csr(key, "clone")


# --- mTLS (T-A1-c at N1): the handshake is signed in the TPM -----------------

_HANDSHAKE = """
import socket, sys
from app.rights.transport import TlsFiles, tls_context
from pathlib import Path
d = Path(sys.argv[2])
ctx = tls_context(TlsFiles(Path(sys.argv[1]), d / "device.crt", d / "device.key", d / "tenant.token"))
with socket.create_connection(("127.0.0.1", int(sys.argv[3])), timeout=10) as raw:
    with ctx.wrap_socket(raw, server_hostname="localhost") as tls:
        tls.sendall(b"GET / HTTP/1.0\\r\\n\\r\\n")
        print(tls.recv(100).decode())
"""


class _Ok(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"seen")


@pytest.fixture
def mtls_server(tmp_path):
    ca_key, ca_cert = _ca(tmp_path, "fleet-ca")
    _leaf(tmp_path, "server", ca_key, ca_cert, server=True)
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(tmp_path / "server.crt", tmp_path / "server.key")
    ctx.load_verify_locations(tmp_path / "fleet-ca.pem")
    ctx.verify_mode = ssl.CERT_REQUIRED  # the client must prove its key
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Ok)
    httpd.socket = ctx.wrap_socket(httpd.socket, server_side=True)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield httpd.server_address[1], ca_key, ca_cert
    httpd.shutdown()
    httpd.server_close()


def _issue(device_dir, ca_key, ca_cert):
    request = x509.load_pem_x509_csr(devicekey.csr(device_dir / "device.key", "device"))
    now = dt.datetime.now(dt.timezone.utc)
    cert = (
        x509.CertificateBuilder().subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "device")]))
        .issuer_name(ca_cert.subject).public_key(request.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1)).not_valid_after(now + timedelta(days=1))
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.CLIENT_AUTH]), critical=False)
        .sign(ca_key, hashes.SHA256())
    )
    (device_dir / "device.crt").write_bytes(cert.public_bytes(serialization.Encoding.PEM))


def test_t_a1_c_mtls_works_on_the_device_and_fails_on_a_clone(tpm, other_tpm, mtls_server, tmp_path):
    port, ca_key, ca_cert = mtls_server
    device = tmp_path / "fleet"
    device.mkdir()
    devicekey.create(device / "device.key")
    _issue(device, ca_key, ca_cert)
    ca = str(tmp_path / "fleet-ca.pem")

    on_device = tpm.run_python(_HANDSHAKE, ca, str(device), str(port))
    assert on_device.returncode == 0, on_device.stderr
    assert "200 OK" in on_device.stdout

    on_clone = other_tpm.run_python(_HANDSHAKE, ca, str(device), str(port))
    assert on_clone.returncode != 0
    assert "200 OK" not in on_clone.stdout
    assert "TPM device key" in on_clone.stderr, on_clone.stderr  # refused at the key, not elsewhere


# --- enroll (FLEET-RIGHTS-API §8 step 1) --------------------------------------


def test_t_a1_g_enroll_without_a_tpm_writes_nothing_and_exits_2(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("TPM2OPENSSL_TCTI", raising=False)
    monkeypatch.setattr(devicekey, "TPM_DEVICE", tmp_path / "no-tpmrm0")
    files = enroll.TlsFiles.default(tmp_path / "fleet")
    inv = enroll.parse_invitation({
        "eira_enroll_invite": "1", "fleet_url": "https://fleet.example", "ca": _ca(tmp_path, "ca")[1]
        .public_bytes(serialization.Encoding.PEM).decode(), "enroll_token": "single-use-token-0123",
        "expires_at": "2099-01-01T00:00:00Z"}, dt.datetime.now(dt.timezone.utc))
    with pytest.raises(devicekey.NoTpm):
        enroll.enroll(inv, enrollment_path=tmp_path / "enrollment.json", files=files, group=None)
    assert not (tmp_path / "fleet").exists() and not (tmp_path / "enrollment.json").exists()

    monkeypatch.setattr(enroll.os, "geteuid", lambda: 0)
    monkeypatch.setattr(enroll, "enroll", lambda *a, **k: (_ for _ in ()).throw(devicekey.NoTpm("no TPM 2.0")))
    path = tmp_path / "invite.json"
    path.write_text('{"eira_enroll_invite": "1", "fleet_url": "https://fleet.example", "ca": "x", '
                    '"enroll_token": "single-use-token-0123", "expires_at": "2099-01-01T00:00:00Z"}')
    monkeypatch.setattr(enroll, "parse_invitation", lambda data, now: inv)
    assert enroll.main([str(path)]) == 2
    assert "TPM 2.0" in capsys.readouterr().err


# --- packaging: the processes that use the key can reach the TPM, nothing more --


def test_packaging_gives_the_key_users_the_tpm_and_nothing_else():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    unit = (root / "packaging" / "rights" / "eira-rights-sync.service").read_text()
    for line in ("Environment=OPENSSL_CONF=/usr/share/eira-os/openssl-tpm2.cnf",
                 "Environment=TPM2OPENSSL_TCTI=device:/dev/tpmrm0", "SupplementaryGroups=tss",
                 "DevicePolicy=closed", "DeviceAllow=/dev/tpmrm0 rw"):
        assert line in unit, line
    assert "PrivateDevices=true" not in unit  # would hide /dev/tpmrm0
    profile = (root / "packaging" / "rights" / "usr.bin.eira-rights-apply").read_text()
    assert "/dev/tpmrm0 rw," in profile and "/dev/tpm0" not in profile
    assert "OPENSSL_CONF=/usr/share/eira-os/openssl-tpm2.cnf" in (root / "packaging" / "bin" / "eira-enroll").read_text()
    assert "usr/share/eira-os/openssl-tpm2.cnf" in (root / "packaging" / "debian" / "rules").read_text()
    control = (root / "packaging" / "debian" / "control").read_text()
    assert "tpm2-openssl" in control and "tpm-udev" in control
    cnf = (root / "packaging" / "rights" / "openssl-tpm2.cnf").read_text()
    assert "tpm2 = eira_tpm2" in cnf and "default = eira_default" in cnf
