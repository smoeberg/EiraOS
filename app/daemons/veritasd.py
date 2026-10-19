"""In-process Veritas Shield JSON-RPC daemon."""

from __future__ import annotations

import hashlib
import json
import os
import sys
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.ipc.jsonrpc import INVALID_PARAMS, JsonRpcError
from app.veritas.c2pa_engine import C2PAEngine
from app.veritas.layer1_rules import Layer1RulesEngine
from app.veritas.layer2_qeaa import EUTrustedList, QEAAVerifier
from app.veritas.layer3_graph import Layer3GraphEngine

VERITAS_WEIGHTS = {
    "layer1": 0.30,
    "layer2": 0.35,
    "layer3": 0.20,
    "c2pa": 0.15,
}

# Reject text-like fields larger than this (JSON-RPC -32602).
_MAX_TEXT_BYTES = 1 * 1024 * 1024


def _input_digest(value: Mapping[str, Any]) -> str:
    canonical = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        default=lambda item: (
            f"<{type(item).__name__}:{len(item)} bytes>"
            if isinstance(item, bytes)
            else str(item)
        ),
    ).encode("utf-8")
    return hashlib.sha3_256(canonical).hexdigest()


def _qeaa_verifier_from_environment() -> QEAAVerifier:
    snapshot_path = os.getenv("EIRA_EUTL_SNAPSHOT", "").strip()
    if not snapshot_path:
        return QEAAVerifier()
    snapshot = Path(snapshot_path).read_text(encoding="utf-8")
    return QEAAVerifier(eutl_resolver=EUTrustedList.from_json(snapshot))


def _utf8_size(value: str) -> int:
    return len(value.encode("utf-8"))


def _fail_closed_result(reason: str = "intern fejl") -> dict[str, Any]:
    """Safe response when evaluation raises an unexpected exception."""
    issued_at = datetime.now(timezone.utc).isoformat()
    layer_scores = {name: 0.0 for name in VERITAS_WEIGHTS}
    empty_layer = {"score": 0.0, "flags": [], "details": {}}
    return {
        "media_type": "text",
        "trust_score": 0.0,
        "confidence": 0.0,
        "layers": {
            "layer1": dict(empty_layer),
            "layer2": dict(empty_layer),
            "layer3": dict(empty_layer),
            "c2pa": dict(empty_layer),
        },
        "rationale": [reason],
        "hud_certificate": {
            "certificate_type": "EIRA_VERITAS_HUD_V1",
            "input_sha3_256": "",
            "issued_at": issued_at,
            "trust_score": 0.0,
            "weights": dict(VERITAS_WEIGHTS),
            "layer_scores": layer_scores,
            "certificate_id": "veritas:fail-closed",
        },
    }


