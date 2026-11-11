"""OpenID Connect login — CP-OIDC-001, vendor-neutral (ADR-0004 D1, EIRA-IDENTITY 1.0).

identityd knows an OIDC provider only through configuration: a provider id
chosen by the installation, an issuer, a client id, and endpoints taken from
the issuer's discovery document. No provider is built in. Microsoft Entra is
one configuration among others (see config.example.env).

The gate's identity is ``did:eira:<provider-id>.<subject>``
(``eira_identity``). The provider id is bound to its issuer the first time it
is used, so a reconfiguration cannot silently map one provider's subjects onto
another's identities (``bind_provider``).
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode

import httpx

from app.auth.audit import record_auth_event
from app.auth.mock_guard import validate_mock_login_configuration
from app.database import get_connection, utc_now_iso
from app.session_store import create_session_from_claims

# Fail at import, before any login can be served (moved here from app.config,
# which identityd cannot import on an installed system).
validate_mock_login_configuration()

_STATE_TTL = timedelta(minutes=10)
_JWKS_TTL = timedelta(hours=1)
_DISCOVERY_TTL = timedelta(hours=1)

# Installation-chosen name of the provider: first segment of every identity
# it issues. No dot (the dot ends it), lowercase, so it fits EDP's did:eira:.
PROVIDER_ID = re.compile(r"^[a-z][a-z0-9-]{0,31}$")
# A subject used as-is in an identity; anything else is hashed (eira_identity).
_RAW_SUBJECT = re.compile(r"^[a-z0-9-]{1,64}$")
# Only RS256 is verified (_verify_jwt_signature).
_SUPPORTED_ALG = "RS256"


class OidcNotConfigured(PermissionError):
    """Live login is not configured on this machine (identityd answers
    live_login_unavailable)."""


def eira_identity(provider_id: str, subject: str, *, case_insensitive: bool = False) -> str:
    """``did:eira:<provider-id>.<subject>`` (EIRA-IDENTITY 1.0 §2).

    OIDC subjects are case-sensitive and may hold any character, while EDP
    identities are ``[a-z0-9_.-]``. A subject that is already lowercase
    ``[a-z0-9-]`` (at most 64) is used as-is; any other is replaced by
    ``_h`` + base32(SHA-256(subject)). Raw subjects never contain ``_``, so the
    two forms cannot collide. ``case_insensitive`` is for providers whose
    subject is a GUID (e.g. Entra's ``oid``): it is lowercased first.
    """
    if not PROVIDER_ID.fullmatch(provider_id or ""):
        raise ValueError("invalid provider id")
    value = (subject or "").strip()
    if not value or len(value) > 255:
        raise ValueError("subject is empty or too long")
    if case_insensitive:
        value = value.lower()
    if _RAW_SUBJECT.fullmatch(value):
        local = value
    else:
        digest = hashlib.sha256(value.encode("utf-8")).digest()
        local = "_h" + base64.b32encode(digest).decode("ascii").rstrip("=").lower()
    return f"did:eira:{provider_id}.{local}"
_NONCE_TTL = timedelta(minutes=10)


class JWKS:
    """Minimal JWKS container for RSA public keys."""

    def __init__(self, keys: list[dict[str, Any]]) -> None:
        # "use" and "alg" are optional in a JWK (RFC 7517 §4.2, §4.4); many
        # providers omit "use". A key stated for something else is skipped.
        self.keys = {
            k["kid"]: k
            for k in keys
            if k.get("kty") == "RSA"
            and k.get("use", "sig") == "sig"
            and k.get("alg", _SUPPORTED_ALG) == _SUPPORTED_ALG
            and "kid" in k
        }

    @classmethod
    def from_json(cls, jwks_json: dict[str, Any]) -> JWKS:
        return cls(jwks_json.get("keys", []))

    def get_key(self, kid: str) -> dict[str, Any] | None:
        return self.keys.get(kid)


class JWKSCache:
    """Simple in-memory JWKS cache with TTL."""

    def __init__(self) -> None:
        self._jwks: JWKS | None = None
        self._fetched_at: datetime | None = None
        self._jwks_url: str | None = None

    def get(self, jwks_url: str) -> JWKS | None:
        now = datetime.now(timezone.utc)
        if self._jwks is None or self._jwks_url != jwks_url:
            return None
        if now - self._fetched_at > _JWKS_TTL:
            return None
        return self._jwks

    def set(self, jwks_url: str, jwks: JWKS) -> None:
        self._jwks = jwks
        self._jwks_url = jwks_url
        self._fetched_at = datetime.now(timezone.utc)

    def clear(self) -> None:
        self._jwks = None
        self._jwks_url = None
        self._fetched_at = None


_jwks_cache = JWKSCache()


def _fetch_jwks(jwks_url: str) -> JWKS:
    """Fetch JWKS from URL, cache with TTL."""
    cached = _jwks_cache.get(jwks_url)
    if cached is not None:
        return cached

    with httpx.Client(timeout=10.0) as client:
        response = client.get(jwks_url)
        if response.status_code != 200:
            raise ValueError(f"JWKS fetch failed: {response.status_code}")
        jwks = JWKS.from_json(response.json())
        _jwks_cache.set(jwks_url, jwks)
        return jwks


def _rsa_public_key_from_jwk(jwk: dict[str, Any]) -> tuple[int, int]:
    """Extract (n, e) from JWK for RSA verification."""
    n = _base64url_decode(jwk["n"])
    e = _base64url_decode(jwk["e"])
    n_int = int.from_bytes(n, byteorder="big")
    e_int = int.from_bytes(e, byteorder="big")
    return n_int, e_int


def _base64url_decode(s: str) -> bytes:
    """Decode base64url-encoded string."""
    s = s.replace("-", "+").replace("_", "/")
    padding = 4 - len(s) % 4
    if padding != 4:
        s += "=" * padding
    return base64.b64decode(s)


def _verify_jwt_signature(token: str, jwk: dict[str, Any]) -> bool:
    """Verify JWT signature using RSA public key from JWK."""
    parts = token.split(".")
    if len(parts) != 3:
        return False
    signing_input = f"{parts[0]}.{parts[1]}".encode("ascii")
    signature = _base64url_decode(parts[2])

    n, e = _rsa_public_key_from_jwk(jwk)

    # RSA PKCS#1 v1.5 verification
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding, rsa

    try:
        public_key = rsa.RSAPublicNumbers(e, n).public_key()
        public_key.verify(
            signature,
            signing_input,
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
        return True
    except Exception:
        return False


@dataclass
class OidcConfig:
    provider_id: str
    issuer: str
    client_id: str
    client_secret: str
    redirect_uri: str
    scopes: str
    mock_enabled: bool
    display_name: str = ""
    subject_claim: str = "sub"
    subject_case_insensitive: bool = False
    groups_claim: str = "groups"
    org_claim: str = ""
    # Override the discovery document (all must be https).
    authorization_endpoint: str = ""
    token_endpoint: str = ""
    jwks_uri: str = ""

    def require_live(self) -> None:
        """Fail closed: live login needs an explicit provider. There is no
        default issuer."""
        if not PROVIDER_ID.fullmatch(self.provider_id or ""):
            raise OidcNotConfigured(
                "OIDC_PROVIDER_ID must be set (lowercase letters, digits and '-', at most 32)"
            )
        if not self.issuer.startswith("https://"):
            raise OidcNotConfigured("OIDC_ISSUER must be set to the provider's https issuer")
        if not self.client_id:
            raise OidcNotConfigured("OIDC_CLIENT_ID must be set")
        for name in ("authorization_endpoint", "token_endpoint", "jwks_uri"):
            value = getattr(self, name)
            if value and not value.startswith("https://"):
                raise OidcNotConfigured(f"{name} override must be https")

    def endpoint(self, name: str) -> str:
        """An endpoint (authorization_endpoint, token_endpoint, jwks_uri): its
        override, else the issuer's discovery document. Must be https."""
        value = getattr(self, name)
        if value:
            return value
        discovered = str(_discover(self.issuer).get(name) or "")
        if not discovered.startswith("https://"):
            raise ValueError(f"discovery document has no https {name}")
        return discovered

    def endpoints(self) -> dict[str, str]:
        return {n: self.endpoint(n) for n in ("authorization_endpoint", "token_endpoint", "jwks_uri")}

    def authorize_url(self) -> str:
        return self.endpoint("authorization_endpoint")

    def token_url(self) -> str:
        return self.endpoint("token_endpoint")

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id or None,
            "provider_name": self.display_name or self.provider_id or None,
            "issuer": self.issuer or None,
            "client_id": self.client_id or None,
            "redirect_uri": self.redirect_uri,
            "scopes": self.scopes,
            "mock_enabled": self.mock_enabled,
            "login_mode": "mock" if self.mock_enabled else "oidc",
            "login_path": "/v1/auth/oidc/mock-login" if self.mock_enabled else "/v1/auth/oidc/login",
            "callback_path": "/v1/auth/oidc/callback",
        }


