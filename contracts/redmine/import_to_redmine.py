#!/usr/bin/env python3
"""
Import EIRA P1 issues into Redmine via REST API.

Usage:
  set REDMINE_URL=https://redmine.example.com
  set REDMINE_API_KEY=your-key
  set REDMINE_PROJECT=eira-os
  python import_to_redmine.py --dry-run
  python import_to_redmine.py

Requires: requests (pip install requests)
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
from pathlib import Path

try:
    import requests
except ImportError:
    print("pip install requests", file=sys.stderr)
    sys.exit(1)

CSV_PATH = Path(__file__).parent / "eira-p1-issues.csv"
ENV_PATH = Path(__file__).parent / "redmine.env"

# Redmine navn → id caches
_custom_field_ids: dict[str, int] = {}
_trackers: dict[str, int] = {}
_statuses: dict[str, int] = {}
_priorities: dict[str, int] = {}
_versions: dict[str, int] = {}
_users: dict[str, int] = {}
_subject_to_id: dict[str, int] = {}


def load_env_file(path: Path) -> None:
    """Load KEY=VALUE pairs into os.environ (does not override existing)."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if key and key not in os.environ:
            os.environ[key] = value


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def load_custom_field_ids() -> None:
    mapping = {
        "Contract ID": "REDMINE_CF_CONTRACT_ID",
        "Owner": "REDMINE_CF_OWNER",
        "Prompt path": "REDMINE_CF_PROMPT_PATH",
        "Contract status": "REDMINE_CF_CONTRACT_STATUS",
        "Depends on": "REDMINE_CF_DEPENDS_ON",
    }
    for csv_col, env_key in mapping.items():
        raw = env(env_key)
        if raw.isdigit():
            _custom_field_ids[csv_col] = int(raw)


