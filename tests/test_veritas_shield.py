from __future__ import annotations

import base64
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from cryptography.x509.oid import NameOID

from app.daemons.base import JsonRpcServer
from app.daemons.veritasd import (
    VERITAS_WEIGHTS,
    VeritasDaemon,
    register_veritas_handlers,
)
from app.ipc.client import IpcClient
from app.veritas.c2pa_engine import C2PAEngine
from app.veritas.layer1_rules import Layer1RulesEngine
from app.veritas.layer2_qeaa import EUTrustedList, QEAAVerifier
from app.veritas.layer3_graph import CallableGraphProvider, Layer3GraphEngine


def _b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _certificate() -> tuple[ec.EllipticCurvePrivateKey, x509.Certificate]:
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "EIRA QEAA Test QTSP")])
    now = datetime.now(timezone.utc)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=7))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )
    return key, certificate


def _sign_es256(
    key: ec.EllipticCurvePrivateKey,
    certificate: x509.Certificate,
    claims: dict,
    *,
    typ: str,
) -> str:
    header = {
        "alg": "ES256",
        "typ": typ,
        "x5c": [
            base64.b64encode(
                certificate.public_bytes(serialization.Encoding.DER)
            ).decode()
        ],
    }
    encoded_header = _b64url(json.dumps(header, separators=(",", ":")).encode())
    encoded_claims = _b64url(json.dumps(claims, separators=(",", ":")).encode())
    signing_input = f"{encoded_header}.{encoded_claims}".encode("ascii")
    der = key.sign(signing_input, ec.ECDSA(hashes.SHA256()))
    r, s = decode_dss_signature(der)
    signature = r.to_bytes(32, "big") + s.to_bytes(32, "big")
    return f"{encoded_header}.{encoded_claims}.{_b64url(signature)}"


def test_layer1_evaluates_known_sources() -> None:
    engine = Layer1RulesEngine(
        allowlist={"trusted.example"},
        denylist={"blocked.example"},
        trusted_authors={"Ada Reporter"},
        trusted_publishers={"Public News"},
    )
    trusted = engine.evaluate(
        {
            "url": "https://news.trusted.example/article",
            "text": "Kommunen offentliggjorde afgørelsen med kilder og dato.",
            "author": "Ada Reporter",
            "publisher": "Public News",
        }
    )
    blocked = engine.evaluate(
        {
            "url": "https://blocked.example/story",
            "text": "CHOKERENDE!!! DEL NU FØR DET SLETTES!!!",
        }
    )
    assert trusted["score"] > 0.9
    assert blocked["score"] < 0.35
    assert "source_denylisted" in blocked["flags"]


def test_qeaa_accepts_valid_sd_jwt_and_rejects_tampering() -> None:
    key, certificate = _certificate()
    now = int(datetime.now(timezone.utc).timestamp())
    disclosure = _b64url(json.dumps(["salt", "role", "org_acting"]).encode())
    digest = _b64url(hashlib.sha256(disclosure.encode("ascii")).digest())
    claims = {
        "iss": "https://qtsp.example",
        "vct": "urn:eira:credential:QEAA",
        "iat": now,
        "exp": now + 300,
        "_sd_alg": "sha-256",
        "_sd": [digest],
    }
    issuer_jwt = _sign_es256(key, certificate, claims, typ="dc+sd-jwt")
    credential = f"{issuer_jwt}~{disclosure}~"
    eutl = EUTrustedList([certificate.fingerprint(hashes.SHA256()).hex()])
    verifier = QEAAVerifier(eutl_resolver=eutl)

    valid = verifier.verify(credential)
    assert valid["valid"] is True
    assert valid["score"] == 1.0
    assert valid["format"] == "sd-jwt-vc"
    assert valid["certificate"]["eutl_trusted"] is True

    jws, disclosure_part, trailer = credential.split("~")
    header, payload, signature = jws.split(".")
    raw_signature = bytearray(
        base64.urlsafe_b64decode(signature + "=" * (-len(signature) % 4))
    )
    raw_signature[-1] ^= 1
    tampered = f"{header}.{payload}.{_b64url(bytes(raw_signature))}~{disclosure_part}~{trailer}"
    rejected = verifier.verify(tampered)
    assert rejected["valid"] is False
    assert rejected["score"] == 0.0
    assert "signature_invalid" in rejected["flags"]


def test_qeaa_accepts_w3c_vc_jwt() -> None:
    key, certificate = _certificate()
    now = int(datetime.now(timezone.utc).timestamp())
    claims = {
        "iss": "https://qtsp.example",
        "iat": now,
        "exp": now + 300,
        "vc": {
            "type": [
                "VerifiableCredential",
                "QualifiedElectronicAttestationOfAttributes",
            ],
            "credentialSubject": {"id": "did:example:holder"},
        },
    }
    credential = _sign_es256(key, certificate, claims, typ="vc+jwt")
    eutl = EUTrustedList([certificate.fingerprint(hashes.SHA256()).hex()])
    result = QEAAVerifier(eutl_resolver=eutl).verify(credential)
    assert result["valid"] is True
    assert result["format"] == "w3c-vc-jwt"


