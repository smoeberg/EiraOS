"""HTTPS + mTLS transport against a real TLS server on localhost.

The server is a stand-in for Fleet, with a test CA, a server certificate and
a device certificate. Fleet itself is not involved."""

from __future__ import annotations

import datetime as dt
import json
import ssl
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from ipaddress import ip_address
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from app.gate.policy import REGISTRY
from app.rights import agent, contract, fleet_api
from app.rights.cache import RightsCache
from app.rights.fleet_api import FleetError, ProtocolViolation
from app.rights.transport import HttpsFleetRightsClient, TlsFiles
from tests.rights_helpers import TestFleet
from tests.test_gate_kernel import Clock


def _name(cn: str) -> x509.Name:
    return x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])


def _ca(directory: Path, name: str):
    key = ec.generate_private_key(ec.SECP256R1())
    now = dt.datetime.now(dt.timezone.utc)
    cert = (
        x509.CertificateBuilder().subject_name(_name(name)).issuer_name(_name(name))
        .public_key(key.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(days=1)).not_valid_after(now + dt.timedelta(days=30))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )
    (directory / f"{name}.pem").write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    return key, cert


def _leaf(directory: Path, name: str, ca_key, ca_cert, *, server: bool, names=("localhost",)):
    key = ec.generate_private_key(ec.SECP256R1())
    now = dt.datetime.now(dt.timezone.utc)
    builder = (
        x509.CertificateBuilder().subject_name(_name(name)).issuer_name(ca_cert.subject)
        .public_key(key.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(days=1)).not_valid_after(now + dt.timedelta(days=30))
    )
    if server:
        builder = builder.add_extension(
            x509.SubjectAlternativeName(
                [x509.DNSName(n) for n in names] + [x509.IPAddress(ip_address("127.0.0.1"))] * ("localhost" in names)
            ),
            critical=False,
        )
    cert = builder.sign(ca_key, hashes.SHA256())
    (directory / f"{name}.crt").write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    (directory / f"{name}.key").write_bytes(
        key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                          serialization.NoEncryption())
    )


class FleetStandIn(BaseHTTPRequestHandler):
    signer: TestFleet
    behaviour: dict
    seen: list

    def log_message(self, *args):
        pass

    def _send(self, status, body=b"", headers=None):
        self.send_response(status)
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self.seen.append(("GET", self.path, dict(self.headers)))
        b = self.behaviour
        if "status" in b:
            return self._send(b["status"], b.get("body", b""), b.get("headers"))
        if "raw" in b:
            return self._send(200, b["raw"])
        certs, rev = self.signer.key_material()
        body = {"rights_keys": [fleet_api.encode_rights_set(c) for c in certs], "policy_revision": "git:1"}
        if f"rights_version={self.signer.version}" not in self.path:
            body["rights_set"] = fleet_api.encode_rights_set(contract.canonical(self.signer.document()))
        self._send(200, json.dumps(body).encode(), {"Content-Type": "application/json"})

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        self.seen.append(("POST", self.path, json.loads(self.rfile.read(length))))
        self._send(self.behaviour.get("post_status", 204))


@pytest.fixture
def pki(tmp_path):
    ca_key, ca_cert = _ca(tmp_path, "fleet-ca")
    _leaf(tmp_path, "server", ca_key, ca_cert, server=True)
    _leaf(tmp_path, "device", ca_key, ca_cert, server=False)
    _leaf(tmp_path, "other-host", ca_key, ca_cert, server=True, names=("fleet.other.example",))
    other_key, other_cert = _ca(tmp_path, "other-ca")
    _leaf(tmp_path, "impostor", other_key, other_cert, server=True)
    return tmp_path


@pytest.fixture
def fleet(pki, tmp_path):
    clock = Clock()
    signer = TestFleet(tmp_path / "signer", clock)
    signer.version = 5
    signer.grant("obj:sag:*", principal="did:eira:anne")

    def start(server_cert="server", require_client_cert=True):
        handler = type("H", (FleetStandIn,), {"signer": signer, "behaviour": {}, "seen": []})
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(pki / f"{server_cert}.crt", pki / f"{server_cert}.key")
        ctx.load_verify_locations(pki / "fleet-ca.pem")
        ctx.verify_mode = ssl.CERT_REQUIRED if require_client_cert else ssl.CERT_NONE
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        httpd.socket = ctx.wrap_socket(httpd.socket, server_side=True)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        servers.append(httpd)
        return httpd, handler

    servers: list = []
    yield signer, clock, start
    for s in servers:
        s.shutdown()
        s.server_close()


