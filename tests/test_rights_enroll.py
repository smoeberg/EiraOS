"""Enrollment (FLEET-RIGHTS-API §8) against a TLS stand-in for Fleet, and the
sync schedule (§4)."""

from __future__ import annotations

import datetime as dt
import json
import ssl
import stat
import threading
from datetime import timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.x509.oid import ExtendedKeyUsageOID

from app.rights import agent, devicekey, enroll, fleet_api
from app.rights.cache import RightsCache
from app.rights.transport import TlsFiles
from tests.test_fleet_transport import _ca, _leaf

ROOT = Path(__file__).resolve().parents[1]
ROOTS = {"kk-root-1": {"public_key": "A" * 43, "not_after": "2036-01-01T00:00:00Z"}}


class EnrollStandIn(BaseHTTPRequestHandler):
    ca_key = None
    ca_cert = None
    answer_override: dict = {}
    requests: list = []
    url = ""

    def log_message(self, *args):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.requests.append((self.path, body))
        csr = x509.load_pem_x509_csr(body["csr"].encode())
        now = dt.datetime.now(dt.timezone.utc)
        cert = (
            x509.CertificateBuilder().subject_name(csr.subject).issuer_name(self.ca_cert.subject)
            .public_key(csr.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=1)).not_valid_after(now + timedelta(days=30))
            .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.CLIENT_AUTH]), critical=False)
            .sign(self.ca_key, hashes.SHA256())
        )
        answer = {
            "tenant_id": "kk", "device_id": "dev-0042", "fleet_url": self.url,
            "device_certificate": cert.public_bytes(serialization.Encoding.PEM).decode(),
            "rights_roots": ROOTS, "tenant_token": "tenant-secret",
        }
        answer.update(self.answer_override)
        data = json.dumps(answer).encode()
        self.send_response(201)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


@pytest.fixture
def fleet(tmp_path):
    ca_key, ca_cert = _ca(tmp_path, "fleet-ca")
    _leaf(tmp_path, "server", ca_key, ca_cert, server=True)
    handler = type("H", (EnrollStandIn,), {"ca_key": ca_key, "ca_cert": ca_cert,
                                           "answer_override": {}, "requests": []})
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(tmp_path / "server.crt", tmp_path / "server.key")
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    httpd.socket = ctx.wrap_socket(httpd.socket, server_side=True)
    handler.url = f"https://localhost:{httpd.server_address[1]}"
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield handler, tmp_path
    httpd.shutdown()
    httpd.server_close()


def invitation(handler, tmp_path, **over):
    data = {
        "eira_enroll_invite": "1", "fleet_url": handler.url,
        "ca": (tmp_path / "fleet-ca.pem").read_text(), "enroll_token": "single-use-token-0123",
        "expires_at": "2099-01-01T00:00:00Z",
    }
    data.update(over)
    return enroll.parse_invitation(data, dt.datetime.now(dt.timezone.utc))


@pytest.fixture
def machine(tmp_path, monkeypatch, tpm):
    mid = tmp_path / "machine-id"
    mid.write_text("0123456789abcdef0123456789abcdef\n")
    monkeypatch.setattr(enroll, "MACHINE_ID", mid)
    files = TlsFiles.default(tmp_path / "etc" / "fleet")
    return tmp_path / "etc" / "enrollment.json", files


def test_enroll_writes_a_managed_device(fleet, machine):
    handler, tmp = fleet
    enrollment_path, files = machine
    enrollment_path.parent.mkdir(parents=True)
    result = enroll.enroll(invitation(handler, tmp), enrollment_path=enrollment_path, files=files, group=None)
    assert (result["tenant_id"], result["device_id"]) == ("kk", "dev-0042")
    parsed = fleet_api.read_enrollment(enrollment_path)
    assert parsed.device_id == "dev-0042" and set(parsed.rights_roots) == {"kk-root-1"}
    path, body = handler.requests[0]
    assert path == "/v1/enroll" and body["enroll_token"] == "single-use-token-0123"
    openapi = json.loads((ROOT / "specs" / "eira-fleet-rights-api-1.0.openapi.json").read_text())
    import jsonschema

    jsonschema.validate(body, openapi["components"]["schemas"]["EnrollRequest"])
    assert body["machine_hash"].startswith("sha256:") and "0123456789abcdef" not in body["machine_hash"]
    assert "PRIVATE" not in json.dumps(body)  # only the CSR leaves the device
    assert files.key.read_bytes().startswith(b"-----BEGIN TSS2 PRIVATE KEY-----")
    assert stat.S_IMODE(files.key.stat().st_mode) == 0o640
    assert stat.S_IMODE(files.token.stat().st_mode) == 0o640
    assert files.token.read_text() == "tenant-secret"
    assert files.ca.read_bytes() == (tmp / "fleet-ca.pem").read_bytes()


