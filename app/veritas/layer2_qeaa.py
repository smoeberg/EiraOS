"""Cryptographic validation boundary for QEAA and EUDI credentials.

The verifier validates compact JWS/SD-JWT signatures locally and delegates the
policy decision "is this certificate/service currently trusted by the EUTL?"
to an injectable resolver.  This avoids treating an ordinary valid X.509 chain
as proof that a provider is a qualified EU trust service provider.
"""

from __future__ import annotations

import base64
import hashlib
import json
import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from itertools import pairwise
from typing import Any

from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, ed448, ed25519, padding, rsa
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature


class CredentialValidationError(ValueError):
    """Raised internally when a credential fails deterministic validation."""


EUTLResolver = Callable[[x509.Certificate, tuple[x509.Certificate, ...]], bool]


@dataclass(frozen=True)
class EUTrustedList:
    """Validated EUTL snapshot reduced to active service-certificate hashes.

    XML signature validation and refresh belong in the deployment updater;
    veritasd consumes only its fail-closed, locally pinned snapshot.
    """

    qualified_certificate_fingerprints: frozenset[str]

    def __init__(self, fingerprints: Iterable[str]) -> None:
        object.__setattr__(
            self,
            "qualified_certificate_fingerprints",
            frozenset(item.casefold().replace(":", "") for item in fingerprints),
        )

    @classmethod
    def from_json(cls, source: str | bytes | Mapping[str, Any]) -> EUTrustedList:
        if isinstance(source, Mapping):
            data = source
        else:
            raw = source.decode("utf-8") if isinstance(source, bytes) else source
            parsed = json.loads(raw)
            if not isinstance(parsed, Mapping):
                raise TypeError("EUTL snapshot must be a JSON object")
            data = parsed
        fingerprints = list(data.get("qualified_certificate_fingerprints") or [])
        services = data.get("services") or []
        if isinstance(services, list):
            for service in services:
                if not isinstance(service, Mapping):
                    continue
                status = str(service.get("status") or "").casefold()
                fingerprint = service.get("sha256_fingerprint")
                if fingerprint and status in {"granted", "recognised", "recognized"}:
                    fingerprints.append(str(fingerprint))
        return cls(str(item) for item in fingerprints)

    def __call__(
        self, leaf: x509.Certificate, chain: tuple[x509.Certificate, ...]
    ) -> bool:
        del chain
        return _cert_fingerprint(leaf) in self.qualified_certificate_fingerprints


@dataclass(frozen=True)
class QEAAResult:
    score: float
    valid: bool
    flags: tuple[str, ...]
    format: str | None
    claims: Mapping[str, Any] | None
    certificate: Mapping[str, Any] | None

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["flags"] = list(self.flags)
        return result


def _b64url_decode(value: str) -> bytes:
    try:
        return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except (ValueError, TypeError) as exc:
        raise CredentialValidationError("invalid_base64url") from exc


def _b64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _json_segment(value: str) -> dict[str, Any]:
    try:
        parsed = json.loads(_b64url_decode(value))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise CredentialValidationError("invalid_jws_json") from exc
    if not isinstance(parsed, dict):
        raise CredentialValidationError("jws_segment_not_object")
    return parsed


def _load_certificate(value: x509.Certificate | bytes | str) -> x509.Certificate:
    if isinstance(value, x509.Certificate):
        return value
    raw = value.encode("utf-8") if isinstance(value, str) else value
    try:
        if b"-----BEGIN CERTIFICATE-----" in raw:
            return x509.load_pem_x509_certificate(raw)
        return x509.load_der_x509_certificate(raw)
    except ValueError as exc:
        raise CredentialValidationError("invalid_certificate") from exc


def _cert_fingerprint(cert: x509.Certificate) -> str:
    return cert.fingerprint(hashes.SHA256()).hex()


