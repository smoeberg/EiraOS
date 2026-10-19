"""Tests for OIDC JWKS signature verification and claims validation (Issue #28)."""

from __future__ import annotations

import base64
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from app.auth.oidc import (
    JWKS,
    OidcConfig,
    _verify_jwt_signature,
    _verify_token_claims,
    claims_from_id_token,
)


def _make_jwt(
    header: dict[str, str],
    payload: dict[str, any],
    private_key_pem: str,
) -> str:
    """Create a JWT signed with the given RSA private key."""
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding

    private_key = serialization.load_pem_private_key(private_key_pem.encode(), password=None)

    header_json = base64.urlsafe_b64encode(json.dumps(header).encode()).rstrip(b"=")
    payload_json = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=")

    signing_input = f"{header_json.decode()}.{payload_json.decode()}"
    signature = private_key.sign(
        signing_input.encode(),
        padding.PKCS1v15(),
        hashes.SHA256(),
    )
    signature_b64 = base64.urlsafe_b64encode(signature).rstrip(b"=")

    return f"{header_json.decode()}.{payload_json.decode()}.{signature_b64.decode()}"


def _make_rsa_key_pair() -> tuple[str, str, str, str]:
    """Generate RSA key pair and return PEM strings for private and public keys."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()

    public_key = private_key.public_key()
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()

    # Extract n and e for JWK
    n = public_key.public_numbers().n
    e = public_key.public_numbers().e
    n_b64 = base64.urlsafe_b64encode(n.to_bytes((n.bit_length() + 7) // 8, "big")).rstrip(b"=").decode()
    e_b64 = base64.urlsafe_b64encode(e.to_bytes(4, "big")).rstrip(b"=").decode()

    return private_pem, public_pem, n_b64, e_b64


@pytest.fixture
def rsa_keys():
    """Generate RSA key pair for testing."""
    return _make_rsa_key_pair()


@pytest.fixture
def valid_jwk(rsa_keys):
    """Create a valid JWK from the RSA key pair."""
    _, _, n_b64, e_b64 = rsa_keys
    return {
        "kty": "RSA",
        "use": "sig",
        "kid": "test-kid-1",
        "alg": "RS256",
        "n": n_b64,
        "e": e_b64,
    }


@pytest.fixture
def valid_jwks(valid_jwk):
    """Create a JWKS with the valid JWK."""
    return JWKS([valid_jwk])


@pytest.fixture
def oidc_config():
    """Create a test OIDC config."""
    return OidcConfig(
        issuer="https://login.microsoftonline.com/test-tenant/v2.0",
        client_id="test-client-id",
        client_secret="test-secret",
        redirect_uri="http://localhost:8765/v1/auth/oidc/callback",
        scopes="openid profile email",
        tenant_id="test-tenant",
        mock_enabled=False,
    )


class TestJWKS:
    def test_jwks_parsing(self, valid_jwk):
        """Test JWKS can be created from JSON."""
        jwks = JWKS.from_json({"keys": [valid_jwk]})
        assert jwks.get_key("test-kid-1") == valid_jwk
        assert jwks.get_key("nonexistent") is None

    def test_jwks_filters_rsa_sig_keys(self):
        """Test JWKS filters only RSA sig keys."""
        keys = [
            {"kty": "RSA", "use": "sig", "kid": "rsa-sig"},
            {"kty": "RSA", "use": "enc", "kid": "rsa-enc"},
            {"kty": "EC", "use": "sig", "kid": "ec-sig"},
        ]
        jwks = JWKS(keys)
        assert jwks.get_key("rsa-sig") is not None
        assert jwks.get_key("rsa-enc") is None
        assert jwks.get_key("ec-sig") is None


class TestJWTVerification:
    def test_verify_valid_signature(self, rsa_keys, valid_jwk):
        """Test that a valid signature is verified."""
        private_pem, _, _, _ = rsa_keys
        header = {"alg": "RS256", "typ": "JWT", "kid": "test-kid-1"}
        payload = {"sub": "test-user", "iss": "https://test-issuer.com", "exp": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp())}
        token = _make_jwt(header, payload, private_pem)

        assert _verify_jwt_signature(token, valid_jwk) is True

    def test_verify_invalid_signature(self, rsa_keys, valid_jwk):
        """Test that an invalid signature is rejected."""
        private_pem, _, _, _ = rsa_keys
        header = {"alg": "RS256", "typ": "JWT", "kid": "test-kid-1"}
        payload = {"sub": "test-user"}
        token = _make_jwt(header, payload, private_pem)

        # Modify the token to invalidate the signature
        parts = token.split(".")
        parts[1] = base64.urlsafe_b64encode(b'{"sub":"hacked"}').rstrip(b"=").decode()
        forged_token = ".".join(parts)

        assert _verify_jwt_signature(forged_token, valid_jwk) is False

    def test_verify_wrong_key(self, rsa_keys, valid_jwk):
        """Test that verification fails with wrong key."""
        private_pem, _, _, _ = rsa_keys
        header = {"alg": "RS256", "typ": "JWT", "kid": "test-kid-1"}
        payload = {"sub": "test-user"}
        token = _make_jwt(header, payload, private_pem)  # noqa: F841

        # Create a different key
        other_private_pem, _, _, _ = _make_rsa_key_pair()
        other_header = {"alg": "RS256", "typ": "JWT", "kid": "other-kid"}
        other_token = _make_jwt(other_header, payload, other_private_pem)

        # Try to verify with original key
        assert _verify_jwt_signature(other_token, valid_jwk) is False


class TestClaimsVerification:
    def test_verify_iss_mismatch(self, oidc_config):
        """Test that iss mismatch raises ValueError."""
        payload = {
            "iss": "https://evil-issuer.com/v2.0",
            "aud": "test-client-id",
            "exp": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()),
        }
        with pytest.raises(ValueError, match="iss mismatch"):
            _verify_token_claims(payload, oidc_config)

    def test_verify_aud_mismatch(self, oidc_config):
        """Test that aud mismatch raises ValueError."""
        payload = {
            "iss": "https://login.microsoftonline.com/test-tenant/v2.0",
            "aud": "other-client-id",
            "exp": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()),
        }
        with pytest.raises(ValueError, match="aud mismatch"):
            _verify_token_claims(payload, oidc_config)

    def test_verify_aud_list(self, oidc_config):
        """Test that aud can be a list containing client_id."""
        payload = {
            "iss": "https://login.microsoftonline.com/test-tenant/v2.0",
            "aud": ["test-client-id", "other-audience"],
            "exp": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()),
        }
        # Should not raise
        _verify_token_claims(payload, oidc_config)

    def test_verify_expired_token(self, oidc_config):
        """Test that expired token raises ValueError."""
        payload = {
            "iss": "https://login.microsoftonline.com/test-tenant/v2.0",
            "aud": "test-client-id",
            "exp": int((datetime.now(timezone.utc) - timedelta(hours=1)).timestamp()),
        }
        with pytest.raises(ValueError, match="token expired"):
            _verify_token_claims(payload, oidc_config)

    def test_verify_missing_exp(self, oidc_config):
        """Test that missing exp raises ValueError."""
        payload = {
            "iss": "https://login.microsoftonline.com/test-tenant/v2.0",
            "aud": "test-client-id",
        }
        with pytest.raises(ValueError, match="missing exp claim"):
            _verify_token_claims(payload, oidc_config)

    def test_verify_nonce_mismatch(self, oidc_config):
        """Test that nonce mismatch raises ValueError."""
        payload = {
            "iss": "https://login.microsoftonline.com/test-tenant/v2.0",
            "aud": "test-client-id",
            "exp": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()),
            "nonce": "expected-nonce",
        }
        with pytest.raises(ValueError, match="nonce mismatch"):
            _verify_token_claims(payload, oidc_config, nonce="different-nonce")

    def test_verify_nonce_when_none_provided(self, oidc_config):
        """Test that nonce verification is skipped when nonce is None."""
        payload = {
            "iss": "https://login.microsoftonline.com/test-tenant/v2.0",
            "aud": "test-client-id",
            "exp": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()),
            "nonce": "some-nonce",
        }
        # Should not raise when nonce is None (not provided)
        _verify_token_claims(payload, oidc_config, nonce=None)

    def test_verify_all_valid(self, oidc_config):
        """Test that valid claims pass verification."""
        payload = {
            "iss": "https://login.microsoftonline.com/test-tenant/v2.0",
            "aud": "test-client-id",
            "exp": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()),
            "nonce": "test-nonce",
        }
        _verify_token_claims(payload, oidc_config, nonce="test-nonce")


class TestClaimsFromIdToken:
    def test_valid_token_with_signature(self, rsa_keys, valid_jwks, oidc_config):
        """Test claims_from_id_token with valid signature and claims."""
        private_pem, _, _, _ = rsa_keys
        header = {"alg": "RS256", "typ": "JWT", "kid": "test-kid-1"}
        now = datetime.now(timezone.utc)
        payload = {
            "sub": "test-sub",
            "preferred_username": "test@example.com",
            "name": "Test User",
            "tid": "test-tenant",
            "iss": oidc_config.issuer,
            "aud": oidc_config.client_id,
            "exp": int((now + timedelta(hours=1)).timestamp()),
            "nonce": "test-nonce",
        }
        token = _make_jwt(header, payload, private_pem)

        with patch("app.auth.oidc._fetch_jwks") as mock_fetch:
            mock_fetch.return_value = valid_jwks
            claims = claims_from_id_token(token, oidc_config, nonce="test-nonce")

        assert claims["email"] == "test@example.com"
        assert claims["name"] == "Test User"
        assert claims["tenant_id"] == "test-tenant"
        assert claims["sub"] == "test-sub"
        assert claims["idp"] == "entra"

    def test_forged_token_rejected(self, rsa_keys, valid_jwks, oidc_config):
        """Test that a forged token is rejected."""
        private_pem, _, _, _ = rsa_keys
        header = {"alg": "RS256", "typ": "JWT", "kid": "test-kid-1"}
        now = datetime.now(timezone.utc)
        payload = {
            "sub": "test-sub",
            "preferred_username": "test@example.com",
            "iss": oidc_config.issuer,
            "aud": oidc_config.client_id,
            "exp": int((now + timedelta(hours=1)).timestamp()),
            "nonce": "test-nonce",
        }
        token = _make_jwt(header, payload, private_pem)

        # Forge the token by modifying the payload
        parts = token.split(".")
        forged_payload = {
            "sub": "hacker",
            "preferred_username": "hacker@evil.com",
            "iss": oidc_config.issuer,
            "aud": oidc_config.client_id,
            "exp": int((now + timedelta(hours=1)).timestamp()),
            "nonce": "test-nonce",
        }
        parts[1] = base64.urlsafe_b64encode(json.dumps(forged_payload).encode()).rstrip(b"=").decode()
        forged_token = ".".join(parts)

        with patch("app.auth.oidc._fetch_jwks") as mock_fetch:
            mock_fetch.return_value = valid_jwks
            with pytest.raises(ValueError, match="invalid signature"):
                claims_from_id_token(forged_token, oidc_config, nonce="test-nonce")

    def test_iss_mismatch_rejected(self, rsa_keys, valid_jwks, oidc_config):
        """Test that iss mismatch is rejected."""
        private_pem, _, _, _ = rsa_keys
        header = {"alg": "RS256", "typ": "JWT", "kid": "test-kid-1"}
        now = datetime.now(timezone.utc)
        payload = {
            "sub": "test-sub",
            "preferred_username": "test@example.com",
            "iss": "https://evil-issuer.com/v2.0",  # Wrong issuer
            "aud": oidc_config.client_id,
            "exp": int((now + timedelta(hours=1)).timestamp()),
            "nonce": "test-nonce",
        }
        token = _make_jwt(header, payload, private_pem)

        with patch("app.auth.oidc._fetch_jwks") as mock_fetch:
            mock_fetch.return_value = valid_jwks
            with pytest.raises(ValueError, match="iss mismatch"):
                claims_from_id_token(token, oidc_config, nonce="test-nonce")

    def test_expired_token_rejected(self, rsa_keys, valid_jwks, oidc_config):
        """Test that expired token is rejected."""
        private_pem, _, _, _ = rsa_keys
        header = {"alg": "RS256", "typ": "JWT", "kid": "test-kid-1"}
        payload = {
            "sub": "test-sub",
            "preferred_username": "test@example.com",
            "iss": oidc_config.issuer,
            "aud": oidc_config.client_id,
            "exp": int((datetime.now(timezone.utc) - timedelta(hours=1)).timestamp()),  # Expired
            "nonce": "test-nonce",
        }
        token = _make_jwt(header, payload, private_pem)

        with patch("app.auth.oidc._fetch_jwks") as mock_fetch:
            mock_fetch.return_value = valid_jwks
            with pytest.raises(ValueError, match="token expired"):
                claims_from_id_token(token, oidc_config, nonce="test-nonce")

    def test_nonce_replay_rejected(self, rsa_keys, valid_jwks, oidc_config):
        """Test that nonce replay is rejected."""
        private_pem, _, _, _ = rsa_keys
        header = {"alg": "RS256", "typ": "JWT", "kid": "test-kid-1"}
        now = datetime.now(timezone.utc)
        payload = {
            "sub": "test-sub",
            "preferred_username": "test@example.com",
            "iss": oidc_config.issuer,
            "aud": oidc_config.client_id,
            "exp": int((now + timedelta(hours=1)).timestamp()),
            "nonce": "expected-nonce",
        }
        token = _make_jwt(header, payload, private_pem)

        with patch("app.auth.oidc._fetch_jwks") as mock_fetch:
            mock_fetch.return_value = valid_jwks
            with pytest.raises(ValueError, match="nonce mismatch"):
                claims_from_id_token(token, oidc_config, nonce="different-nonce")

    def test_missing_kid_rejected(self, rsa_keys, valid_jwks, oidc_config):
        """Test that token without kid is rejected."""
        private_pem, _, _, _ = rsa_keys
        header = {"alg": "RS256", "typ": "JWT"}  # No kid
        now = datetime.now(timezone.utc)
        payload = {
            "sub": "test-sub",
            "preferred_username": "test@example.com",
            "iss": oidc_config.issuer,
            "aud": oidc_config.client_id,
            "exp": int((now + timedelta(hours=1)).timestamp()),
            "nonce": "test-nonce",
        }
        token = _make_jwt(header, payload, private_pem)

        with patch("app.auth.oidc._fetch_jwks") as mock_fetch:
            mock_fetch.return_value = valid_jwks
            with pytest.raises(ValueError, match="missing kid"):
                claims_from_id_token(token, oidc_config, nonce="test-nonce")

    def test_unknown_kid_rejected(self, rsa_keys, valid_jwks, oidc_config):
        """Test that token with unknown kid is rejected."""
        private_pem, _, _, _ = rsa_keys
        header = {"alg": "RS256", "typ": "JWT", "kid": "unknown-kid"}
        now = datetime.now(timezone.utc)
        payload = {
            "sub": "test-sub",
            "preferred_username": "test@example.com",
            "iss": oidc_config.issuer,
            "aud": oidc_config.client_id,
            "exp": int((now + timedelta(hours=1)).timestamp()),
            "nonce": "test-nonce",
        }
        token = _make_jwt(header, payload, private_pem)

        with patch("app.auth.oidc._fetch_jwks") as mock_fetch:
            mock_fetch.return_value = valid_jwks
            with pytest.raises(ValueError, match="no matching key"):
                claims_from_id_token(token, oidc_config, nonce="test-nonce")
