#!/usr/bin/env python3
"""Online SQLite backups and verified recovery-point restore for EiraOS."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import stat
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence
from uuid import uuid4

CHUNK_SIZE = 1024 * 1024


class BackupError(RuntimeError):
    pass


@dataclass(frozen=True)
class RecoveryPoint:
    format: str
    recovery_point_id: str
    created_at: str
    source_database: str
    snapshot_file: str
    snapshot_sha3_256: str
    snapshot_size: int
    sqlite_version: str
    integrity_check: str

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> "RecoveryPoint":
        try:
            return cls(**value)
        except TypeError as exc:
            raise BackupError("Invalid recovery-point manifest") from exc


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise BackupError(f"Invalid timestamp: {value}") from exc
    if parsed.tzinfo is None:
        raise BackupError("Timestamp must include a timezone")
    return parsed.astimezone(timezone.utc)


def _sha3_file(path: Path) -> str:
    digest = hashlib.sha3_256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _ensure_regular_file(path: Path, *, label: str) -> None:
    try:
        metadata = path.lstat()
    except FileNotFoundError as exc:
        raise BackupError(f"{label} does not exist: {path}") from exc
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise BackupError(f"{label} must be a regular non-symlink file: {path}")


def _integrity_check(path: Path) -> str:
    connection = sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True, timeout=5.0)
    try:
        rows = connection.execute("PRAGMA integrity_check").fetchall()
    finally:
        connection.close()
    result = "\n".join(str(row[0]) for row in rows)
    if result != "ok":
        raise BackupError(f"SQLite integrity check failed: {result}")
    return result


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


class SQLiteRecoveryEngine:
    """Create hot snapshots and restore to the latest point at/before a time."""

    def __init__(self, database: str | os.PathLike[str], backup_dir: str | os.PathLike[str]) -> None:
        self.database = Path(database).expanduser().resolve()
        self.backup_dir = Path(backup_dir).expanduser().resolve()

    def _prepare_backup_dir(self) -> None:
        self.backup_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        if self.backup_dir.is_symlink() or not self.backup_dir.is_dir():
            raise BackupError("Backup path must be a non-symlink directory")
        os.chmod(self.backup_dir, 0o700)

    def create_recovery_point(self, *, now: datetime | None = None) -> RecoveryPoint:
        _ensure_regular_file(self.database, label="Source database")
        self._prepare_backup_dir()
        created = (now or _utc_now()).astimezone(timezone.utc)
        recovery_id = f"{created.strftime('%Y%m%dT%H%M%S.%fZ')}-{uuid4().hex[:12]}"
        snapshot_name = f"eira-backup-{recovery_id}.sqlite3"
        snapshot = self.backup_dir / snapshot_name
        temporary = self.backup_dir / f".{snapshot_name}.tmp"

        source = sqlite3.connect(str(self.database), timeout=5.0)
        destination = sqlite3.connect(str(temporary), timeout=5.0)
        try:
            source.execute("PRAGMA busy_timeout = 5000")
            destination.execute("PRAGMA journal_mode = DELETE")
            source.backup(destination, pages=256, sleep=0.01)
            destination.commit()
        except sqlite3.Error as exc:
            raise BackupError(f"SQLite online backup failed: {exc}") from exc
        finally:
            destination.close()
            source.close()

        try:
            integrity = _integrity_check(temporary)
            os.chmod(temporary, 0o600)
            with temporary.open("rb") as handle:
                os.fsync(handle.fileno())
            os.replace(temporary, snapshot)
            digest = _sha3_file(snapshot)
            point = RecoveryPoint(
                format="eira-sqlite-recovery-point-v1",
                recovery_point_id=recovery_id,
                created_at=_timestamp(created),
                source_database=str(self.database),
                snapshot_file=snapshot_name,
                snapshot_sha3_256=digest,
                snapshot_size=snapshot.stat().st_size,
                sqlite_version=sqlite3.sqlite_version,
                integrity_check=integrity,
            )
            manifest = self.backup_dir / f"eira-backup-{recovery_id}.json"
            manifest_tmp = self.backup_dir / f".{manifest.name}.tmp"
            with manifest_tmp.open("x", encoding="utf-8") as handle:
                json.dump(asdict(point), handle, sort_keys=True, separators=(",", ":"))
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(manifest_tmp, 0o600)
            os.replace(manifest_tmp, manifest)
            _fsync_directory(self.backup_dir)
            return point
        finally:
            temporary.unlink(missing_ok=True)

    def recovery_points(self, *, verify: bool = True) -> list[RecoveryPoint]:
        self._prepare_backup_dir()
        points: list[RecoveryPoint] = []
        for manifest in sorted(self.backup_dir.glob("eira-backup-*.json")):
            _ensure_regular_file(manifest, label="Recovery manifest")
            try:
                value = json.loads(manifest.read_text(encoding="utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise BackupError(f"Invalid recovery manifest: {manifest}") from exc
            point = RecoveryPoint.from_mapping(value)
            if point.format != "eira-sqlite-recovery-point-v1":
                raise BackupError(f"Unsupported recovery format: {point.format}")
            snapshot = self.backup_dir / point.snapshot_file
            if snapshot.parent != self.backup_dir or snapshot.name != point.snapshot_file:
                raise BackupError("Recovery manifest contains an unsafe snapshot path")
            _ensure_regular_file(snapshot, label="Recovery snapshot")
            if verify:
                if snapshot.stat().st_size != point.snapshot_size:
                    raise BackupError(f"Recovery snapshot size mismatch: {snapshot}")
                if _sha3_file(snapshot) != point.snapshot_sha3_256:
                    raise BackupError(f"Recovery snapshot hash mismatch: {snapshot}")
                _integrity_check(snapshot)
            points.append(point)
        return sorted(points, key=lambda point: _parse_timestamp(point.created_at))

    def restore_at(
        self,
        target_time: datetime,
        output_database: str | os.PathLike[str],
        *,
        overwrite: bool = False,
    ) -> RecoveryPoint:
        target = target_time.astimezone(timezone.utc)
        candidates = [
            point
            for point in self.recovery_points(verify=True)
            if _parse_timestamp(point.created_at) <= target
        ]
        if not candidates:
            raise BackupError("No verified recovery point exists at or before target time")
        point = candidates[-1]
        output = Path(output_database).expanduser().resolve()
        if output == self.database:
            raise BackupError("Refusing to overwrite the live source database")
        if output.exists() and not overwrite:
            raise BackupError(f"Restore target already exists: {output}")
        output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if output.parent.is_symlink():
            raise BackupError("Restore parent must not be a symlink")

        snapshot = self.backup_dir / point.snapshot_file
        temporary = output.parent / f".{output.name}.{uuid4().hex}.tmp"
        source = sqlite3.connect(
            f"{snapshot.as_uri()}?mode=ro", uri=True, timeout=5.0
        )
        destination = sqlite3.connect(str(temporary), timeout=5.0)
        try:
            source.backup(destination, pages=256, sleep=0.01)
            destination.commit()
        except sqlite3.Error as exc:
            raise BackupError(f"SQLite restore failed: {exc}") from exc
        finally:
            destination.close()
            source.close()
        try:
            _integrity_check(temporary)
            os.chmod(temporary, 0o600)
            if output.exists() and overwrite:
                _ensure_regular_file(output, label="Restore target")
            os.replace(temporary, output)
            _fsync_directory(output.parent)
        finally:
            temporary.unlink(missing_ok=True)
        return point


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("backup", "verify"):
        child = subparsers.add_parser(name)
        child.add_argument("--database", required=True)
        child.add_argument("--backup-dir", required=True)
    restore = subparsers.add_parser("restore")
    restore.add_argument("--database", required=True, help="Live source DB (never overwritten)")
    restore.add_argument("--backup-dir", required=True)
    restore.add_argument("--target-time", required=True, help="ISO-8601 recovery time")
    restore.add_argument("--output", required=True)
    restore.add_argument("--overwrite", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    engine = SQLiteRecoveryEngine(args.database, args.backup_dir)
    try:
        if args.command == "backup":
            result: Any = asdict(engine.create_recovery_point())
        elif args.command == "verify":
            result = {"valid": True, "recovery_points": len(engine.recovery_points())}
        else:
            result = asdict(
                engine.restore_at(
                    _parse_timestamp(args.target_time),
                    args.output,
                    overwrite=args.overwrite,
                )
            )
    except BackupError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1
    print(json.dumps({"ok": True, "result": result}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
