"""EIRA-IDENTITY 1.0: identities are did:eira:<provider-id>.<subject>, for any
OIDC provider the installation configures (ADR-0004 D1).

Covers the identity grammar, that existing Entra identities are unchanged,
the provider-to-issuer pin, and the JWT/JWKS rules a generic provider needs.
"""

from __future__ import annotations

import base64
import json
from datetime import datetime, timedelta, timezone

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from app.auth import oidc
from app.auth.oidc import JWKS, OidcConfig, bind_provider, claims_from_id_token, eira_identity
from app.gate.edp import IDENTITY as _IDENTITY_RE

ENTRA_OID = "7a9c1e4b-0000-4000-8000-000000000001"


# --- identity grammar --------------------------------------------------------

def test_raw_subject_is_kept():
    assert eira_identity("keycloak", "f3b2-11aa") == "did:eira:keycloak.f3b2-11aa"


def test_entra_identities_are_unchanged():
    """Rights sets already name did:eira:entra.<oid>; the Entra configuration
    (subject = oid, case-insensitive) must keep producing exactly that."""
    assert eira_identity("entra", ENTRA_OID.upper(), case_insensitive=True) == f"did:eira:entra.{ENTRA_OID}"


@pytest.mark.parametrize("subject", ["auth0|AbC123", "Anne", "248289761001", "a" * 65, "x@y.dk", "under_score"])
def test_other_subjects_are_hashed_and_fit_edp(subject):
    identity = eira_identity("idp", subject)
    assert _IDENTITY_RE.fullmatch(identity), identity
    local = identity.split(".", 1)[1]
    if subject == "248289761001":
        assert local == subject  # digits are already in the raw alphabet
    else:
        assert local.startswith("_h") and len(local) == 54


def test_case_is_significant_unless_configured_otherwise():
    """OIDC subjects are case-sensitive: "Anne" and "anne" are two people."""
    assert eira_identity("idp", "Anne") != eira_identity("idp", "anne")
    assert eira_identity("idp", "Anne", case_insensitive=True) == eira_identity("idp", "anne")


def test_raw_and_hashed_forms_cannot_collide():
    """A raw subject never contains "_", a hashed one always starts with "_h":
    a subject that looks like a hashed form is itself hashed."""
    hashed_local = eira_identity("idp", "Anne").split(".", 1)[1]
    assert eira_identity("idp", hashed_local) != f"did:eira:idp.{hashed_local}"


def test_longest_identity_fits_edp():
    identity = eira_identity("a" * 32, "Z" * 255)
    assert _IDENTITY_RE.fullmatch(identity)


@pytest.mark.parametrize("provider", ["", "Entra", "my.idp", "1x", "a" * 33])
def test_bad_provider_id(provider):
    with pytest.raises(ValueError):
        eira_identity(provider, "s")


@pytest.mark.parametrize("subject", ["", "   ", "x" * 256])
def test_bad_subject(subject):
    with pytest.raises(ValueError):
        eira_identity("idp", subject)


# --- a generic provider, end to end through token verification ---------------

@pytest.fixture(scope="module")
def key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _jwk(key, **extra):
    numbers = key.public_key().public_numbers()
    jwk = {"kty": "RSA", "kid": "k1",
           "n": _b64(numbers.n.to_bytes((numbers.n.bit_length() + 7) // 8, "big")),
           "e": _b64(numbers.e.to_bytes(3, "big"))}
    jwk.update(extra)
    return jwk


def _token(key, payload, alg="RS256"):
    header = _b64(json.dumps({"alg": alg, "typ": "JWT", "kid": "k1"}).encode())
    body = _b64(json.dumps(payload).encode())
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                            serialization.NoEncryption())
    signer = serialization.load_pem_private_key(pem, None)
    sig = signer.sign(f"{header}.{body}".encode(), padding.PKCS1v15(), hashes.SHA256())
    return f"{header}.{body}.{_b64(sig)}"


KEYCLOAK = OidcConfig(
    provider_id="keycloak", display_name="Kommunens login",
    issuer="https://login.kommune.example/realms/staff", client_id="eira-desktop",
    client_secret="", redirect_uri="http://127.0.0.1:1/callback", scopes="openid email",
    mock_enabled=False, jwks_uri="https://login.kommune.example/realms/staff/certs",
)


def _payload(**kw):
    now = datetime.now(timezone.utc)
    payload = {"iss": KEYCLOAK.issuer, "aud": KEYCLOAK.client_id, "sub": "6f1c0a52-9d1e-4c55-b2f4-0b9f1e0c7a11",
               "email": "anne@kommune.example", "name": "Anne", "groups": ["laerere"], "nonce": "n",
               "exp": int((now + timedelta(minutes=5)).timestamp())}
    payload.update(kw)
    return payload


def test_generic_provider_login(monkeypatch, key):
    """A JWKS without "use" (common outside Entra) and the standard "sub"."""
    monkeypatch.setattr(oidc, "_fetch_jwks", lambda url: JWKS([_jwk(key)]))
    claims = claims_from_id_token(_token(key, _payload()), KEYCLOAK, nonce="n")
    assert claims["identity"] == "did:eira:keycloak.6f1c0a52-9d1e-4c55-b2f4-0b9f1e0c7a11"
    assert claims["idp"] == "keycloak"
    assert claims["groups"] == ["laerere"]
    assert claims["org_unit"] == "Kommunens login"


def test_only_rs256_is_accepted(monkeypatch, key):
    monkeypatch.setattr(oidc, "_fetch_jwks", lambda url: JWKS([_jwk(key)]))
    with pytest.raises(ValueError, match="unsupported JWT alg"):
        claims_from_id_token(_token(key, _payload(), alg="none"), KEYCLOAK, nonce="n")


def test_key_declared_for_another_use_or_alg_is_ignored(key):
    assert JWKS([_jwk(key, use="enc")]).get_key("k1") is None
    assert JWKS([_jwk(key, alg="RS512")]).get_key("k1") is None
    assert JWKS([_jwk(key, use="sig", alg="RS256")]).get_key("k1") is not None


# --- provider pinned to its issuer --------------------------------------------

@pytest.fixture
def app_db(tmp_path, monkeypatch):
    from app import database

    path = tmp_path / "app.db"
    monkeypatch.setenv("EIRA_DB_PATH", str(path))
    monkeypatch.setattr(database, "DB_PATH", path)
    database.init_db()
    return path


def test_provider_is_pinned_to_its_first_issuer(app_db):
    bind_provider(KEYCLOAK)
    bind_provider(KEYCLOAK)  # same issuer again: fine
    moved = OidcConfig(**{**KEYCLOAK.__dict__, "issuer": "https://other.example/realms/staff"})
    with pytest.raises(ValueError, match="provider_issuer_changed"):
        bind_provider(moved)


def test_another_provider_id_binds_separately(app_db):
    bind_provider(KEYCLOAK)
    bind_provider(OidcConfig(**{**KEYCLOAK.__dict__, "provider_id": "skole",
                                "issuer": "https://other.example/realms/staff"}))