def _verify_cert_signature(cert: x509.Certificate, issuer: x509.Certificate) -> None:
    public_key = issuer.public_key()
    if isinstance(public_key, rsa.RSAPublicKey):
        public_key.verify(
            cert.signature,
            cert.tbs_certificate_bytes,
            padding.PKCS1v15(),
            cert.signature_hash_algorithm,
        )
    elif isinstance(public_key, ec.EllipticCurvePublicKey):
        public_key.verify(
            cert.signature,
            cert.tbs_certificate_bytes,
            ec.ECDSA(cert.signature_hash_algorithm),
        )
    elif isinstance(public_key, (ed25519.Ed25519PublicKey, ed448.Ed448PublicKey)):
        public_key.verify(cert.signature, cert.tbs_certificate_bytes)
    else:  # pragma: no cover - future cryptography key types
        raise CredentialValidationError("unsupported_certificate_key")


def _verify_jws_signature(
    algorithm: str,
    public_key: Any,
    signing_input: bytes,
    signature: bytes,
) -> None:
    if algorithm == "ES256" and isinstance(public_key, ec.EllipticCurvePublicKey):
        if len(signature) != 64:
            raise CredentialValidationError("invalid_es256_signature_length")
        der_signature = encode_dss_signature(
            int.from_bytes(signature[:32], "big"),
            int.from_bytes(signature[32:], "big"),
        )
        public_key.verify(der_signature, signing_input, ec.ECDSA(hashes.SHA256()))
        return
    if algorithm == "RS256" and isinstance(public_key, rsa.RSAPublicKey):
        public_key.verify(signature, signing_input, padding.PKCS1v15(), hashes.SHA256())
        return
    if algorithm == "PS256" and isinstance(public_key, rsa.RSAPublicKey):
        public_key.verify(
            signature,
            signing_input,
            padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=32),
            hashes.SHA256(),
        )
        return
    if algorithm == "EdDSA" and isinstance(
        public_key, (ed25519.Ed25519PublicKey, ed448.Ed448PublicKey)
    ):
        public_key.verify(signature, signing_input)
        return
    raise CredentialValidationError("unsupported_or_mismatched_jws_algorithm")


def _collect_sd_digests(value: Any) -> set[str]:
    result: set[str] = set()
    if isinstance(value, dict):
        digests = value.get("_sd")
        if isinstance(digests, list):
            result.update(str(item) for item in digests)
        for child in value.values():
            result.update(_collect_sd_digests(child))
    elif isinstance(value, list):
        for child in value:
            result.update(_collect_sd_digests(child))
    return result


