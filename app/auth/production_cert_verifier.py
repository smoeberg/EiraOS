"""Fail-closed OIDC, X.509 and revocation verification for production eID.

Provider endpoints and trust anchors are deployment configuration.  This file
intentionally contains no invented MitID or EUDI production URL: a registered
broker/wallet provider must be pinned explicitly by the administrator.
"""

from __future__ import annotations

import hmac
import json
import ssl
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlsplit

from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import (
    ec,
    ed448,
    ed25519,
    padding,
    rsa,
)
from cryptography.x509 import ocsp
from cryptography.x509.oid import ExtendedKeyUsageOID

MAX_DISCOVERY_BYTES = 1024 * 1024
WEAK_SIGNATURE_HASHES = {"md5", "sha1"}
PRODUCTION_PROVIDER_TYPES = frozenset({"mitid_erhverv", "eudi_wallet"})


class ProductionCertificateError(ValueError):
    """A stable fail-closed validation error safe for audit logging."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class OIDCProviderPolicy:
    provider: str
    discovery_url: str
    issuer: str
    allowed_hosts: frozenset[str]
    require_revocation: bool = True

    def __init__(
        self,
        *,
        provider: str,
        discovery_url: str,
        issuer: str,
        allowed_hosts: Iterable[str],
        require_revocation: bool = True,
    ) -> None:
        normalized_provider = provider.strip().casefold()
        if normalized_provider not in PRODUCTION_PROVIDER_TYPES:
            raise ProductionCertificateError("provider_type_unsupported")
        object.__setattr__(self, "provider", normalized_provider)
        object.__setattr__(self, "discovery_url", discovery_url)
        object.__setattr__(self, "issuer", issuer)
        object.__setattr__(
            self,
            "allowed_hosts",
            frozenset(host.strip().casefold().rstrip(".") for host in allowed_hosts),
        )
        object.__setattr__(self, "require_revocation", require_revocation)


@dataclass(frozen=True)
class ProductionVerificationReport:
    valid: bool
    provider: str
    issuer: str
    discovery_url: str
    endpoint_hosts: tuple[str, ...]
    certificate_subject: str
    certificate_sha256: str
    revocation_sources: tuple[str, ...]
    checked_at: str

    def as_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["endpoint_hosts"] = list(self.endpoint_hosts)
        value["revocation_sources"] = list(self.revocation_sources)
        return value


JsonFetcher = Callable[[str], Mapping[str, Any]]


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        raise ProductionCertificateError("oidc_redirect_rejected")


def _certificate(value: x509.Certificate | bytes | str) -> x509.Certificate:
    if isinstance(value, x509.Certificate):
        return value
    raw = value.encode("utf-8") if isinstance(value, str) else value
    try:
        if b"-----BEGIN CERTIFICATE-----" in raw:
            return x509.load_pem_x509_certificate(raw)
        return x509.load_der_x509_certificate(raw)
    except ValueError as exc:
        raise ProductionCertificateError("x509_certificate_invalid") from exc


def _fingerprint(certificate: x509.Certificate) -> str:
    return certificate.fingerprint(hashes.SHA256()).hex()


def _now_utc(clock: Callable[[], float]) -> datetime:
    return datetime.fromtimestamp(clock(), tz=timezone.utc)


def _not_before(certificate: x509.Certificate) -> datetime:
    if hasattr(certificate, "not_valid_before_utc"):
        return certificate.not_valid_before_utc
    return certificate.not_valid_before.replace(tzinfo=timezone.utc)


def _not_after(certificate: x509.Certificate) -> datetime:
    if hasattr(certificate, "not_valid_after_utc"):
        return certificate.not_valid_after_utc
    return certificate.not_valid_after.replace(tzinfo=timezone.utc)


def _verify_signature(signed: Any, public_key: Any) -> None:
    algorithm = signed.signature_hash_algorithm
    if algorithm is not None and algorithm.name.casefold() in WEAK_SIGNATURE_HASHES:
        raise ProductionCertificateError("x509_weak_signature_algorithm")
    try:
        if isinstance(public_key, rsa.RSAPublicKey):
            parameters = getattr(signed, "signature_algorithm_parameters", None)
            public_key.verify(
                signed.signature,
                signed.tbs_certificate_bytes
                if isinstance(signed, x509.Certificate)
                else signed.tbs_certlist_bytes
                if isinstance(signed, x509.CertificateRevocationList)
                else signed.tbs_response_bytes,
                parameters if isinstance(parameters, padding.AsymmetricPadding) else padding.PKCS1v15(),
                algorithm,
            )
        elif isinstance(public_key, ec.EllipticCurvePublicKey):
            data = (
                signed.tbs_certificate_bytes
                if isinstance(signed, x509.Certificate)
                else signed.tbs_certlist_bytes
                if isinstance(signed, x509.CertificateRevocationList)
                else signed.tbs_response_bytes
            )
            public_key.verify(signed.signature, data, ec.ECDSA(algorithm))
        elif isinstance(public_key, (ed25519.Ed25519PublicKey, ed448.Ed448PublicKey)):
            data = (
                signed.tbs_certificate_bytes
                if isinstance(signed, x509.Certificate)
                else signed.tbs_certlist_bytes
                if isinstance(signed, x509.CertificateRevocationList)
                else signed.tbs_response_bytes
            )
            public_key.verify(signed.signature, data)
        else:
            raise ProductionCertificateError("x509_public_key_unsupported")
    except InvalidSignature as exc:
        raise ProductionCertificateError("x509_signature_invalid") from exc


def _url_host(
    url: str,
    allowed_hosts: frozenset[str],
    *,
    allow_query: bool,
) -> str:
    parsed = urlsplit(url)
    host = (parsed.hostname or "").casefold().rstrip(".")
    if parsed.scheme != "https" or not host:
        raise ProductionCertificateError("endpoint_https_required")
    if parsed.username or parsed.password or parsed.fragment:
        raise ProductionCertificateError("endpoint_url_invalid")
    if parsed.query and not allow_query:
        raise ProductionCertificateError("endpoint_query_rejected")
    if parsed.port not in (None, 443):
        raise ProductionCertificateError("endpoint_port_rejected")
    if host not in allowed_hosts:
        raise ProductionCertificateError("endpoint_host_not_allowlisted")
    return host


def _dns_matches(pattern: str, hostname: str) -> bool:
    pattern = pattern.casefold().rstrip(".")
    hostname = hostname.casefold().rstrip(".")
    if pattern == hostname:
        return True
    if not pattern.startswith("*."):
        return False
    suffix = pattern[2:]
    return hostname.endswith(f".{suffix}") and hostname.count(".") == suffix.count(".") + 1


class ProductionCertificateVerifier:
    def __init__(
        self,
        trust_anchors: Iterable[x509.Certificate | bytes | str],
        *,
        fetch_json: JsonFetcher | None = None,
        clock: Callable[[], float] = time.time,
        leeway_seconds: int = 60,
    ) -> None:
        self.trust_anchors = tuple(_certificate(item) for item in trust_anchors)
        if not self.trust_anchors:
            raise ProductionCertificateError("trust_anchor_missing")
        now = _now_utc(clock)
        for anchor in self.trust_anchors:
            if now < _not_before(anchor) or now > _not_after(anchor):
                raise ProductionCertificateError("trust_anchor_expired_or_not_yet_valid")
            try:
                constraints = anchor.extensions.get_extension_for_class(
                    x509.BasicConstraints
                ).value
            except x509.ExtensionNotFound as exc:
                raise ProductionCertificateError(
                    "trust_anchor_ca_constraint_missing"
                ) from exc
            if not constraints.ca:
                raise ProductionCertificateError("trust_anchor_not_ca")
        self.fetch_json = fetch_json or self._fetch_json
        self.clock = clock
        self.leeway = timedelta(seconds=max(0, leeway_seconds))

    @staticmethod
    def _fetch_json(url: str) -> Mapping[str, Any]:
        opener = urllib.request.build_opener(
            urllib.request.HTTPSHandler(context=ssl.create_default_context()),
            _NoRedirect(),
        )
        request = urllib.request.Request(
            url,
            headers={"Accept": "application/json", "User-Agent": "EiraOS/1.0-RC1"},
            method="GET",
        )
        try:
            with opener.open(request, timeout=5) as response:
                length = response.headers.get("Content-Length")
                if length and int(length) > MAX_DISCOVERY_BYTES:
                    raise ProductionCertificateError("oidc_discovery_too_large")
                body = response.read(MAX_DISCOVERY_BYTES + 1)
        except ProductionCertificateError:
            raise
        except (OSError, ValueError, urllib.error.URLError) as exc:
            raise ProductionCertificateError("oidc_discovery_unavailable") from exc
        if len(body) > MAX_DISCOVERY_BYTES:
            raise ProductionCertificateError("oidc_discovery_too_large")
        try:
            value = json.loads(body)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ProductionCertificateError("oidc_discovery_invalid_json") from exc
        if not isinstance(value, dict):
            raise ProductionCertificateError("oidc_discovery_not_object")
        return value

    def _validate_discovery(
        self,
        policy: OIDCProviderPolicy,
        document: Mapping[str, Any],
    ) -> tuple[str, ...]:
        if not policy.provider or not policy.allowed_hosts:
            raise ProductionCertificateError("provider_policy_invalid")
        _url_host(policy.discovery_url, policy.allowed_hosts, allow_query=False)
        issuer = str(document.get("issuer") or "")
        if not hmac.compare_digest(issuer.encode(), policy.issuer.encode()):
            raise ProductionCertificateError("oidc_issuer_mismatch")
        hosts = {
            _url_host(issuer, policy.allowed_hosts, allow_query=False),
        }
        for field, allow_query in (
            ("authorization_endpoint", True),
            ("token_endpoint", False),
            ("jwks_uri", False),
        ):
            value = document.get(field)
            if not isinstance(value, str):
                raise ProductionCertificateError(f"oidc_{field}_missing")
            hosts.add(_url_host(value, policy.allowed_hosts, allow_query=allow_query))
        response_types = document.get("response_types_supported")
        if not isinstance(response_types, list) or "code" not in response_types:
            raise ProductionCertificateError("oidc_authorization_code_required")
        algorithms = document.get("id_token_signing_alg_values_supported")
        if isinstance(algorithms, list) and "none" in algorithms:
            raise ProductionCertificateError("oidc_unsigned_tokens_advertised")
        return tuple(sorted(hosts))

    def _validate_chain(
        self,
        chain: Sequence[x509.Certificate | bytes | str],
        hostname: str,
    ) -> tuple[x509.Certificate, x509.Certificate]:
        certificates = tuple(_certificate(item) for item in chain)
        if not certificates:
            raise ProductionCertificateError("x509_chain_missing")
        now = _now_utc(self.clock)
        for certificate in certificates:
            if now + self.leeway < _not_before(certificate) or now - self.leeway > _not_after(certificate):
                raise ProductionCertificateError("x509_certificate_expired_or_not_yet_valid")
            algorithm = certificate.signature_hash_algorithm
            if algorithm is not None and algorithm.name.casefold() in WEAK_SIGNATURE_HASHES:
                raise ProductionCertificateError("x509_weak_signature_algorithm")

        leaf = certificates[0]
        try:
            basic = leaf.extensions.get_extension_for_class(x509.BasicConstraints).value
            if basic.ca:
                raise ProductionCertificateError("x509_leaf_is_ca")
        except x509.ExtensionNotFound:
            pass
        try:
            usage = leaf.extensions.get_extension_for_class(x509.KeyUsage).value
            if not usage.digital_signature:
                raise ProductionCertificateError("x509_leaf_not_for_signing")
        except x509.ExtensionNotFound:
            pass
        try:
            eku = leaf.extensions.get_extension_for_class(x509.ExtendedKeyUsage).value
            if ExtendedKeyUsageOID.SERVER_AUTH not in eku:
                raise ProductionCertificateError("x509_server_auth_missing")
        except x509.ExtensionNotFound:
            pass
        try:
            san = leaf.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
            dns_names = san.get_values_for_type(x509.DNSName)
        except x509.ExtensionNotFound as exc:
            raise ProductionCertificateError("x509_san_missing") from exc
        if not any(_dns_matches(name, hostname) for name in dns_names):
            raise ProductionCertificateError("x509_hostname_mismatch")

        for child, issuer in zip(certificates, certificates[1:]):
            if child.issuer != issuer.subject:
                raise ProductionCertificateError("x509_chain_issuer_mismatch")
            try:
                constraints = issuer.extensions.get_extension_for_class(x509.BasicConstraints).value
            except x509.ExtensionNotFound as exc:
                raise ProductionCertificateError("x509_issuer_ca_constraint_missing") from exc
            if not constraints.ca:
                raise ProductionCertificateError("x509_issuer_not_ca")
            try:
                issuer_usage = issuer.extensions.get_extension_for_class(x509.KeyUsage).value
                if not issuer_usage.key_cert_sign:
                    raise ProductionCertificateError("x509_issuer_key_cert_sign_missing")
            except x509.ExtensionNotFound:
                pass
            _verify_signature(child, issuer.public_key())

        anchor_fingerprints = {_fingerprint(anchor) for anchor in self.trust_anchors}
        last = certificates[-1]
        if _fingerprint(last) in anchor_fingerprints:
            issuer = certificates[1] if len(certificates) > 1 else last
            return leaf, issuer
        for anchor in self.trust_anchors:
            if last.issuer != anchor.subject:
                continue
            try:
                _verify_signature(last, anchor.public_key())
            except ProductionCertificateError:
                continue
            issuer = certificates[1] if len(certificates) > 1 else anchor
            return leaf, issuer
        raise ProductionCertificateError("x509_untrusted_chain")

    def _validate_crl(
        self,
        raw: bytes,
        leaf: x509.Certificate,
        issuer: x509.Certificate,
    ) -> None:
        try:
            crl = (
                x509.load_pem_x509_crl(raw)
                if b"-----BEGIN X509 CRL-----" in raw
                else x509.load_der_x509_crl(raw)
            )
        except ValueError as exc:
            raise ProductionCertificateError("crl_invalid") from exc
        if crl.issuer != issuer.subject:
            raise ProductionCertificateError("crl_issuer_mismatch")
        try:
            issuer_usage = issuer.extensions.get_extension_for_class(x509.KeyUsage).value
            if not issuer_usage.crl_sign:
                raise ProductionCertificateError("crl_issuer_usage_invalid")
        except x509.ExtensionNotFound:
            pass
        _verify_signature(crl, issuer.public_key())
        now = _now_utc(self.clock)
        if hasattr(crl, "last_update_utc"):
            last_update = crl.last_update_utc
            next_update = crl.next_update_utc
        else:
            last_update = crl.last_update.replace(tzinfo=timezone.utc)
            next_update = (
                crl.next_update.replace(tzinfo=timezone.utc)
                if crl.next_update is not None
                else None
            )
        if last_update > now + self.leeway or next_update is None or next_update < now - self.leeway:
            raise ProductionCertificateError("crl_stale")
        if crl.get_revoked_certificate_by_serial_number(leaf.serial_number) is not None:
            raise ProductionCertificateError("certificate_revoked")

    def _validate_ocsp(
        self,
        raw: bytes,
        leaf: x509.Certificate,
        issuer: x509.Certificate,
    ) -> None:
        try:
            response = ocsp.load_der_ocsp_response(raw)
        except ValueError as exc:
            raise ProductionCertificateError("ocsp_response_invalid") from exc
        if response.response_status is not ocsp.OCSPResponseStatus.SUCCESSFUL:
            raise ProductionCertificateError("ocsp_response_unsuccessful")
        responder = issuer
        embedded = tuple(response.certificates)
        if embedded:
            responder = embedded[0]
            if responder.subject != issuer.subject:
                if responder.issuer != issuer.subject:
                    raise ProductionCertificateError("ocsp_responder_untrusted")
                _verify_signature(responder, issuer.public_key())
                try:
                    eku = responder.extensions.get_extension_for_class(x509.ExtendedKeyUsage).value
                except x509.ExtensionNotFound as exc:
                    raise ProductionCertificateError("ocsp_signing_eku_missing") from exc
                if ExtendedKeyUsageOID.OCSP_SIGNING not in eku:
                    raise ProductionCertificateError("ocsp_signing_eku_missing")
        _verify_signature(response, responder.public_key())

        serial = response.serial_number
        if serial != leaf.serial_number:
            raise ProductionCertificateError("ocsp_serial_mismatch")
        if response.certificate_status is ocsp.OCSPCertStatus.REVOKED:
            raise ProductionCertificateError("certificate_revoked")
        if response.certificate_status is not ocsp.OCSPCertStatus.GOOD:
            raise ProductionCertificateError("ocsp_status_unknown")
        now = _now_utc(self.clock)
        if hasattr(response, "this_update_utc"):
            this_update = response.this_update_utc
            next_update = response.next_update_utc
        else:
            this_update = response.this_update.replace(tzinfo=timezone.utc)
            next_update = (
                response.next_update.replace(tzinfo=timezone.utc)
                if response.next_update is not None
                else None
            )
        if this_update > now + self.leeway:
            raise ProductionCertificateError("ocsp_response_from_future")
        if next_update is not None and next_update < now - self.leeway:
            raise ProductionCertificateError("ocsp_response_stale")
        if next_update is None and this_update < now - timedelta(hours=24):
            raise ProductionCertificateError("ocsp_response_stale")

    def verify(
        self,
        policy: OIDCProviderPolicy,
        certificate_chain: Sequence[x509.Certificate | bytes | str],
        *,
        discovery_document: Mapping[str, Any] | None = None,
        crl: bytes | None = None,
        ocsp_response: bytes | None = None,
    ) -> dict[str, Any]:
        document = discovery_document or self.fetch_json(policy.discovery_url)
        endpoint_hosts = self._validate_discovery(policy, document)
        discovery_host = _url_host(
            policy.discovery_url, policy.allowed_hosts, allow_query=False
        )
        leaf, issuer = self._validate_chain(certificate_chain, discovery_host)
        revocation_sources: list[str] = []
        if crl is not None:
            self._validate_crl(crl, leaf, issuer)
            revocation_sources.append("crl")
        if ocsp_response is not None:
            self._validate_ocsp(ocsp_response, leaf, issuer)
            revocation_sources.append("ocsp")
        if policy.require_revocation and not revocation_sources:
            raise ProductionCertificateError("revocation_evidence_required")
        return ProductionVerificationReport(
            valid=True,
            provider=policy.provider,
            issuer=policy.issuer,
            discovery_url=policy.discovery_url,
            endpoint_hosts=endpoint_hosts,
            certificate_subject=leaf.subject.rfc4514_string(),
            certificate_sha256=_fingerprint(leaf),
            revocation_sources=tuple(revocation_sources),
            checked_at=_now_utc(self.clock).isoformat(),
        ).as_dict()


def sha256_fingerprint(value: x509.Certificate | bytes | str) -> str:
    """Expose the normalized certificate fingerprint for pinned policies."""

    return _fingerprint(_certificate(value))
