"""Shared Redmine REST API helpers for EIRA contract tooling."""

from __future__ import annotations

import os
from pathlib import Path

try:
    import requests
except ImportError as exc:
    raise SystemExit("pip install requests") from exc

ENV_PATH = Path(__file__).parent / "redmine.env"

_trackers: dict[str, int] = {}
_statuses: dict[str, int] = {}
_status_names: dict[int, str] = {}
_priorities: dict[str, int] = {}
_versions: dict[str, int] = {}
_version_names: dict[int, str] = {}
_users: dict[str, int] = {}
_user_names: dict[int, str] = {}
_custom_field_ids: dict[str, int] = {}
_custom_field_names: dict[int, str] = {}


def load_env_file(path: Path = ENV_PATH) -> None:
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
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
            _custom_field_names[int(raw)] = csv_col


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


def api_put(base: str, key: str, path: str, body: dict) -> dict:
    r = requests.put(
        f"{base.rstrip('/')}{path}",
        json=body,
        headers={"X-Redmine-API-Key": key, "Content-Type": "application/json"},
        timeout=30,
    )
    r.raise_for_status()
    return r.json() if r.content else {}


def resolve_id(mapping: dict[str, int], name: str) -> int | None:
    if not name:
        return None
    return mapping.get(name.strip().lower())


def load_metadata(base: str, key: str, project_id: str) -> int:
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
        _status_names[s["id"]] = s["name"]

    versions = api_get(base, key, f"/projects/{project_id}/versions.json", {"limit": 100})
    for v in versions.get("versions", []):
        _versions[v["name"].lower()] = v["id"]
        _version_names[v["id"]] = v["name"]

    users = api_get(base, key, "/users.json", {"limit": 100})
    for u in users.get("users", []):
        login = (u.get("login") or "").lower()
        if login:
            _users[login] = u["id"]
            _user_names[u["id"]] = login

    return project_numeric_id


def fetch_all_issues(base: str, key: str, project_id: str) -> list[dict]:
    issues: list[dict] = []
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
                "include": "custom_fields",
            },
        )
        batch = data.get("issues", [])
        if not batch:
            break
        issues.extend(batch)
        offset += len(batch)
        if offset >= data.get("total_count", 0):
            break
    return issues


def cf_value(issue: dict, field_name: str) -> str:
    field_id = _custom_field_ids.get(field_name)
    if not field_id:
        return ""
    for cf in issue.get("custom_fields", []):
        if cf.get("id") == field_id:
            return (cf.get("value") or "").strip()
    return ""


def status_name(issue: dict) -> str:
    return issue.get("status", {}).get("name", "?")


def is_closed(issue: dict) -> bool:
    return status_name(issue).lower() == "closed"


def version_name(issue: dict) -> str:
    fv = issue.get("fixed_version")
    return fv.get("name", "") if fv else ""


def assignee_login(issue: dict) -> str:
    a = issue.get("assigned_to")
    if not a:
        return ""
    return _user_names.get(a["id"], a.get("name", ""))


def connect() -> tuple[str, str, str]:
    load_env_file()
    load_custom_field_ids()
    base = env("REDMINE_URL")
    key = env("REDMINE_API_KEY")
    project = env("REDMINE_PROJECT", "eira-os")
    if not base or not key:
        raise SystemExit(
            "Set REDMINE_URL and REDMINE_API_KEY in redmine.env "
            "(copy redmine.env.example)"
        )
    return base, key, project