_discovery_cache: dict[str, tuple[datetime, dict[str, Any]]] = {}


def _discover(issuer: str) -> dict[str, Any]:
    """OpenID Connect Discovery 1.0 §4: the document's issuer must be exactly
    the configured issuer, or nothing from it is used."""
    now = datetime.now(timezone.utc)
    cached = _discovery_cache.get(issuer)
    if cached is not None and now - cached[0] < _DISCOVERY_TTL:
        return cached[1]
    url = issuer.rstrip("/") + "/.well-known/openid-configuration"
    with httpx.Client(timeout=10.0) as client:
        response = client.get(url)
    if response.status_code != 200:
        raise ValueError(f"OIDC discovery failed: {response.status_code}")
    doc = response.json()
    if not isinstance(doc, dict) or doc.get("issuer") != issuer:
        raise ValueError("OIDC discovery issuer does not match the configured issuer")
    _discovery_cache[issuer] = (now, doc)
    return doc


def _flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes")


def load_oidc_config() -> OidcConfig:
    # Recheck on every load as well as import/startup, including tests or
    # launchers that alter the environment after Python imports this module.
    validate_mock_login_configuration()
    env = os.environ.get
    if env("OIDC_TENANT_ID", "").strip() and not env("OIDC_ISSUER", "").strip():
        # The old Entra-only setting: there is no built-in provider any more.
        raise OidcNotConfigured(
            "OIDC_TENANT_ID is no longer used: set OIDC_PROVIDER_ID and OIDC_ISSUER "
            "(see config.example.env for an Entra configuration)"
        )
    return OidcConfig(
        provider_id=env("OIDC_PROVIDER_ID", "").strip(),
        display_name=env("OIDC_PROVIDER_NAME", "").strip(),
        issuer=env("OIDC_ISSUER", "").strip(),
        client_id=env("OIDC_CLIENT_ID", "").strip(),
        client_secret=env("OIDC_CLIENT_SECRET", "").strip(),
        redirect_uri=env("OIDC_REDIRECT_URI", "http://localhost:8765/v1/auth/oidc/callback").strip(),
        scopes=env("OIDC_SCOPES", "openid profile email").strip(),
        mock_enabled=_flag("EIRA_OIDC_MOCK"),
        subject_claim=env("OIDC_SUBJECT_CLAIM", "sub").strip() or "sub",
        subject_case_insensitive=_flag("OIDC_SUBJECT_CASE_INSENSITIVE"),
        groups_claim=env("OIDC_GROUPS_CLAIM", "groups").strip() or "groups",
        org_claim=env("OIDC_ORG_CLAIM", "").strip(),
        authorization_endpoint=env("OIDC_AUTHORIZATION_ENDPOINT", "").strip(),
        token_endpoint=env("OIDC_TOKEN_ENDPOINT", "").strip(),
        jwks_uri=env("OIDC_JWKS_URI", "").strip(),
    )