def client_for(pki, port, signer, *, ca="fleet-ca", cert="device", token=None, base=""):
    files = TlsFiles(pki / f"{ca}.pem", pki / f"{cert}.crt", pki / f"{cert}.key", pki / "tenant.token")
    if token is not None:
        files.token.write_text(token)
    enrollment = fleet_api.Enrollment(
        "test-tenant", "test-device", f"https://localhost:{port}{base}",
        fleet_api.read_enrollment(signer.enrollment_path).rights_roots,
    )
    return HttpsFleetRightsClient(enrollment, files, timeout=5)


def test_full_round_over_mutual_tls(pki, fleet, tmp_path):
    signer, clock, start = fleet
    httpd, handler = start()
    client = client_for(pki, httpd.server_address[1], signer, token="tenant-secret")
    cache = RightsCache(tmp_path / "rights", enrollment_path=signer.enrollment_path)
    enrolled = fleet_api.read_enrollment(signer.enrollment_path)
    assert agent.sync_once(client, enrolled, cache, registry=REGISTRY, wall_now=clock()) == "applied"
    assert agent.sync_once(client, enrolled, cache, registry=REGISTRY, wall_now=clock()) == "unchanged"
    client.heartbeat(agent.heartbeat_fields(cache, clock()))
    methods = [(m, p.split("?")[0]) for m, p, _ in handler.seen]
    assert methods == [("GET", "/v1/desired-state"), ("POST", "/v1/report/apply-result"),
                       ("GET", "/v1/desired-state"), ("POST", "/v1/heartbeat")]
    assert "rights_version=5" in handler.seen[2][1]
    headers = handler.seen[0][2]
    assert headers["Authorization"] == "Bearer tenant-secret" and headers["X-EIRA-Device-Id"] == "test-device"
    assert handler.seen[3][2]["rights"]["rights_state"] == "active"


def test_server_from_another_ca_is_refused(pki, fleet):
    """Only Fleet's CA is trusted; the system store is never loaded."""
    signer, _, start = fleet
    httpd, _ = start(server_cert="impostor")
    with pytest.raises(FleetError, match="TLS"):
        client_for(pki, httpd.server_address[1], signer).desired_rights(None)


def test_device_without_a_fleet_issued_certificate_is_refused(pki, fleet):
    signer, _, start = fleet
    httpd, _ = start()
    with pytest.raises(FleetError):
        client_for(pki, httpd.server_address[1], signer, cert="impostor").desired_rights(None)


def test_hostname_must_match_the_enrolled_fleet(pki, fleet):
    """A certificate from Fleet's own CA, but for another host, is refused."""
    signer, _, start = fleet
    httpd, _ = start(server_cert="other-host")
    with pytest.raises(FleetError, match="TLS.*(hostname|match)"):
        client_for(pki, httpd.server_address[1], signer).desired_rights(None)


@pytest.mark.parametrize(
    "behaviour, error",
    [
        ({"status": 302, "headers": {"Location": "https://evil.example/"}}, FleetError),
        ({"status": 500}, FleetError),
        ({"raw": b"<html>not json</html>"}, ProtocolViolation),
        ({"raw": b"[]"}, ProtocolViolation),
        ({"raw": b"x" * (4 * 1024 * 1024 + 10)}, ProtocolViolation),
    ],
    ids=["redirect", "server-error", "not-json", "not-an-object", "too-large"],
)
def test_answers_outside_the_api(pki, fleet, behaviour, error):
    signer, _, start = fleet
    httpd, handler = start()
    handler.behaviour.update(behaviour)
    with pytest.raises(error):
        client_for(pki, httpd.server_address[1], signer).desired_rights(None)


def test_unreachable_fleet_is_offline_not_a_crash(pki, fleet):
    signer, _, _ = fleet
    with pytest.raises(FleetError):
        client_for(pki, 9, signer).desired_rights(None)  # nothing listens on port 9