def api_get(base: str, key: str, path: str, params: dict | None = None) -> dict:
    r = requests.get(
        f"{base.rstrip('/')}{path}",
        params=params,
        headers={"X-Redmine-API-Key": key},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


def api_post(base: str, key: str, path: str, body: dict) -> dict:
    r = requests.post(
        f"{base.rstrip('/')}{path}",
        json=body,
        headers={"X-Redmine-API-Key": key, "Content-Type": "application/json"},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


def load_metadata(base: str, key: str, project_id: str) -> int:
    """Load trackers, statuses, priorities, versions, users. Return project numeric id."""
    projects = api_get(base, key, "/projects.json", {"limit": 100})
    project_numeric_id = None
    for p in projects.get("projects", []):
        if p.get("identifier") == project_id or p.get("name") == project_id:
            project_numeric_id = p["id"]
            break
    if project_numeric_id is None:
        raise SystemExit(f"Project not found: {project_id}")

    meta = api_get(base, key, f"/projects/{project_id}.json", {"include": "trackers"})
    for t in meta.get("project", {}).get("trackers", []):
        _trackers[t["name"].lower()] = t["id"]

    enums = api_get(base, key, "/enumerations/issue_priorities.json")
    for p in enums.get("issue_priorities", []):
        _priorities[p["name"].lower()] = p["id"]

    statuses = api_get(base, key, "/issue_statuses.json")
    for s in statuses.get("issue_statuses", []):
        _statuses[s["name"].lower()] = s["id"]

    versions = api_get(
        base, key, f"/projects/{project_id}/versions.json", {"limit": 100}
    )
    for v in versions.get("versions", []):
        _versions[v["name"].lower()] = v["id"]

    users = api_get(base, key, "/users.json", {"limit": 100})
    for u in users.get("users", []):
        login = (u.get("login") or "").lower()
        if login:
            _users[login] = u["id"]

    return project_numeric_id


def resolve_id(mapping: dict[str, int], name: str, kind: str) -> int | None:
    if not name:
        return None
    key = name.strip().lower()
    if key in mapping:
        return mapping[key]
    print(f"  WARNING: unknown {kind} '{name}' — skipped", file=sys.stderr)
    return None


def existing_subjects(base: str, key: str, project_id: str) -> set[str]:
    found: set[str] = set()
    offset = 0
    while True:
        data = api_get(
            base,
            key,
            "/issues.json",
            {
                "project_id": project_id,
                "limit": 100,
                "offset": offset,
                "status_id": "*",
            },
        )
        issues = data.get("issues", [])
        if not issues:
            break
        for i in issues:
            found.add(i["subject"])
            _subject_to_id[i["subject"]] = i["id"]
        offset += len(issues)
        if offset >= data.get("total_count", 0):
            break
    return found


def read_csv() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    with CSV_PATH.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append({k: (v or "").strip() for k, v in row.items()})
    return rows


def build_issue_payload(
    row: dict[str, str],
    project_numeric_id: int,
) -> dict:
    issue: dict = {
        "project_id": project_numeric_id,
        "subject": row["Subject"],
        "description": row.get("Description", ""),
    }

    tid = resolve_id(_trackers, row.get("Tracker", ""), "tracker")
    if tid:
        issue["tracker_id"] = tid

    sid = resolve_id(_statuses, row.get("Status", "New"), "status")
    if sid:
        issue["status_id"] = sid

    pid = resolve_id(_priorities, row.get("Priority", ""), "priority")
    if pid:
        issue["priority_id"] = pid

    assignee = row.get("Assignee", "")
    if assignee:
        uid = _users.get(assignee.lower())
        if uid:
            issue["assigned_to_id"] = uid

    version = row.get("Target version", "")
    if version:
        vid = resolve_id(_versions, version, "version")
        if vid:
            issue["fixed_version_id"] = vid

    hours = row.get("Estimated hours", "")
    if hours:
        try:
            issue["estimated_hours"] = float(hours)
        except ValueError:
            pass

    parent_subject = row.get("Parent task", "")
    if parent_subject and parent_subject in _subject_to_id:
        issue["parent_issue_id"] = _subject_to_id[parent_subject]

    custom_fields: list[dict] = []
    for col, field_id in _custom_field_ids.items():
        value = row.get(col, "").strip()
        if value:
            custom_fields.append({"id": field_id, "value": value})
    if custom_fields:
        issue["custom_fields"] = custom_fields

    return issue


def main() -> None:
    parser = argparse.ArgumentParser(description="Import EIRA issues to Redmine")
    parser.add_argument("--dry-run", action="store_true", help="Print only, no API writes")
    parser.add_argument("--skip-existing", action="store_true", default=True)
    parser.add_argument("--csv", type=Path, default=CSV_PATH)
    args = parser.parse_args()

    load_env_file(ENV_PATH)

    base = env("REDMINE_URL")
    key = env("REDMINE_API_KEY")
    project = env("REDMINE_PROJECT", "eira-os")

    load_custom_field_ids()

    if not base or not key:
        print("Set REDMINE_URL and REDMINE_API_KEY (or copy redmine.env.example → redmine.env)", file=sys.stderr)
        sys.exit(1)

    global CSV_PATH
    CSV_PATH = args.csv

    if _custom_field_ids:
        print(f"Custom fields: {list(_custom_field_ids.keys())}")
    else:
        print("No custom field IDs — set REDMINE_CF_* in redmine.env for contract metadata")

    print(f"Project: {project}")
    print(f"CSV: {CSV_PATH}")
    project_id = load_metadata(base, key, project)
    print(f"Resolved project id: {project_id}")

    existing = existing_subjects(base, key, project) if args.skip_existing else set()
    rows = read_csv()

    created = 0
    skipped = 0

    for row in rows:
        subject = row["Subject"]
        if subject in existing:
            print(f"SKIP (exists): {subject}")
            skipped += 1
            continue

        payload = build_issue_payload(row, project_id)
        parent = row.get("Parent task", "")
        if parent and "parent_issue_id" not in payload:
            print(f"  NOTE: parent not resolved yet for '{subject}' -> '{parent}'")

        if args.dry_run:
            print(f"CREATE: {subject}")
            print(f"  tracker_id={payload.get('tracker_id')} parent={payload.get('parent_issue_id')}")
            _subject_to_id[subject] = -1  # simulate for child resolution in dry-run
            created += 1
            continue

        result = api_post(base, key, "/issues.json", {"issue": payload})
        new_id = result["issue"]["id"]
        _subject_to_id[subject] = new_id
        existing.add(subject)
        print(f"CREATED #{new_id}: {subject}")
        created += 1

    print(f"\nDone: {created} created, {skipped} skipped")


if __name__ == "__main__":
    main()