class QEAAVerifier:
    """Validate W3C VC JWT and SD-JWT VC signatures plus EU trust policy."""

    def __init__(
        self,
        *,
        trusted_certificates: Iterable[x509.Certificate | bytes | str] = (),
        eutl_resolver: EUTLResolver | None = None,
        clock: Callable[[], float] = time.time,
        leeway_seconds: int = 60,
    ) -> None:
        self.trusted_certificates = tuple(
            _load_certificate(item) for item in trusted_certificates
        )
        self.eutl_resolver = eutl_resolver
        self.clock = clock
        self.leeway_seconds = leeway_seconds

    def _certificate_from_header(
        self,
        header: Mapping[str, Any],
        supplied: x509.Certificate | bytes | str | None,
    ) -> tuple[x509.Certificate, tuple[x509.Certificate, ...]]:
        chain_values = header.get("x5c")
        chain: tuple[x509.Certificate, ...] = ()
        if isinstance(chain_values, list) and chain_values:
            try:
                chain = tuple(
                    x509.load_der_x509_certificate(
                        base64.b64decode(item, validate=True)
                    )
                    for item in chain_values
                )
            except (ValueError, TypeError) as exc:
                raise CredentialValidationError("invalid_x5c_chain") from exc
        if supplied is not None:
            leaf = _load_certificate(supplied)
            if chain and _cert_fingerprint(chain[0]) != _cert_fingerprint(leaf):
                raise CredentialValidationError("certificate_header_mismatch")
            if not chain:
                chain = (leaf,)
        if not chain:
            raise CredentialValidationError("signing_certificate_missing")
        return chain[0], chain

    def _certificate_chain_is_valid(
        self, leaf: x509.Certificate, chain: tuple[x509.Certificate, ...]
    ) -> bool:
        now = datetime.fromtimestamp(self.clock(), tz=timezone.utc)
        for cert in chain:
            if now < cert.not_valid_before_utc or now > cert.not_valid_after_utc:
                raise CredentialValidationError("certificate_expired_or_not_yet_valid")

        for child, issuer in pairwise(chain):
            if child.issuer != issuer.subject:
                raise CredentialValidationError("certificate_chain_issuer_mismatch")
            _verify_cert_signature(child, issuer)

        trusted_by_anchor = False
        anchor_fingerprints = {
            _cert_fingerprint(cert) for cert in self.trusted_certificates
        }
        if any(_cert_fingerprint(cert) in anchor_fingerprints for cert in chain):
            trusted_by_anchor = True
        elif self.trusted_certificates:
            last = chain[-1]
            for anchor in self.trusted_certificates:
                if last.issuer == anchor.subject:
                    try:
                        _verify_cert_signature(last, anchor)
                    except InvalidSignature:
                        continue
                    trusted_by_anchor = True
                    break

        if self.eutl_resolver is not None:
            return bool(self.eutl_resolver(leaf, chain))
        return trusted_by_anchor

    def _validate_time_claims(self, claims: Mapping[str, Any]) -> None:
        now = self.clock()
        leeway = self.leeway_seconds
        try:
            if "exp" in claims and float(claims["exp"]) < now - leeway:
                raise CredentialValidationError("credential_expired")
            if "nbf" in claims and float(claims["nbf"]) > now + leeway:
                raise CredentialValidationError("credential_not_yet_valid")
            if "iat" in claims and float(claims["iat"]) > now + leeway:
                raise CredentialValidationError("credential_issued_in_future")
        except (TypeError, ValueError) as exc:
            raise CredentialValidationError("invalid_numeric_date") from exc

    @staticmethod
    def _is_qeaa(claims: Mapping[str, Any]) -> bool:
        candidate_types: list[str] = []
        for key in ("vct", "type"):
            value = claims.get(key)
            if isinstance(value, str):
                candidate_types.append(value)
            elif isinstance(value, list):
                candidate_types.extend(str(item) for item in value)
        vc = claims.get("vc")
        if isinstance(vc, dict):
            value = vc.get("type")
            if isinstance(value, str):
                candidate_types.append(value)
            elif isinstance(value, list):
                candidate_types.extend(str(item) for item in value)
        for item in candidate_types:
            normalised = "".join(
                character for character in item.casefold() if character.isalnum()
            )
            if (
                "qeaa" in normalised
                or "qualifiedelectronicattestationofattributes" in normalised
            ):
                return True
        return False

    def _verify_sd_disclosures(
        self, claims: Mapping[str, Any], disclosures: Iterable[str]
    ) -> None:
        allowed = _collect_sd_digests(claims)
        algorithm = str(claims.get("_sd_alg", "sha-256")).lower()
        if algorithm != "sha-256":
            raise CredentialValidationError("unsupported_sd_hash_algorithm")
        for disclosure in disclosures:
            digest = _b64url_encode(hashlib.sha256(disclosure.encode("ascii")).digest())
            if digest not in allowed:
                raise CredentialValidationError("sd_disclosure_digest_mismatch")
            try:
                decoded = json.loads(_b64url_decode(disclosure))
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                raise CredentialValidationError("invalid_sd_disclosure") from exc
            if not isinstance(decoded, list) or len(decoded) not in (2, 3):
                raise CredentialValidationError("invalid_sd_disclosure_shape")

    def verify(
        self,
        credential: str | Mapping[str, Any] | None,
        *,
        issuer_certificate: x509.Certificate | bytes | str | None = None,
    ) -> dict[str, Any]:
        flags: list[str] = []
        credential_format: str | None = None
        claims: dict[str, Any] | None = None
        cert_details: dict[str, Any] | None = None

        try:
            if credential is None:
                raise CredentialValidationError("credential_missing")
            compact: str | None
            if isinstance(credential, str):
                compact = credential
            else:
                proof = credential.get("proof")
                compact = (
                    credential.get("jwt")
                    if isinstance(credential.get("jwt"), str)
                    else None
                )
                if compact is None and isinstance(proof, Mapping):
                    compact = proof.get("jwt") or proof.get("jws")
                if compact is None:
                    raise CredentialValidationError("unsupported_vc_proof")

            parts = compact.split("~")
            issuer_jws = parts[0]
            disclosures = [part for part in parts[1:] if part and part.count(".") != 2]
            jws_parts = issuer_jws.split(".")
            if len(jws_parts) != 3:
                raise CredentialValidationError("invalid_compact_jws")
            header = _json_segment(jws_parts[0])
            claims = _json_segment(jws_parts[1])
            algorithm = str(header.get("alg") or "")
            if not algorithm or algorithm.casefold() == "none":
                raise CredentialValidationError("unsafe_jws_algorithm")

            leaf, chain = self._certificate_from_header(header, issuer_certificate)
            _verify_jws_signature(
                algorithm,
                leaf.public_key(),
                f"{jws_parts[0]}.{jws_parts[1]}".encode("ascii"),
                _b64url_decode(jws_parts[2]),
            )
            self._validate_time_claims(claims)

            typ = str(header.get("typ") or "").casefold()
            if "sd-jwt" in typ or len(parts) > 1:
                credential_format = "sd-jwt-vc"
                self._verify_sd_disclosures(claims, disclosures)
            elif "vc" in claims or "credentialSubject" in claims:
                credential_format = "w3c-vc-jwt"
            else:
                credential_format = "jwt-vc"

            if not self._is_qeaa(claims):
                flags.append("qeaa_type_unconfirmed")

            eutl_trusted = self._certificate_chain_is_valid(leaf, chain)
            if not eutl_trusted:
                flags.append("issuer_not_eutl_trusted")

            cert_details = {
                "subject": leaf.subject.rfc4514_string(),
                "issuer": leaf.issuer.rfc4514_string(),
                "serial_number": str(leaf.serial_number),
                "sha256_fingerprint": _cert_fingerprint(leaf),
                "not_valid_before": leaf.not_valid_before_utc.isoformat(),
                "not_valid_after": leaf.not_valid_after_utc.isoformat(),
                "chain_length": len(chain),
                "eutl_trusted": eutl_trusted,
                "algorithm": algorithm,
            }
            qeaa_type = self._is_qeaa(claims)
            valid = eutl_trusted and qeaa_type
            score = 1.0 if valid else (0.65 if eutl_trusted else 0.25)
            return QEAAResult(
                score=score,
                valid=valid,
                flags=tuple(flags),
                format=credential_format,
                claims=claims,
                certificate=cert_details,
            ).to_dict()
        except (
            CredentialValidationError,
            InvalidSignature,
            ValueError,
            TypeError,
        ) as exc:
            flag = str(exc) if str(exc) else "signature_invalid"
            if isinstance(exc, InvalidSignature):
                flag = "signature_invalid"
            flags.append(flag)
            return QEAAResult(
                score=0.0,
                valid=False,
                flags=tuple(dict.fromkeys(flags)),
                format=credential_format,
                claims=None,
                certificate=cert_details,
            ).to_dict()

    evaluate = verify


# Backwards-friendly spelling for integrations that avoid CamelCase acronyms.
QEAA_Verifier = QEAAVerifier