@pytest.mark.parametrize(
    "override, message",
    [
        ({"fleet_url": "https://evil.example"}, "another Fleet"),
        ({"rights_roots": {}}, "malformed"),
        ({"device_certificate": "garbage"}, "malformed"),
        ({"tenant_token": "a\nb"}, "tenant_token"),
    ],
)
def test_bad_answers_leave_the_device_unmanaged(fleet, machine, override, message):
    handler, tmp = fleet
    handler.answer_override.update(override)
    enrollment_path, files = machine
    enrollment_path.parent.mkdir(parents=True)
    with pytest.raises(enroll.EnrollError, match=message):
        enroll.enroll(invitation(handler, tmp), enrollment_path=enrollment_path, files=files, group=None)
    assert not enrollment_path.exists() and not files.key.exists()


def test_certificate_for_another_key_or_ca_is_refused(fleet, machine, tmp_path):
    handler, tmp = fleet
    other_key, other_cert = _ca(tmp_path, "other-ca")
    _leaf(tmp_path, "foreign", other_key, other_cert, server=False)
    handler.answer_override["device_certificate"] = (tmp_path / "foreign.crt").read_text()
    enrollment_path, files = machine
    enrollment_path.parent.mkdir(parents=True)
    with pytest.raises(enroll.EnrollError, match="not issued by"):
        enroll.enroll(invitation(handler, tmp), enrollment_path=enrollment_path, files=files, group=None)


def test_server_outside_the_invitations_ca_is_refused(fleet, machine, tmp_path):
    handler, tmp = fleet
    _ca(tmp_path, "unrelated-ca")
    enrollment_path, files = machine
    enrollment_path.parent.mkdir(parents=True)
    inv = invitation(handler, tmp, ca=(tmp_path / "unrelated-ca.pem").read_text())
    with pytest.raises(enroll.EnrollError, match="cannot reach"):
        enroll.enroll(inv, enrollment_path=enrollment_path, files=files, group=None)
    assert handler.requests == []


def test_already_enrolled_is_refused(fleet, machine):
    handler, tmp = fleet
    enrollment_path, files = machine
    enrollment_path.parent.mkdir(parents=True)
    enrollment_path.write_text("{}")
    with pytest.raises(enroll.EnrollError, match="already enrolled"):
        enroll.enroll(invitation(handler, tmp), enrollment_path=enrollment_path, files=files, group=None)
    assert handler.requests == []


@pytest.mark.parametrize(
    "over, message",
    [
        ({"fleet_url": "http://fleet.example"}, "https"),
        ({"expires_at": "2020-01-01T00:00:00Z"}, "expired"),
        ({"enroll_token": "short"}, "enroll_token"),
        ({"eira_enroll_invite": "2"}, "version"),
        ({"ca": "not a certificate"}, "malformed"),
    ],
)
def test_invitation_rules(fleet, over, message):
    handler, tmp = fleet
    with pytest.raises(enroll.EnrollError, match=message):
        invitation(handler, tmp, **over)


def test_cli_requires_root(monkeypatch, tmp_path):
    monkeypatch.setattr(enroll.os, "geteuid", lambda: 1000)
    assert enroll.main([str(tmp_path / "invite.json")]) == 77
    assert enroll.main([]) == 64


# --- schedule -----------------------------------------------------------------