def test_temporal_contradiction_reduces_provenance_score() -> None:
    supporting = Layer3GraphEngine(
        CallableGraphProvider(
            lambda _: {
                "origin": {"source": "registry", "at": "2026-01-01"},
                "source_reliability": 0.9,
                "relations": [{"stance": "supports", "confidence": 0.9}],
            }
        )
    ).evaluate("Påstand")
    contradictory = Layer3GraphEngine(
        CallableGraphProvider(
            lambda _: {
                "origin": {"source": "registry", "at": "2026-01-01"},
                "source_reliability": 0.9,
                "relations": [
                    {"stance": "supports", "confidence": 0.4},
                    {"stance": "temporal_contradiction", "confidence": 1.0},
                ],
            }
        )
    ).evaluate("Påstand")
    assert contradictory["score"] < supporting["score"]
    assert "temporal_contradiction" in contradictory["flags"]
    assert len(contradictory["relation_links"]) == 2


def test_c2pa_reads_valid_hardware_manifest_mock() -> None:
    manifest = {
        "active_manifest": "urn:c2pa:test",
        "valid": True,
        "trusted": True,
        "validation_status": [{"code": "claimSignature.validated"}],
        "assertions": [
            {"label": "c2pa.actions", "digitalSourceType": "digitalCapture"},
            {"label": "eira.hardware", "camera": "Test Camera"},
        ],
    }
    result = C2PAEngine().evaluate({"c2pa_manifest": manifest}, mime_type="image/jpeg")
    assert result["valid"] is True
    assert result["trusted"] is True
    assert result["score"] >= 0.95
    assert result["manifest"]["active_manifest"] == "urn:c2pa:test"
    assert result["details"]["hardware_signed"] is True


def test_veritas_evaluate_over_ipc(tmp_path: Path, monkeypatch) -> None:
    """End-to-end veritas.evaluate over a real AF_UNIX socket (short path)."""
    import tempfile

    # AF_UNIX sockaddr path is limited (~108 bytes). Prefer a short /tmp dir.
    socket_root = Path(tempfile.mkdtemp(prefix="eirav-", dir="/tmp"))
    monkeypatch.setenv("EIRA_RUN_DIR", str(socket_root))
    server = JsonRpcServer(name="test-veritasd", daemon="veritasd")
    register_veritas_handlers(server, VeritasDaemon())
    params = {
        "type": "text",
        "url": "https://dr.dk/nyheder/test",
        "text": "En nøgtern oplysning med angivet kilde.",
        "author": "Journalist",
        "author_verified": True,
        "publisher": "DR",
        "publisher_verified": True,
    }
    socket_file = socket_root / "veritasd.sock"
    server.start()
    try:
        assert socket_file.exists(), f"expected live socket at {socket_file}"
        result = IpcClient("veritasd").call("veritas.evaluate", params)
    finally:
        server.stop()

    assert 0.0 <= result["trust_score"] <= 100.0
    expected = sum(
        VERITAS_WEIGHTS[name] * result["layers"][name]["score"]
        for name in VERITAS_WEIGHTS
    )
    assert result["trust_score"] == round(max(0.0, min(1.0, expected)) * 100, 2)
    assert result["hud_certificate"]["certificate_type"] == "EIRA_VERITAS_HUD_V1"
    assert result["hud_certificate"]["certificate_id"].startswith("veritas:")
    assert not socket_file.exists(), "socket must be cleaned up after stop"


def test_veritas_evaluate_rejects_invalid_params() -> None:
    from app.ipc.jsonrpc import JsonRpcError

    daemon = VeritasDaemon()
    with pytest.raises(JsonRpcError) as missing:
        daemon.evaluate({})
    assert missing.value.code == -32602

    with pytest.raises(JsonRpcError) as bad_document:
        daemon.evaluate({"document": "not-an-object"})
    assert bad_document.value.code == -32602

    with pytest.raises(JsonRpcError) as bad_claim:
        daemon.evaluate({"claim": 42})
    assert bad_claim.value.code == -32602

    huge = "x" * (1 * 1024 * 1024 + 1)
    with pytest.raises(JsonRpcError) as oversized:
        daemon.evaluate({"text": huge})
    assert oversized.value.code == -32602
    assert "exceeds" in oversized.value.message


def test_veritas_evaluate_invalid_params_over_jsonrpc() -> None:
    server = JsonRpcServer(name="test-veritasd-params", daemon="veritasd")
    register_veritas_handlers(server, VeritasDaemon())
    request = {
        "jsonrpc": "2.0",
        "id": 7,
        "method": "veritas.evaluate",
        "params": {"document": ["wrong"]},
    }
    response = json.loads(server.handle_line(json.dumps(request)))
    assert response["id"] == 7
    assert response["error"]["code"] == -32602


def test_veritas_evaluate_fail_closed_on_layer_crash() -> None:
    class BoomLayer1(Layer1RulesEngine):
        def evaluate(self, document):  # type: ignore[override]
            raise RuntimeError("secret stack detail should not leak")

    daemon = VeritasDaemon(layer1=BoomLayer1())
    result = daemon.evaluate(
        {
            "type": "text",
            "text": "Indhold der udløser lag-fejl.",
            "url": "https://example.org/item",
        }
    )
    assert result["trust_score"] == 0.0
    assert result["rationale"] == ["intern fejl"]
    joined = " ".join(result["rationale"])
    assert "secret stack" not in joined
    assert "RuntimeError" not in joined
    assert 0.0 <= result["trust_score"] <= 100.0


def test_process_evidence_matches_evaluate() -> None:
    daemon = VeritasDaemon()
    params = {
        "type": "text",
        "url": "https://example.org/news",
        "text": "Samme pipeline for process_evidence og evaluate.",
    }
    assert daemon.process_evidence(params)["trust_score"] == daemon.evaluate(params)[
        "trust_score"
    ]
