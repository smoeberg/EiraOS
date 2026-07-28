#!/usr/bin/env python3
"""
EIRA Redmine project coordinator — allocate tasks, sync prompts, track progress.

Requires redmine.env with API key (Manager role recommended).

Commands:
  report              Sprint progress + blocked/ready tasks
  next A|B            Next ready contract for programmer A or B
  allocate [--dry-run] Assign ready unassigned contract tasks
  assign ID LOGIN     Assign contract issue (e.g. CP-SESSION-001 programmer-a)
  start ID            Set issue In Progress
  push [--dry-run]    Sync prompts → Redmine (create/update issues)
  sync-prompts        Redmine Closed → prompt status: frozen in repo

Examples:
  python coordinator.py report
  python coordinator.py report --sprint "P1 — Kontrakt-freeze"
  python coordinator.py allocate --dry-run
  python coordinator.py assign CP-IPC-001 programmer-a
  python coordinator.py push
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

from redmine_api import (
    _custom_field_ids,
    _statuses,
    _users,
    _versions,
    api_post,
    api_put,
    assignee_login,
    cf_value,
    connect,
    fetch_all_issues,
    is_closed,
    load_metadata,
    resolve_id,
    status_name,
    version_name,
)

ROOT = Path(__file__).parent
PROMPTS_DIR = ROOT.parent / "prompts"
IMPORT_SCRIPT = ROOT / "import_to_redmine.py"
SYNC_SCRIPT = ROOT / "sync_contracts.py"

OWNER_LOGIN = {"A": "programmer-a", "B": "programmer-b", "programmer-a": "programmer-a", "programmer-b": "programmer-b"}


def parse_frontmatter(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    match = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
    if not match:
        return {}
    try:
        import yaml
    except ImportError:
        raise SystemExit("pip install pyyaml") from None
    data = yaml.safe_load(match.group(1)) or {}
    return data if isinstance(data, dict) else {}


def set_frontmatter_status(path: Path, status: str) -> bool:
    text = path.read_text(encoding="utf-8")
    if not re.search(r"^status:\s*", text, re.MULTILINE):
        return False
    new_text = re.sub(r"^status:\s*\S+\s*$", f"status: {status}", text, count=1, re.MULTILINE)
    if new_text != text:
        path.write_text(new_text, encoding="utf-8")
        return True
    return False


def contract_issues(issues: list[dict]) -> list[dict]:
    return [i for i in issues if cf_value(i, "Contract ID")]


def issue_by_contract(issues: list[dict], contract_id: str) -> dict | None:
    cid = contract_id.upper()
    for issue in issues:
        if cf_value(issue, "Contract ID").upper() == cid:
            return issue
    return None


def parse_depends(issue: dict) -> list[str]:
    raw = cf_value(issue, "Depends on")
    if not raw:
        return []
    return [p.strip().upper() for p in re.split(r"[,;]", raw) if p.strip()]


def closed_contracts(issues: list[dict]) -> set[str]:
    return {cf_value(i, "Contract ID").upper() for i in issues if cf_value(i, "Contract ID") and is_closed(i)}


def is_ready(issue: dict, closed: set[str]) -> bool:
    deps = parse_depends(issue)
    return all(dep in closed for dep in deps)


def sprint_filter(issue: dict, sprint: str | None) -> bool:
    if not sprint:
        return True
    return version_name(issue) == sprint


def cmd_report(base: str, key: str, project: str, sprint: str | None) -> int:
    load_metadata(base, key, project)
    issues = fetch_all_issues(base, key, project)
    contracts = [i for i in contract_issues(issues) if sprint_filter(i, sprint)]
    closed = closed_contracts(issues)

    by_status: dict[str, list[dict]] = {}
    for i in contracts:
        by_status.setdefault(status_name(i), []).append(i)

    print(f"# EIRA sprint report — {project}")
    if sprint:
        print(f"Sprint: {sprint}")
    print()

    total = len(contracts)
    done = len([i for i in contracts if is_closed(i)])
    print(f"Kontrakter: {done}/{total} closed ({100 * done // total if total else 0}%)")
    print()

    for status in ("New", "In Progress", "Resolved", "Closed"):
        items = by_status.get(status, [])
        if not items:
            continue
        print(f"## {status} ({len(items)})")
        for i in sorted(items, key=lambda x: cf_value(x, "Contract ID")):
            cid = cf_value(i, "Contract ID")
            assignee = assignee_login(i) or "-"
            deps = cf_value(i, "Depends on") or "-"
            blocked = "" if is_ready(i, closed) or is_closed(i) else " [BLOCKED]"
            print(f"  #{i['id']:4} {cid:28} → {assignee:14} deps={deps}{blocked}")
        print()

    print("## Klar til start (afhængigheder opfyldt, ikke closed)")
    ready = [
        i for i in contracts
        if not is_closed(i) and is_ready(i, closed) and status_name(i).lower() == "new"
    ]
    if not ready:
        print("  (ingen)")
    for i in ready:
        cid = cf_value(i, "Contract ID")
        owner = cf_value(i, "Owner")
        print(f"  #{i['id']} {cid} — owner {owner or '?'} — {i['subject']}")
    print()

    print("## Anbefalet næste (per programmør)")
    for letter, login in ("A", "programmer-a"), ("B", "programmer-b"):
        nxt = next_ready_for(contracts, closed, login, letter)
        if nxt:
            print(f"  Programmer {letter}: #{nxt['id']} {cf_value(nxt, 'Contract ID')} — {nxt['subject']}")
        else:
            print(f"  Programmer {letter}: (ingen klar opgave)")
    return 0


def next_ready_for(
    contracts: list[dict],
    closed: set[str],
    login: str,
    owner_letter: str,
) -> dict | None:
    candidates = [
        i for i in contracts
        if not is_closed(i)
        and is_ready(i, closed)
        and status_name(i).lower() in ("new", "in progress")
        and (cf_value(i, "Owner") == owner_letter or assignee_login(i) == login)
    ]
    priority_order = {"high": 0, "normal": 1, "low": 2}

    def sort_key(issue: dict) -> tuple:
        p = (issue.get("priority") or {}).get("name", "Normal").lower()
        return (priority_order.get(p, 9), issue["id"])

    candidates.sort(key=sort_key)
    return candidates[0] if candidates else None


def update_issue(base: str, key: str, issue_id: int, fields: dict, dry_run: bool) -> None:
    if dry_run:
        print(f"  DRY-RUN update #{issue_id}: {fields}")
        return
    api_put(base, key, f"/issues/{issue_id}.json", {"issue": fields})


def cmd_allocate(base: str, key: str, project: str, dry_run: bool) -> int:
    load_metadata(base, key, project)
    issues = fetch_all_issues(base, key, project)
    contracts = contract_issues(issues)
    closed = closed_contracts(issues)
    changed = 0

    for letter, login in ("A", "programmer-a"), ("B", "programmer-b"):
        # Skip if programmer already has In Progress contract
        active = [
            i for i in contracts
            if cf_value(i, "Owner") == letter and status_name(i).lower() == "in progress"
        ]
        if active:
            print(f"Programmer {letter}: already In Progress → #{active[0]['id']} {cf_value(active[0], 'Contract ID')}")
            continue

        nxt = next_ready_for(contracts, closed, login, letter)
        if not nxt:
            print(f"Programmer {letter}: no ready task")
            continue

        uid = _users.get(login)
        if not uid:
            print(f"WARNING: user {login} not found in Redmine", file=sys.stderr)
            continue

        if assignee_login(nxt) == login and status_name(nxt).lower() == "in progress":
            continue

        fields: dict = {"assigned_to_id": uid}
        if status_name(nxt).lower() == "new":
            sid = resolve_id(_statuses, "In Progress")
            if sid:
                fields["status_id"] = sid

        cid = cf_value(nxt, "Contract ID")
        print(f"ALLOCATE {cid} → {login} (#{nxt['id']})")
        update_issue(base, key, nxt["id"], fields, dry_run)
        changed += 1

    print(f"\nAllocated: {changed}")
    return 0


def cmd_assign(base: str, key: str, project: str, contract_id: str, login: str, dry_run: bool) -> int:
    load_metadata(base, key, project)
    issues = fetch_all_issues(base, key, project)
    issue = issue_by_contract(issues, contract_id)
    if not issue:
        raise SystemExit(f"Contract not found in Redmine: {contract_id}")

    uid = _users.get(login.lower())
    if not uid:
        raise SystemExit(f"User not found: {login}")

    print(f"Assign #{issue['id']} {contract_id} → {login}")
    update_issue(base, key, issue["id"], {"assigned_to_id": uid}, dry_run)
    return 0


def cmd_start(base: str, key: str, project: str, contract_id: str, dry_run: bool) -> int:
    load_metadata(base, key, project)
    issues = fetch_all_issues(base, key, project)
    issue = issue_by_contract(issues, contract_id)
    if not issue:
        raise SystemExit(f"Contract not found: {contract_id}")

    closed = closed_contracts(issues)
    if not is_ready(issue, closed):
        deps = parse_depends(issue)
        missing = [d for d in deps if d not in closed]
        raise SystemExit(f"Blocked — waiting on: {', '.join(missing)}")

    sid = resolve_id(_statuses, "In Progress")
    if not sid:
        raise SystemExit("Status 'In Progress' not found")

    print(f"Start #{issue['id']} {contract_id}")
    update_issue(base, key, issue["id"], {"status_id": sid}, dry_run)
    return 0


def cmd_next(base: str, key: str, project: str, who: str) -> int:
    load_metadata(base, key, project)
    issues = fetch_all_issues(base, key, project)
    contracts = contract_issues(issues)
    closed = closed_contracts(issues)

    letter = who.upper()
    login = OWNER_LOGIN.get(who, who)
    nxt = next_ready_for(contracts, closed, login, letter)
    if not nxt:
        print(f"No ready task for programmer {letter}")
        return 1

    cid = cf_value(nxt, "Contract ID")
    path = cf_value(nxt, "Prompt path")
    print(f"#{nxt['id']} {cid}")
    print(f"Subject: {nxt['subject']}")
    print(f"Status: {status_name(nxt)}")
    print(f"Prompt path: {path or '(opret prompt først)'}")
    prompt_file = PROMPTS_DIR / f"{cid}.prompt.md"
    if prompt_file.is_file():
        print(f"Prompt file: {prompt_file}")
    return 0


def cmd_push(dry_run: bool) -> int:
    print("1. sync_contracts.py …")
    if not dry_run:
        subprocess.run([sys.executable, str(SYNC_SCRIPT)], check=True)
    else:
        subprocess.run([sys.executable, str(SYNC_SCRIPT), "--dry-run"], check=True)

    print("2. import_to_redmine.py …")
    args = [sys.executable, str(IMPORT_SCRIPT)]
    if dry_run:
        args.append("--dry-run")
    subprocess.run(args, check=True)
    return 0


def cmd_sync_prompts(base: str, key: str, project: str, dry_run: bool) -> int:
    """Set prompt status: frozen when Redmine issue is Closed."""
    load_metadata(base, key, project)
    issues = fetch_all_issues(base, key, project)
    updated = 0

    for issue in contract_issues(issues):
        if not is_closed(issue):
            continue
        cid = cf_value(issue, "Contract ID")
        prompt_file = PROMPTS_DIR / f"{cid}.prompt.md"
        if not prompt_file.is_file():
            print(f"SKIP {cid}: no prompt file")
            continue
        meta = parse_frontmatter(prompt_file)
        if meta.get("status") == "frozen":
            continue
        print(f"FREEZE prompt {cid} (Redmine #{issue['id']} closed)")
        if not dry_run:
            set_frontmatter_status(prompt_file, "frozen")
            # Update Redmine custom field too
            if _custom_field_ids.get("Contract status"):
                api_put(
                    base,
                    key,
                    f"/issues/{issue['id']}.json",
                    {
                        "issue": {
                            "custom_fields": [
                                {
                                    "id": _custom_field_ids["Contract status"],
                                    "value": "frozen",
                                }
                            ]
                        }
                    },
                )
        updated += 1

    print(f"\nPrompts frozen: {updated}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="EIRA Redmine project coordinator")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--sprint", default="", help='Filter sprint, e.g. "P1 — Kontrakt-freeze"')
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("report", help="Sprint progress report")
    sub.add_parser("allocate", help="Auto-assign ready tasks to A/B")
    p_assign = sub.add_parser("assign", help="Assign contract to programmer")
    p_assign.add_argument("contract_id")
    p_assign.add_argument("login", choices=["programmer-a", "programmer-b", "a", "b"])
    p_start = sub.add_parser("start", help="Set contract In Progress")
    p_start.add_argument("contract_id")
    p_next = sub.add_parser("next", help="Next ready task for A or B")
    p_next.add_argument("who", choices=["A", "B", "a", "b", "programmer-a", "programmer-b"])
    sub.add_parser("push", help="Sync prompts → CSV → Redmine")
    sub.add_parser("sync-prompts", help="Redmine Closed → prompt frozen")

    args = parser.parse_args()
    base, key, project = connect()
    sprint = args.sprint or None

    if args.command == "report":
        sys.exit(cmd_report(base, key, project, sprint))
    if args.command == "allocate":
        sys.exit(cmd_allocate(base, key, project, args.dry_run))
    if args.command == "assign":
        login = OWNER_LOGIN.get(args.login, args.login)
        sys.exit(cmd_assign(base, key, project, args.contract_id, login, args.dry_run))
    if args.command == "start":
        sys.exit(cmd_start(base, key, project, args.contract_id, args.dry_run))
    if args.command == "next":
        sys.exit(cmd_next(base, key, project, args.who))
    if args.command == "push":
        sys.exit(cmd_push(args.dry_run))
    if args.command == "sync-prompts":
        sys.exit(cmd_sync_prompts(base, key, project, args.dry_run))


if __name__ == "__main__":
    main()
