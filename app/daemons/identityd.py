"""Production identity-provider certificate verification daemon."""

from __future__ import annotations

import base64
import json
import os
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path
from typing import Any

from cryptography import x509

from app.auth.production_cert_verifier import (
    OIDCProviderPolicy,
    ProductionCertificateError,
    ProductionCertificateVerifier,
)
from app.ipc.client import IpcClient
from app.ipc.jsonrpc import JsonRpcError

IDENTITY_VALIDATION_FAILED = -32020


def _load_certificates(paths: Iterable[Path]) -> tuple[x509.Certificate, ...]:
    certificates: list[x509.Certificate] = []
    for path in paths:
        raw = path.read_bytes()
        try:
            certificates.append(x509.load_pem_x509_certificate(raw))
        except ValueError as exc:
            raise RuntimeError(f"Invalid trust anchor: {path}") from exc
    return tuple(certificates)


def _policy(value: Mapping[str, Any]) -> OIDCProviderPolicy:
    return OIDCProviderPolicy(
        provider=str(value["provider"]),
        discovery_url=str(value["discovery_url"]),
        issuer=str(value["issuer"]),
        allowed_hosts=[str(item) for item in value["allowed_hosts"]],
        require_revocation=bool(value.get("require_revocation", True)),
    )


def _read_configuration() -> tuple[dict[str, OIDCProviderPolicy], tuple[x509.Certificate, ...]]:
    config_path = Path(
        os.environ.get("EIRA_IDENTITY_PROVIDER_CONFIG", "/etc/eira/providers.json")
    )
    trust_dir = Path(os.environ.get("EIRA_IDENTITY_TRUST_DIR", "/etc/eira/trust"))
    if not config_path.is_file() or not trust_dir.is_dir():
        return {}, ()
    data = json.loads(config_path.read_text(encoding="utf-8"))
    providers = data.get("providers") if isinstance(data, dict) else None
    if not isinstance(providers, list):
        raise RuntimeError("providers.json must contain a providers array")
    parsed_policies = [_policy(item) for item in providers]
    policies = {policy.provider: policy for policy in parsed_policies}
    anchors = _load_certificates(sorted(trust_dir.glob("*.pem")))
    return policies, anchors


def _decode_optional(value: Any, field: str) -> bytes | None:
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        raise ProductionCertificateError(f"{field}_must_be_base64")
    try:
        return base64.b64decode(value, validate=True)
    except ValueError as exc:
        raise ProductionCertificateError(f"{field}_must_be_base64") from exc


AuditSink = Callable[[str, dict[str, Any]], None]


def _required_audit(event_type: str, details: dict[str, Any]) -> None:
    try:
        IpcClient("stated").call(
            "audit.append",
            {"event_type": event_type, "actor_id": "identityd", "details": details},
        )
    except Exception as exc:  # noqa: BLE001 - fail closed at audit boundary
        raise ProductionCertificateError("identity_audit_unavailable") from exc


class IdentityDaemon:
    def __init__(
        self,
        *,
        policies: Mapping[str, OIDCProviderPolicy] | None = None,
        trust_anchors: Iterable[x509.Certificate | bytes | str] = (),
        audit_sink: AuditSink = _required_audit,
    ) -> None:
        if policies is None:
            loaded_policies, loaded_anchors = _read_configuration()
            policies = loaded_policies
            trust_anchors = loaded_anchors
        self.policies = dict(policies)
        self.trust_anchors = tuple(trust_anchors)
        self.audit_sink = audit_sink

    def providers(self, _params: dict[str, Any]) -> dict[str, Any]:
        return {
            "configured": bool(self.policies and self.trust_anchors),
            "providers": sorted(self.policies),
        }

    def verify_production_certificate(self, params: dict[str, Any]) -> dict[str, Any]:
        provider = str(params.get("provider") or "").casefold()
        policy = self.policies.get(provider)
        if policy is None or not self.trust_anchors:
            raise JsonRpcError(
                IDENTITY_VALIDATION_FAILED,
                "identity_provider_not_configured",
                {"provider": provider},
            )
        chain = params.get("certificate_chain")
        if not isinstance(chain, list) or not chain:
            raise JsonRpcError(
                IDENTITY_VALIDATION_FAILED,
                "certificate_chain_required",
                {"provider": provider},
            )
        discovery = params.get("discovery_document")
        if discovery is not None and not isinstance(discovery, dict):
            raise JsonRpcError(
                IDENTITY_VALIDATION_FAILED,
                "discovery_document_invalid",
                {"provider": provider},
            )
        try:
            report = ProductionCertificateVerifier(self.trust_anchors).verify(
                policy,
                chain,
                discovery_document=discovery,
                crl=_decode_optional(params.get("crl"), "crl"),
                ocsp_response=_decode_optional(
                    params.get("ocsp_response"), "ocsp_response"
                ),
            )
            self.audit_sink(
                "identity.production_certificate_verified",
                {
                    "provider": provider,
                    "certificate_sha256": report["certificate_sha256"],
                    "revocation_sources": report["revocation_sources"],
                },
            )
            return report
        except ProductionCertificateError as exc:
            try:
                self.audit_sink(
                    "identity.production_certificate_rejected",
                    {"provider": provider, "reason": exc.code},
                )
            except ProductionCertificateError:
                pass
            raise JsonRpcError(
                IDENTITY_VALIDATION_FAILED,
                "production_certificate_rejected",
                {"provider": provider, "reason": exc.code},
            ) from exc


def register_identity_handlers(
    server: Any, daemon: IdentityDaemon | None = None
) -> IdentityDaemon:
    service = daemon or IdentityDaemon()
    server.register("identity.providers", service.providers)
    server.register(
        "identity.verify_production_certificate",
        service.verify_production_certificate,
    )
    server.register(
        "health",
        lambda _: {
            "daemon": "eira-identityd",
            "ok": True,
            "production_identity_configured": bool(
                service.policies and service.trust_anchors
            ),
        },
    )
    return service