def validate_evaluate_params(params: Any) -> dict[str, Any]:
    """Validate veritas.evaluate / process_evidence params.

    Raises JsonRpcError(-32602) for missing/invalid structure or oversized payloads.
    """
    if not isinstance(params, Mapping):
        raise JsonRpcError(INVALID_PARAMS, "params must be an object")

    payload = dict(params)

    # Strip IPC auth envelope if still present (should already be stripped by server).
    payload.pop("_eira", None)

    document = payload.get("document")
    if document is not None and not isinstance(document, Mapping):
        raise JsonRpcError(INVALID_PARAMS, "document must be an object when provided")

    claim = payload.get("claim")
    if claim is not None and not isinstance(claim, Mapping):
        raise JsonRpcError(INVALID_PARAMS, "claim must be an object when provided")

    media = payload.get("media")
    if media is not None and not isinstance(media, Mapping):
        raise JsonRpcError(INVALID_PARAMS, "media must be an object when provided")

    credential = payload.get("credential", payload.get("qeaa"))
    if credential is not None and not isinstance(credential, (str, Mapping)):
        raise JsonRpcError(
            INVALID_PARAMS, "credential/qeaa must be a string or object when provided"
        )

    text_fields: list[str] = []
    for key in ("text", "body", "content", "url", "source", "source_domain"):
        value = payload.get(key)
        if isinstance(value, str):
            text_fields.append(value)
    if isinstance(document, Mapping):
        for key in ("text", "body", "content", "title"):
            value = document.get(key)
            if isinstance(value, str):
                text_fields.append(value)
    if isinstance(claim, Mapping):
        value = claim.get("text")
        if isinstance(value, str):
            text_fields.append(value)

    for field in text_fields:
        if _utf8_size(field) > _MAX_TEXT_BYTES:
            raise JsonRpcError(
                INVALID_PARAMS,
                f"text field exceeds {_MAX_TEXT_BYTES} bytes",
            )

    # Require at least one evaluable signal so empty/garbage calls fail clearly.
    has_signal = any(
        (
            isinstance(document, Mapping) and document,
            isinstance(claim, Mapping) and claim,
            isinstance(media, Mapping) and media,
            credential is not None,
            isinstance(payload.get("text"), str) and payload.get("text"),
            isinstance(payload.get("url"), str) and payload.get("url"),
            isinstance(payload.get("source_domain"), str) and payload.get("source_domain"),
            isinstance(payload.get("type"), str) and payload.get("type"),
            isinstance(payload.get("media_type"), str) and payload.get("media_type"),
        )
    )
    if not has_signal:
        raise JsonRpcError(
            INVALID_PARAMS,
            "params must include document, claim, media, credential, text, url, or media type",
        )

    return payload


