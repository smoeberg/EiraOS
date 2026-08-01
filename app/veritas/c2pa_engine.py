"""C2PA manifest validation adapter and media-integrity scoring."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Protocol


class ManifestReader(Protocol):
    def read(self, media_path: Path) -> Mapping[str, Any] | None: ...


class C2PAToolReader:
    """Read and cryptographically validate manifests using official c2patool."""

    def __init__(self, executable: str = "c2patool", timeout: float = 20.0) -> None:
        self.executable = executable
        self.timeout = timeout

    @property
    def available(self) -> bool:
        return shutil.which(self.executable) is not None

    def read(self, media_path: Path) -> Mapping[str, Any] | None:
        if not self.available:
            return None
        completed = subprocess.run(
            [self.executable, str(media_path), "--json"],
            check=False,
            capture_output=True,
            text=True,
            timeout=self.timeout,
        )
        output = completed.stdout.strip() or completed.stderr.strip()
        if not output:
            return None
        try:
            parsed = json.loads(output)
        except json.JSONDecodeError as exc:
            raise ValueError("c2patool_invalid_json") from exc
        if not isinstance(parsed, dict):
            raise TypeError("c2patool_result_not_object")
        parsed.setdefault("tool_exit_code", completed.returncode)
        return parsed


@dataclass(frozen=True)
class C2PAResult:
    score: float
    valid: bool
    trusted: bool
    flags: tuple[str, ...]
    manifest: Mapping[str, Any] | None
    details: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["flags"] = list(self.flags)
        return result


def _walk_values(value: Any):
    if isinstance(value, Mapping):
        for key, child in value.items():
            yield str(key), child
            yield from _walk_values(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_values(child)


def _status_codes(manifest: Mapping[str, Any]) -> list[str]:
    result: list[str] = []
    for key, value in _walk_values(manifest):
        if key.casefold() in {"code", "status", "validation_status"}:
            if isinstance(value, str):
                result.append(value)
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, str):
                        result.append(item)
                    elif isinstance(item, Mapping) and item.get("code"):
                        result.append(str(item["code"]))
    return result


class C2PAEngine:
    """Evaluate images, audio and video without inventing provenance.

    AI detection is an explicit injected signal.  When no detector is
    configured, a missing C2PA manifest is reported as unknown, not as proof
    that content is human-made or AI-generated.
    """

    def __init__(
        self,
        *,
        manifest_reader: ManifestReader | None = None,
        ai_detector: Callable[[bytes | Path, str | None], float] | None = None,
    ) -> None:
        self.manifest_reader = manifest_reader or C2PAToolReader()
        self.ai_detector = ai_detector

    def _read_manifest(
        self, media: Mapping[str, Any] | bytes | str | Path | None
    ) -> tuple[Mapping[str, Any] | None, bytes | Path | None, bool]:
        if isinstance(media, Mapping):
            supplied = media.get("c2pa_manifest") or media.get("manifest")
            if isinstance(supplied, Mapping):
                return dict(supplied), None, False
            if media.get("path"):
                path = Path(str(media["path"]))
                return self.manifest_reader.read(path), path, False
            raw = media.get("bytes")
            if isinstance(raw, bytes):
                media = raw
            else:
                return None, None, False
        if isinstance(media, (str, Path)):
            path = Path(media)
            return self.manifest_reader.read(path), path, False
        if isinstance(media, bytes):
            with tempfile.NamedTemporaryFile(suffix=".bin") as handle:
                handle.write(media)
                handle.flush()
                manifest = self.manifest_reader.read(Path(handle.name))
            return manifest, media, False
        return None, None, False

    @staticmethod
    def _manifest_state(manifest: Mapping[str, Any]) -> tuple[bool, bool, list[str]]:
        codes = _status_codes(manifest)
        lowered = [code.casefold() for code in codes]
        explicit_valid = manifest.get("valid")
        explicit_trusted = manifest.get("trusted")
        failure = any(
            token in code
            for code in lowered
            for token in ("invalid", "mismatch", "error", "failure", "untrusted")
        )
        success = any(
            token in code
            for code in lowered
            for token in ("validated", "valid", "trusted")
        )
        has_manifest = bool(
            manifest.get("active_manifest") or manifest.get("manifests")
        )
        valid = (
            bool(explicit_valid)
            if explicit_valid is not None
            else has_manifest and success and not failure
        )
        trusted = (
            bool(explicit_trusted)
            if explicit_trusted is not None
            else valid and any("trusted" in code for code in lowered)
        )
        return valid, trusted, codes

    @staticmethod
    def _provenance_markers(manifest: Mapping[str, Any]) -> tuple[bool, bool]:
        serialised = json.dumps(manifest, sort_keys=True, default=str).casefold()
        hardware = any(
            marker in serialised
            for marker in (
                "digital capture",
                "digitalcapture",
                "camera",
                "hardware",
                "sensor",
            )
        )
        ai_generated = any(
            marker in serialised
            for marker in (
                "trainedalgorithmicmedia",
                "trained algorithmic media",
                "ai-generated",
                "ai_generated",
            )
        )
        return hardware, ai_generated

    def evaluate(
        self,
        media: Mapping[str, Any] | bytes | str | Path | None,
        *,
        mime_type: str | None = None,
    ) -> dict[str, Any]:
        flags: list[str] = []
        try:
            manifest, detector_input, _ = self._read_manifest(media)
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            return C2PAResult(
                score=0.10,
                valid=False,
                trusted=False,
                flags=("c2pa_validation_error",),
                manifest=None,
                details={"error": type(exc).__name__, "mime_type": mime_type},
            ).to_dict()

        ai_probability: float | None = None
        if self.ai_detector is not None and detector_input is not None:
            try:
                ai_probability = max(
                    0.0, min(1.0, float(self.ai_detector(detector_input, mime_type)))
                )
            except (OSError, RuntimeError, TypeError, ValueError):
                flags.append("ai_detector_error")

        if manifest is None:
            flags.append("c2pa_manifest_missing")
            if ai_probability is None:
                flags.append("ai_origin_unknown")
                score = 0.35
            elif ai_probability >= 0.75:
                flags.append("ai_generation_suspected")
                score = 0.12
            else:
                score = 0.40
            return C2PAResult(
                score=score,
                valid=False,
                trusted=False,
                flags=tuple(flags),
                manifest=None,
                details={"ai_probability": ai_probability, "mime_type": mime_type},
            ).to_dict()

        valid, trusted, status_codes = self._manifest_state(manifest)
        hardware_signed, ai_declared = self._provenance_markers(manifest)
        if not valid:
            flags.append("c2pa_manifest_invalid")
            score = 0.10
        elif not trusted:
            flags.append("c2pa_signer_untrusted")
            score = 0.70
        else:
            score = 0.94
        if hardware_signed and valid:
            score = min(1.0, score + 0.04)
        if ai_declared:
            flags.append("ai_generation_declared")
        if ai_probability is not None and ai_probability >= 0.75 and not ai_declared:
            flags.append("ai_signal_without_manifest_declaration")
            score = max(0.0, score - 0.20)

        # Invalid manifest contents are not exposed as trusted provenance data.
        safe_manifest = dict(manifest) if valid else None
        return C2PAResult(
            score=round(score, 4),
            valid=valid,
            trusted=trusted,
            flags=tuple(dict.fromkeys(flags)),
            manifest=safe_manifest,
            details={
                "status_codes": status_codes,
                "hardware_signed": hardware_signed,
                "ai_declared": ai_declared,
                "ai_probability": ai_probability,
                "mime_type": mime_type,
            },
        ).to_dict()

    analyze = evaluate
