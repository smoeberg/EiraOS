from __future__ import annotations

import base64
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import Encoding
from cryptography.x509 import ocsp
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from app.auth.production_cert_verifier import (
    OIDCProviderPolicy,
    ProductionCertificateError,
    ProductionCertificateVerifier,
)
from app.daemons.identityd import IdentityDaemon
from scripts.disaster_recovery_backup import BackupError, SQLiteRecoveryEngine


def _certificate_material(*, revoked: bool = False):
    now = datetime.now(timezone.utc)
    root_key = ec.generate_private_key(ec.SECP256R1())
    root_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Eira Test Root")])
    root = (
        x509.CertificateBuilder()
        .subject_name(root_name)
        .issuer_name(root_name)
        .public_key(root_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=365))
        .add_extension(x509.BasicConstraints(ca=True, path_length=1), critical=True)
        .sign(root_key, hashes.SHA256())
    )
    leaf_key = ec.generate_private_key(ec.SECP256R1())
    leaf = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "idp.example")]))
        .issuer_name(root.subject)
        .public_key(leaf_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(hours=1))
        .not_valid_after(now + timedelta(days=30))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.SubjectAlternativeName([x509.DNSName("idp.example")]), critical=False)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .sign(root_key, hashes.SHA256())
    )
    builder = (
        x509.CertificateRevocationListBuilder()
        .issuer_name(root.subject)
        .last_update(now - timedelta(minutes=5))
        .next_update(now + timedelta(days=1))
    )
    if revoked:
        builder = builder.add_revoked_certificate(
            x509.RevokedCertificateBuilder()
            .serial_number(leaf.serial_number)
            .revocation_date(now - timedelta(minutes=1))
            .build()
        )
    return (
        root_key,
        root,
        leaf,
        builder.sign(root_key, hashes.SHA256()).public_bytes(Encoding.DER),
    )


def _policy() -> OIDCProviderPolicy:
    return OIDCProviderPolicy(
        provider="eudi_wallet",
        discovery_url="https://idp.example/.well-known/openid-configuration",
        issuer="https://idp.example",
        allowed_hosts={"idp.example"},
    )


def _discovery() -> dict:
    return {
        "issuer": "https://idp.example",
        "authorization_endpoint": "https://idp.example/authorize",
        "token_endpoint": "https://idp.example/token",
        "jwks_uri": "https://idp.example/jwks",
        "response_types_supported": ["code"],
        "id_token_signing_alg_values_supported": ["ES256"],
    }


def test_production_certificate_requires_trust_chain_and_current_crl() -> None:
    _root_key, root, leaf, crl = _certificate_material()
    report = ProductionCertificateVerifier([root]).verify(
        _policy(), [leaf, root], discovery_document=_discovery(), crl=crl
    )
    assert report["valid"] is True
    assert report["provider"] == "eudi_wallet"
    assert report["revocation_sources"] == ["crl"]


def test_revoked_certificate_and_issuer_substitution_are_rejected() -> None:
    _root_key, root, leaf, revoked_crl = _certificate_material(revoked=True)
    verifier = ProductionCertificateVerifier([root])
    with pytest.raises(ProductionCertificateError, match="certificate_revoked"):
        verifier.verify(
            _policy(), [leaf, root], discovery_document=_discovery(), crl=revoked_crl
        )
    discovery = _discovery()
    discovery["issuer"] = "https://attacker.example"
    with pytest.raises(ProductionCertificateError, match="oidc_issuer_mismatch"):
        verifier.verify(
            _policy(), [leaf, root], discovery_document=discovery, crl=revoked_crl
        )


def test_identity_daemon_audits_successful_production_verification() -> None:
    _root_key, root, leaf, crl = _certificate_material()
    events: list[tuple[str, dict]] = []
    daemon = IdentityDaemon(
        policies={"eudi_wallet": _policy()},
        trust_anchors=[root],
        audit_sink=lambda event, details: events.append((event, details)),
    )
    result = daemon.verify_production_certificate(
        {
            "provider": "eudi_wallet",
            "certificate_chain": [
                leaf.public_bytes(Encoding.PEM).decode(),
                root.public_bytes(Encoding.PEM).decode(),
            ],
            "discovery_document": _discovery(),
            "crl": base64.b64encode(crl).decode(),
        }
    )
    assert result["valid"] is True
    assert events[0][0] == "identity.production_certificate_verified"


def test_production_certificate_accepts_fresh_issuer_signed_ocsp() -> None:
    root_key, root, leaf, _crl = _certificate_material()
    now = datetime.now(timezone.utc)
    response = (
        ocsp.OCSPResponseBuilder()
        .add_response(
            cert=leaf,
            issuer=root,
            algorithm=hashes.SHA256(),
            cert_status=ocsp.OCSPCertStatus.GOOD,
            this_update=now - timedelta(minutes=1),
            next_update=now + timedelta(hours=1),
            revocation_time=None,
            revocation_reason=None,
        )
        .responder_id(ocsp.OCSPResponderEncoding.HASH, root)
        .sign(root_key, hashes.SHA256())
        .public_bytes(Encoding.DER)
    )
    report = ProductionCertificateVerifier([root]).verify(
        _policy(),
        [leaf, root],
        discovery_document=_discovery(),
        ocsp_response=response,
    )
    assert report["revocation_sources"] == ["ocsp"]


def test_online_wal_backup_and_recovery_point_restore(tmp_path: Path) -> None:
    database = tmp_path / "eira.db"
    backup_dir = tmp_path / "backups"
    connection = sqlite3.connect(database)
    connection.execute("PRAGMA journal_mode = WAL")
    connection.execute("CREATE TABLE states (id INTEGER PRIMARY KEY, payload TEXT)")
    connection.execute("INSERT INTO states(payload) VALUES ('first')")
    connection.commit()

    engine = SQLiteRecoveryEngine(database, backup_dir)
    first_time = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)
    first = engine.create_recovery_point(now=first_time)
    connection.execute("INSERT INTO states(payload) VALUES ('second')")
    connection.commit()
    second_time = first_time + timedelta(minutes=5)
    engine.create_recovery_point(now=second_time)
    connection.close()

    restored = tmp_path / "restore.db"
    chosen = engine.restore_at(first_time + timedelta(minutes=1), restored)
    assert chosen.recovery_point_id == first.recovery_point_id
    with sqlite3.connect(restored) as restored_connection:
        assert restored_connection.execute("SELECT payload FROM states").fetchall() == [
            ("first",)
        ]


def test_backup_hash_tampering_blocks_restore(tmp_path: Path) -> None:
    database = tmp_path / "eira.db"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE data (value TEXT)")
        connection.execute("INSERT INTO data VALUES ('trusted')")
    engine = SQLiteRecoveryEngine(database, tmp_path / "backups")
    point = engine.create_recovery_point()
    snapshot = engine.backup_dir / point.snapshot_file
    with snapshot.open("ab") as handle:
        handle.write(b"tampered")
    with pytest.raises(BackupError, match="size mismatch"):
        engine.recovery_points(verify=True)