def test_offline_rounds_back_off_and_success_resets(tmp_path):
    cache = RightsCache(tmp_path / "rights", enrollment_path=tmp_path / "none.json")
    now = dt.datetime(2026, 11, 8, 12, tzinfo=dt.timezone.utc)
    assert cache.sync_due(now)
    cache.record_sync("offline", now, agent.next_poll)
    assert cache.sync_due(now)  # the first miss waits only for the next timer tick
    cache.record_sync("offline", now, agent.next_poll)
    assert not cache.sync_due(now + timedelta(minutes=15))
    assert cache.sync_due(now + timedelta(hours=1))
    cache.record_sync("unchanged", now, agent.next_poll)
    assert cache.sync_due(now)


def test_sync_skips_while_backing_off(tmp_path, monkeypatch, capsys):
    from tests.rights_helpers import TestFleet
    from tests.test_gate_kernel import Clock

    signer = TestFleet(tmp_path / "s", Clock())
    monkeypatch.setattr(fleet_api, "ENROLLMENT_PATH", signer.enrollment_path)
    cache = RightsCache(tmp_path / "rights", enrollment_path=signer.enrollment_path)
    now = dt.datetime.now(dt.timezone.utc)
    cache.record_sync("offline", now, agent.next_poll)
    cache.record_sync("offline", now, agent.next_poll)

    class NeverCalled:
        def desired_rights(self, v):
            raise AssertionError("called Fleet while backing off")

    assert agent.sync(NeverCalled(), cache) == 0
    assert json.loads(capsys.readouterr().out.strip().splitlines()[-1])["result"] == "not_due"


def test_enrolled_device_key_is_the_tpm_blob(tpm, fleet, machine):
    handler, tmp = fleet
    enrollment_path, files = machine
    enrollment_path.parent.mkdir(parents=True)
    enroll.enroll(invitation(handler, tmp), enrollment_path=enrollment_path, files=files, group=None)
    assert files.key.read_bytes().startswith(b"-----BEGIN TSS2 PRIVATE KEY-----")
    assert {"fixedTPM", "fixedParent"} <= devicekey.attributes(files.key)
    assert not list(files.key.parent.glob(".device.key*"))  # no staged copy left behind
    cert = x509.load_pem_x509_certificate(files.certificate.read_bytes())
    assert cert.public_key().public_bytes(serialization.Encoding.DER,
                                          serialization.PublicFormat.SubjectPublicKeyInfo) \
        == devicekey.public_key_der(files.key)


# --- packaging ----------------------------------------------------------------


def test_sync_unit_is_hardened_and_conditional():
    unit = (ROOT / "packaging" / "rights" / "eira-rights-sync.service").read_text()
    for line in ("User=eira", "ConditionPathExists=/etc/eira/enrollment.json", "NoNewPrivileges=true",
                 "ProtectSystem=strict", "ReadWritePaths=/data/rights", "CapabilityBoundingSet=",
                 "AppArmorProfile=/usr/bin/eira-rights-apply", "SuccessExitStatus=1 3"):
        assert line in unit, line
    timer = (ROOT / "packaging" / "rights" / "eira-rights-sync.timer").read_text()
    assert "OnUnitActiveSec=15min" in timer and "RandomizedDelaySec=" in timer


def test_sync_profile_reads_but_never_writes_fleet_files():
    profile = (ROOT / "packaging" / "rights" / "usr.bin.eira-rights-apply").read_text()
    fleet_lines = [line.strip() for line in profile.splitlines() if "/etc/eira" in line]
    assert fleet_lines and all(line.endswith(" r,") for line in fleet_lines)
    assert "/data/rights/** rwk," in profile


def test_rules_install_the_sync_unit_profile_and_enroll_tool():
    rules = (ROOT / "packaging" / "debian" / "rules").read_text()
    assert "packaging/rights/eira-rights-sync.timer" in rules
    assert "etc/apparmor.d/usr.bin.eira-rights-apply" in rules
    assert "usr/bin/eira-enroll" in rules
    assert "systemctl enable eira-rights-sync.timer" in (ROOT / "packaging" / "debian" / "postinst").read_text()