def bind_provider(cfg: OidcConfig) -> None:
    """Pin the provider id to its issuer the first time it is used.

    Identities are ``did:eira:<provider-id>.<subject>``, and rights sets from
    Fleet name them. If the id were later pointed at another issuer, that
    issuer's subjects would become the old identities. Fail closed instead:
    changing a provider's issuer is an explicit administrative step.
    """
    with get_connection() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO oidc_provider_bindings (provider_id, issuer, bound_at)"
            " VALUES (?, ?, ?)",
            (cfg.provider_id, cfg.issuer, utc_now_iso()),
        )
        row = conn.execute(
            "SELECT issuer FROM oidc_provider_bindings WHERE provider_id = ?", (cfg.provider_id,)
        ).fetchone()
        conn.commit()
    if row is None or row["issuer"] != cfg.issuer:
        raise ValueError("provider_issuer_changed")


def _pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


def _store_auth_state(
    state: str,
    code_verifier: str,
    nonce: str | None = None,
    os_uid: int | None = None,
    redirect_uri: str | None = None,
) -> None:
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO oidc_auth_states (state, code_verifier, nonce, created_at, os_uid, redirect_uri)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (state, code_verifier, nonce, utc_now_iso(), os_uid, redirect_uri),
        )


def _pop_auth_state(state: str, os_uid: int | None = None) -> tuple[str, str | None] | None:
    found = pop_login_state(state, os_uid)
    return None if found is None else (found["code_verifier"], found["nonce"])