class VeritasDaemon:
    def __init__(
        self,
        *,
        layer1: Layer1RulesEngine | None = None,
        layer2: QEAAVerifier | None = None,
        layer3: Layer3GraphEngine | None = None,
        c2pa: C2PAEngine | None = None,
    ) -> None:
        self.name = "eira-veritasd"
        self.layer1 = layer1 or Layer1RulesEngine()
        self.layer2 = layer2 or _qeaa_verifier_from_environment()
        self.layer3 = layer3 or Layer3GraphEngine()
        self.c2pa = c2pa or C2PAEngine()

    @staticmethod
    def _evaluate_layer(label: str, callback, *args, **kwargs) -> dict[str, Any]:
        """Fail closed for one layer without taking down the daemon."""
        try:
            return callback(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001 - layer boundary must fail closed
            print(
                f"[eira-veritasd] layer {label} failed: {type(exc).__name__}",
                file=sys.stderr,
            )
            return {
                "score": 0.0,
                "flags": (f"layer_error:{label}",),
                "details": {"error": type(exc).__name__},
            }

    def evaluate(self, input_data: Mapping[str, Any]) -> dict[str, Any]:
        """Run Veritas Shield layers with validation and fail-closed semantics.

        Invalid parameters raise JsonRpcError(-32602). Layer errors are caught
        per layer (score 0/flag) and unexpected exceptions fail closed with
        trust_score 0 and a generic rationale (no stack traces leak).
        """
        try:
            payload = validate_evaluate_params(input_data)
            return self._evaluate(payload)
        except JsonRpcError:
            raise
        except Exception as exc:  # noqa: BLE001 - IPC boundary: never leak internals
            print(
                f"[eira-veritasd] evaluation failed: {type(exc).__name__}",
                file=sys.stderr,
            )
            result = _fail_closed_result("intern fejl")
            # Surface only the exception type name (never the message/trace).
            result["hud_certificate"]["error"] = type(exc).__name__
            return result

    def process_evidence(self, input_data: Mapping[str, Any]) -> dict[str, Any]:
        """Process evidence through the same pipeline as ``evaluate``."""
        return self.evaluate(input_data)

    def _evaluate(self, payload: dict[str, Any]) -> dict[str, Any]:
        media_type = str(
            payload.get("type") or payload.get("media_type") or "text"
        ).casefold()

        layer1_input = payload.get("document")
        if not isinstance(layer1_input, Mapping):
            layer1_input = payload
        layer1 = self._evaluate_layer("layer1", self.layer1.evaluate, layer1_input)

        credential = payload.get("credential") or payload.get("qeaa")
        issuer_certificate = payload.get("issuer_certificate")
        layer2 = self._evaluate_layer(
            "layer2", self.layer2.verify, credential,
            issuer_certificate=issuer_certificate,
        )

        claim = payload.get("claim")
        if claim is None and payload.get("text"):
            claim = {
                "text": payload.get("text"),
                "source": payload.get("url") or payload.get("source_domain"),
                "observed_at": payload.get("observed_at"),
            }
        layer3 = self._evaluate_layer("layer3", self.layer3.evaluate, claim)

        media = payload.get("media")
        if media is None and media_type in {"image", "photo", "audio", "video", "c2pa"}:
            media = payload
        c2pa = self._evaluate_layer(
            "c2pa", self.c2pa.evaluate, media, mime_type=payload.get("mime_type")
        )

        layer_scores = {
            "layer1": float(layer1["score"]),
            "layer2": float(layer2["score"]),
            "layer3": float(layer3["score"]),
            "c2pa": float(c2pa["score"]),
        }
        # Clamp each layer contribution so a buggy provider cannot escape [0, 1].
        for name, score in list(layer_scores.items()):
            layer_scores[name] = max(0.0, min(1.0, score))

        normalised_score = sum(
            VERITAS_WEIGHTS[name] * layer_scores[name] for name in VERITAS_WEIGHTS
        )
        normalised_score = max(0.0, min(1.0, normalised_score))
        trust_score = round(normalised_score * 100, 2)
        trust_score = max(0.0, min(100.0, trust_score))

        rationale: list[str] = []
        for label, result in (
            ("Lag 1", layer1),
            ("Lag 2", layer2),
            ("Lag 3", layer3),
            ("C2PA", c2pa),
        ):
            flags = result.get("flags") or []
            if flags:
                rationale.append(f"{label}: {', '.join(str(flag) for flag in flags)}")
            else:
                rationale.append(f"{label}: ingen identificerede risikoflag")

        issued_at = datetime.now(timezone.utc).isoformat()
        digest = _input_digest(payload)
        hud_certificate = {
            "certificate_type": "EIRA_VERITAS_HUD_V1",
            "input_sha3_256": digest,
            "issued_at": issued_at,
            "trust_score": trust_score,
            "weights": dict(VERITAS_WEIGHTS),
            "layer_scores": layer_scores,
        }
        certificate_digest = hashlib.sha3_256(
            json.dumps(hud_certificate, sort_keys=True, separators=(",", ":")).encode(
                "utf-8"
            )
        ).hexdigest()
        hud_certificate["certificate_id"] = f"veritas:{certificate_digest}"

        return {
            "media_type": media_type,
            "trust_score": trust_score,
            "confidence": round(normalised_score, 4),
            "layers": {
                "layer1": layer1,
                "layer2": layer2,
                "layer3": layer3,
                "c2pa": c2pa,
            },
            "rationale": rationale,
            "hud_certificate": hud_certificate,
        }

    def run_loop(self) -> None:
        """Run veritasd under the shared runner lifecycle.

        Uses AF_UNIX sockets, SIGTERM/SIGINT graceful shutdown, and socket
        cleanup on exit — same path as ``python -m app.daemons.runner --daemon veritasd``.
        """
        from app.daemons.runner import main as runner_main

        raise SystemExit(runner_main(["--daemon", "veritasd"]))


def register_veritas_handlers(
    server, daemon: VeritasDaemon | None = None
) -> VeritasDaemon:
    service = daemon or VeritasDaemon()
    server.register("veritas.evaluate", service.evaluate)
    server.register("veritas.process_evidence", service.process_evidence)
    server.register("health", lambda _: {"daemon": service.name, "ok": True})
    return service


if __name__ == "__main__":
    VeritasDaemon().run_loop()