def test_base_path_and_url_rules(pki, fleet):
    signer, _, start = fleet
    httpd, handler = start()
    client_for(pki, httpd.server_address[1], signer, base="/fleet/").desired_rights(None)
    assert handler.seen[0][1].startswith("/fleet/v1/desired-state")
    roots = fleet_api.read_enrollment(signer.enrollment_path).rights_roots
    for url in ("http://fleet.example", "https://user:pw@fleet.example", "https://fleet.example/?x=1"):
        with pytest.raises(ValueError):
            HttpsFleetRightsClient(fleet_api.Enrollment("t", "d", url, roots),
                                   TlsFiles.default(pki), context=ssl.create_default_context())


def test_token_with_newline_is_refused(pki, fleet):
    signer, _, start = fleet
    httpd, _ = start()
    with pytest.raises(FleetError, match="token"):
        client_for(pki, httpd.server_address[1], signer, token="a\r\nX-Injected: 1").desired_rights(None)


def test_sync_cli_exit_codes(pki, fleet, tmp_path, monkeypatch, capsys):
    signer, clock, start = fleet
    httpd, _ = start()
    monkeypatch.setattr(fleet_api, "ENROLLMENT_PATH", tmp_path / "none.json")
    assert agent.sync() == 2  # not enrolled
    monkeypatch.setattr(fleet_api, "ENROLLMENT_PATH", signer.enrollment_path)
    cache = RightsCache(tmp_path / "rights", enrollment_path=signer.enrollment_path)
    client = client_for(pki, httpd.server_address[1], signer)
    monkeypatch.setattr(agent, "datetime", type("D", (), {"now": staticmethod(lambda tz=None: clock())}))
    assert agent.sync(client, cache) == 0
    assert agent.sync(client_for(pki, 9, signer), cache) == 3


def test_the_journal_seal_key_goes_to_fleet_once_and_leaves_the_device(pki, fleet, tmp_path, monkeypatch):
    """GATE-KERNEL bilag A pkt. 2: the FSS verification key can regenerate the
    sealing keys, so after Fleet has it (2xx) it is deleted here."""
    from app.gate import audit_seal

    signer, clock, start = fleet
    httpd, handler = start()
    monkeypatch.setattr(audit_seal, "SEAL_DIR", tmp_path / "seal")
    key = "aabbcc-ddeeff-001122/1a2b3c-35a4e900"
    assert audit_seal.setup(run=lambda *a, **k: type("R", (), {"returncode": 0, "stdout": key + "\n",
                                                                "stderr": ""})()) == 0
    monkeypatch.setattr(fleet_api, "ENROLLMENT_PATH", signer.enrollment_path)
    monkeypatch.setattr(agent, "datetime", type("D", (), {"now": staticmethod(lambda tz=None: clock())}))
    cache = RightsCache(tmp_path / "rights", enrollment_path=signer.enrollment_path)
    assert agent.sync(client_for(pki, httpd.server_address[1], signer), cache) == 0
    beats = [body for method, path, body in handler.seen if path.endswith("/v1/heartbeat")]
    assert beats[-1]["audit_seal"]["verify_key"] == key
    assert audit_seal.status() == "sealed" and audit_seal.state()["state"] == "fleet"
    assert not (tmp_path / "seal" / "verify-key").exists()
    assert audit_seal.for_fleet() is None  # never sent again


def test_an_undelivered_seal_key_stays_until_fleet_has_it(pki, fleet, tmp_path, monkeypatch):
    from app.gate import audit_seal

    signer, clock, start = fleet
    httpd, handler = start()
    handler.behaviour["post_status"] = 503
    monkeypatch.setattr(audit_seal, "SEAL_DIR", tmp_path / "seal")
    audit_seal.setup(run=lambda *a, **k: type("R", (), {"returncode": 0, "stdout": "aa-bb/1-2\n", "stderr": ""})())
    monkeypatch.setattr(fleet_api, "ENROLLMENT_PATH", signer.enrollment_path)
    monkeypatch.setattr(agent, "datetime", type("D", (), {"now": staticmethod(lambda tz=None: clock())}))
    cache = RightsCache(tmp_path / "rights", enrollment_path=signer.enrollment_path)
    agent.sync(client_for(pki, httpd.server_address[1], signer), cache)
    assert audit_seal.status() == "sealed_key_on_device" and audit_seal.pending_key() == "aa-bb/1-2"