def pop_login_state(state: str, os_uid: int | None = None) -> dict[str, Any] | None:
    """Use a state once. With `os_uid`, only the OS user who started the login
    can complete it; another user's attempt does not consume it."""
    # One statement: a state can be used once, even by two concurrent callbacks.
    with get_connection() as conn:
        if os_uid is None:
            row = conn.execute(
                "DELETE FROM oidc_auth_states WHERE state = ?"
                " RETURNING code_verifier, nonce, created_at, redirect_uri",
                (state,),
            ).fetchone()
        else:
            row = conn.execute(
                "DELETE FROM oidc_auth_states WHERE state = ? AND os_uid = ?"
                " RETURNING code_verifier, nonce, created_at, redirect_uri",
                (state, os_uid),
            ).fetchone()
        conn.commit()
    if row is None:
        return None
    created = datetime.strptime(row["created_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) - created > _STATE_TTL:
        return None
    return {"code_verifier": row["code_verifier"], "nonce": row["nonce"], "redirect_uri": row["redirect_uri"]}


LOOPBACK_REDIRECT = re.compile(r"^http://127\.0\.0\.1:([1-9][0-9]{0,4})/callback$")


def validate_loopback_redirect(redirect_uri: str) -> str:
    """Desktop login (RFC 8252 §7.3): only the IPv4 loopback literal, an
    explicit port and the fixed path. Anything else could send the code to
    another host."""
    match = LOOPBACK_REDIRECT.match(redirect_uri or "")
    if not match or not 1024 <= int(match.group(1)) <= 65535:
        raise ValueError("redirect_uri must be http://127.0.0.1:<port>/callback (port 1024-65535)")
    return redirect_uri


def start_oidc_login(os_uid: int | None = None, redirect_uri: str | None = None) -> dict[str, str]:
    """Build the provider's authorize URL with PKCE state and nonce (live mode only).
    `os_uid` binds the login to the OS user who started it; `redirect_uri`
    is the desktop app's loopback (validated) instead of the configured one."""
    cfg = load_oidc_config()
    if redirect_uri is not None:
        validate_loopback_redirect(redirect_uri)
    if cfg.mock_enabled:
        raise PermissionError("Mock mode active — use POST /v1/auth/oidc/mock-login")
    cfg.require_live()

    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    verifier, challenge = _pkce_pair()
    _store_auth_state(state, verifier, nonce, os_uid, redirect_uri)

    params = {
        "client_id": cfg.client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri or cfg.redirect_uri,
        "response_mode": "query",
        "scope": cfg.scopes,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "nonce": nonce,
    }
    return {
        "authorize_url": f"{cfg.authorize_url()}?{urlencode(params)}",
        "state": state,
    }


def _decode_jwt_payload_unverified(token: str) -> dict[str, Any]:
    parts = token.split(".")
    if len(parts) < 2:
        raise ValueError("invalid id_token")
    padded = parts[1] + "=" * (-len(parts[1]) % 4)
    return json.loads(base64.urlsafe_b64decode(padded))


def _get_jwks_url(cfg: OidcConfig) -> str:
    """The provider's JWKS: OIDC_JWKS_URI, else ``jwks_uri`` from discovery."""
    return cfg.endpoint("jwks_uri")


def _verify_token_claims(payload: dict[str, Any], cfg: OidcConfig, nonce: str | None = None) -> None:
    """Verify iss, aud, exp, and nonce claims."""
    issuer = cfg.issuer
    if not issuer:
        raise ValueError("no issuer configured")

    # Verify iss
    token_iss = payload.get("iss")
    if not token_iss or token_iss != issuer:
        raise ValueError(f"iss mismatch: expected {issuer}, got {token_iss}")

    # Verify aud
    token_aud = payload.get("aud")
    if isinstance(token_aud, str):
        token_aud = [token_aud]
    if not token_aud or cfg.client_id not in token_aud:
        raise ValueError(f"aud mismatch: expected {cfg.client_id} in {token_aud}")

    # Verify exp
    token_exp = payload.get("exp")
    if token_exp is None:
        raise ValueError("missing exp claim")
    exp_time = datetime.fromtimestamp(token_exp, tz=timezone.utc)
    if datetime.now(timezone.utc) > exp_time:
        raise ValueError("token expired")

    # Verify nonce
    if nonce and payload.get("nonce") != nonce:
        raise ValueError("nonce mismatch")


def _verify_and_decode_id_token(id_token: str, cfg: OidcConfig, nonce: str | None = None) -> dict[str, Any]:
    """Verify JWT signature and claims, then decode payload."""
    parts = id_token.split(".")
    if len(parts) != 3:
        raise ValueError("invalid id_token format")

    # Get header to find kid
    header_b64 = parts[0] + "=" * (-len(parts[0]) % 4)
    header = json.loads(base64.urlsafe_b64decode(header_b64))
    if header.get("alg") != _SUPPORTED_ALG:
        raise ValueError(f"unsupported JWT alg {header.get('alg')!r}")
    kid = header.get("kid")
    if not kid:
        raise ValueError("missing kid in JWT header")

    # Fetch JWKS and verify signature
    jwks_url = _get_jwks_url(cfg)
    jwks = _fetch_jwks(jwks_url)
    jwk = jwks.get_key(kid)
    if jwk is None:
        raise ValueError(f"no matching key for kid {kid}")

    if not _verify_jwt_signature(id_token, jwk):
        raise ValueError("invalid signature")

    # Decode payload
    payload = _decode_jwt_payload_unverified(id_token)

    # Verify claims
    _verify_token_claims(payload, cfg, nonce)

    return payload


def claims_from_id_token(id_token: str, cfg: OidcConfig | None = None, nonce: str | None = None) -> dict[str, Any]:
    """Map verified id_token claims to EIRA session fields. Which claims hold
    the subject, groups and organisation is configuration, not code."""
    cfg = cfg or load_oidc_config()
    cfg.require_live()
    payload = _verify_and_decode_id_token(id_token, cfg, nonce)

    # Order kept from the Entra-only version, so actor ids of existing users
    # do not change.
    email = str(
        payload.get("preferred_username")
        or payload.get("email")
        or payload.get("upn")
        or ""
    ).strip().lower()
    if not email:
        raise ValueError("id_token missing email claim")

    name = str(payload.get("name") or email.split("@")[0])
    org = str(payload.get(cfg.org_claim) or "").strip() if cfg.org_claim else ""
    # The gate's identity is the provider's stable subject (EIRA-IDENTITY 1.0),
    # not an email: did:eira:<provider-id>.<subject>. EDP participants, the
    # gate and rights-set principals share this one form.
    subject = payload.get(cfg.subject_claim)
    if not isinstance(subject, str) or not subject.strip():
        raise ValueError(f"id_token missing or malformed {cfg.subject_claim} claim")
    try:
        identity = eira_identity(
            cfg.provider_id, subject, case_insensitive=cfg.subject_case_insensitive
        )
    except ValueError as exc:
        raise ValueError(f"id_token missing or malformed {cfg.subject_claim} claim: {exc}") from None
    groups = payload.get(cfg.groups_claim) or []
    if not isinstance(groups, list) or len(groups) > 200 or not all(isinstance(g, str) for g in groups):
        raise ValueError("id_token groups claim is malformed")

    return {
        "sub": payload.get("sub") or email,
        "email": email,
        "name": name,
        "org_unit": org or cfg.display_name or cfg.provider_id,
        "tenant_id": org,
        "identity": identity,
        "groups": sorted({g for g in groups if 0 < len(g) <= 128}),
        "idp": cfg.provider_id,
        "assurance_level": "idp_authenticated",
    }


def exchange_code_for_tokens(
    code: str, code_verifier: str, cfg: OidcConfig | None = None, redirect_uri: str | None = None
) -> dict[str, Any]:
    cfg = cfg or load_oidc_config()
    data: dict[str, str] = {
        "client_id": cfg.client_id,
        "scope": cfg.scopes,
        "code": code,
        # Must be the same redirect_uri as in the authorize request.
        "redirect_uri": redirect_uri or cfg.redirect_uri,
        "grant_type": "authorization_code",
        "code_verifier": code_verifier,
    }
    if cfg.client_secret:
        data["client_secret"] = cfg.client_secret

    with httpx.Client(timeout=30.0) as client:
        response = client.post(cfg.token_url(), data=data)
        if response.status_code >= 400:
            raise ValueError(f"token exchange failed: {response.status_code}")
        return response.json()


def complete_oidc_callback(
    *,
    code: str | None,
    state: str | None,
    error: str | None = None,
    error_description: str | None = None,
) -> dict[str, Any]:
    """Handle OAuth callback — exchange code, map claims, create session."""
    if error:
        reason = error_description or error
        fail_oidc_login(reason, detail={"mode": "oidc", "error": error})
        raise ValueError(reason)

    if not code or not state:
        fail_oidc_login("missing_code_or_state", detail={"mode": "oidc"})
        raise ValueError("missing authorization code or state")

    state_data = _pop_auth_state(state)
    if not state_data:
        fail_oidc_login("invalid_state", detail={"mode": "oidc"})
        raise ValueError("invalid or expired state")

    verifier, nonce = state_data

    try:
        tokens = exchange_code_for_tokens(code, verifier)
        id_token = tokens.get("id_token")
        if not id_token:
            raise ValueError("token response missing id_token")
        claims = claims_from_id_token(id_token, nonce=nonce)
        bind_provider(load_oidc_config())
        return complete_oidc_login(claims)
    except ValueError as exc:
        fail_oidc_login(str(exc), detail={"mode": "oidc"})
        raise


def claims_from_mock_login(body: dict[str, Any]) -> dict[str, Any]:
    """Create deliberately low-assurance mock claims from untrusted input."""
    email = str(body.get("email") or body.get("actor_id") or "").strip().lower()
    if not email or "@" not in email:
        raise ValueError("email required for mock login")

    name = str(body.get("name") or body.get("actor_name") or email.split("@")[0])

    # Tenant, organization, subject and identity-provider claims are server
    # controlled. Request data must never be able to assert trusted identity.
    return {
        "sub": email,
        "email": email,
        "name": name,
        "org_unit": "Mock",
        "tenant_id": "mock-tenant",
        "idp": "mock",
        "assurance_level": "mock_authenticated",
    }


def complete_oidc_login(claims: dict[str, Any], *, session_id: str | None = None) -> dict[str, Any]:
    """Create or bind session from OIDC claims; audit success."""
    sid = create_session_from_claims(claims, session_id=session_id)
    record_auth_event("auth.login.success", {
        "session_id": sid,
        "actor_id": claims.get("email") or claims.get("sub"),
        "idp": claims.get("idp", "oidc"),
        "tenant_id": claims.get("tenant_id"),
        "assurance_level": claims.get("assurance_level", "idp_authenticated"),
    })
    return {
        "session_id": sid,
        "actor_id": claims.get("email") or claims.get("sub"),
        "actor_name": claims.get("name"),
        "org_unit": claims.get("org_unit"),
        "assurance_level": claims.get("assurance_level", "idp_authenticated"),
    }


def fail_oidc_login(reason: str, *, detail: dict | None = None) -> None:
    record_auth_event("auth.login.failure", {
        "reason": reason,
        **(detail or {}),
    })


def mock_login(body: dict[str, Any]) -> dict[str, Any]:
    cfg = load_oidc_config()
    if not cfg.mock_enabled:
        raise PermissionError("Mock login disabled — set EIRA_OIDC_MOCK=1 explicitly")

    try:
        claims = claims_from_mock_login(body)
        return complete_oidc_login(claims, session_id=body.get("session_id"))
    except ValueError as exc:
        fail_oidc_login(str(exc), detail={"mode": "mock"})
        raise
