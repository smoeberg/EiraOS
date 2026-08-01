"""In-process Veritas Shield JSON-RPC daemon."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

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

    def evaluate(self, input_data: Mapping[str, Any]) -> dict[str, Any]:
        payload = dict(input_data)
        media_type = str(
            payload.get("type") or payload.get("media_type") or "text"
        ).casefold()

        layer1_input = payload.get("document")
        if not isinstance(layer1_input, Mapping):
            layer1_input = payload
        layer1 = self.layer1.evaluate(layer1_input)

        credential = payload.get("credential") or payload.get("qeaa")
        issuer_certificate = payload.get("issuer_certificate")
        layer2 = self.layer2.verify(
            credential,
            issuer_certificate=issuer_certificate,
        )

        claim = payload.get("claim")
        if claim is None and payload.get("text"):
            claim = {
                "text": payload.get("text"),
                "source": payload.get("url") or payload.get("source_domain"),
                "observed_at": payload.get("observed_at"),
            }
        layer3 = self.layer3.evaluate(claim)

        media = payload.get("media")
        if media is None and media_type in {"image", "photo", "audio", "video", "c2pa"}:
            media = payload
        c2pa = self.c2pa.evaluate(media, mime_type=payload.get("mime_type"))

        layer_scores = {
            "layer1": float(layer1["score"]),
            "layer2": float(layer2["score"]),
            "layer3": float(layer3["score"]),
            "c2pa": float(c2pa["score"]),
        }
        normalised_score = sum(
            VERITAS_WEIGHTS[name] * layer_scores[name] for name in VERITAS_WEIGHTS
        )
        trust_score = round(max(0.0, min(1.0, normalised_score)) * 100, 2)

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
        certificate_digest = _input_digest(hud_certificate)
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

    process_evidence = evaluate

    def run_loop(self) -> None:
        print(f"[{self.name}] ready")


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
