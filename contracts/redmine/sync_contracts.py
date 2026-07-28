#!/usr/bin/env python3
"""
Generate eira-p1-issues.csv from CP-*.prompt.md + sprint_plan.yaml.

Usage:
  python sync_contracts.py              # write CSV
  python sync_contracts.py --dry-run    # print summary only
  python sync_contracts.py --check      # verify prompts vs sprint plan

Requires: pyyaml (pip install pyyaml)
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("pip install pyyaml", file=sys.stderr)
    sys.exit(1)

ROOT = Path(__file__).parent
PROMPTS_DIR = ROOT.parent / "prompts"
SPRINT_PLAN = ROOT / "sprint_plan.yaml"
CSV_PATH = ROOT / "eira-p1-issues.csv"
PROJECT = "eira-os"

OWNER_PARENT = {
    "programmer-a": "[EIRA-A] Endpoint Runtime — Programmer A",
    "programmer-b": "[EIRA-B] Fleet & Integration — Programmer B",
}

OWNER_LETTER = {
    "programmer-a": "A",
    "programmer-b": "B",
}

DEFAULT_SPRINT = "P1 — Kontrakt-freeze"


def parse_frontmatter(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    match = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
    if not match:
        return {}
    data = yaml.safe_load(match.group(1)) or {}
    return data if isinstance(data, dict) else {}


def parse_title(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    for line in text.splitlines():
        if line.startswith("# CP-"):
            # "# CP-SESSION-001 — Session isolation (database-backed)"
            parts = line.lstrip("# ").split(" — ", 1)
            if len(parts) == 2:
                return parts[1].strip()
    return path.stem


def depends_str(deps: list | str | None) -> str:
    if not deps:
        return ""
    if isinstance(deps, str):
        return deps
    return ", ".join(deps)


def contract_description(
    contract_id: str,
    prompt_path: str,
    prototype_ref: str,
    schema: str | None,
    depends_on: list | str | None,
    acceptance_hint: str = "",
) -> str:
    schema_line = schema or f"contracts/schemas/{contract_id.lower().replace('cp-', 'ipc-').rsplit('-', 1)[0]}-v1.json"
    deps = depends_str(depends_on)
    lines = [
        "h2. Kontrakt",
        "",
        f"* ID: *{contract_id}*",
        f"* Prompt: {{{{eira-os/{prompt_path}}}}}",
        f"* Kode: {{{{eira-os/{prototype_ref}}}}}",
    ]
    if deps:
        lines.append(f"* Depends on: {deps}")
    lines.extend(["", "h2. Acceptance", ""])
    if acceptance_hint:
        lines.append(acceptance_hint)
    else:
        lines.append(f"* Se prompt {{{{eira-os/{prompt_path}}}}} ACCEPTANCE-sektion")
    lines.extend(
        [
            "",
            "h2. Done",
            "",
            "* [ ] pytest contract tests grønne",
            "* [ ] INVARIANTS overholdt",
            "* [ ] OUT OF SCOPE respekteret",
            "* [ ] Schema opdateret (hvis relevant)",
            "* [ ] Prompt status: *frozen*",
        ]
    )
    return "\n".join(lines)


def epic_description() -> str:
    return """h2. Mål

Luk engineering-fasen med fryste kontrakter (CP-*) og grønne acceptance tests.

h2. Dokumentation

* Framework: {{eira-os/contracts/EIRA_Contract_Prompt_Framework_v0.1.md}}
* Onboarding: {{eira-os/contracts/ONBOARDING_Programmoerer.md}}
* Redmine: {{eira-os/contracts/redmine/REDMINE_SETUP.md}}
* Prompts: {{eira-os/contracts/prompts/}}

h2. Definition of Done (projekt)

* Alle P1 CP-* har status *frozen*
* JSON schemas matcher phase1 handlers
* {{pytest tests/contracts/}} grøn i CI
"""


def onboarding_description() -> str:
    return """h2. Opgave

Alle hovedprogrammører gennemfører onboarding (~30 min) og får reference runtime til at køre.

h2. Checklist

* [ ] Læst {{eira-os/contracts/EIRA_Contract_Prompt_Framework_v0.1.md}}
* [ ] Læst {{eira-os/contracts/prompts/README.md}}
* [ ] Læst {{eira-os/prototype/phase1/README.md}}
* [ ] {{uvicorn app.http_bridge:app --port 8765}} kører
* [ ] {{pytest tests/contracts/}} — mindst 3 passed

h2. Kommandoer (Windows)

<pre>
cd eira-os/prototype/phase1
.venv\\Scripts\\activate
uvicorn app.http_bridge:app --reload --port 8765
</pre>
"""


def owner_epic_description(letter: str, contracts: str, scope: str) -> str:
    return f"""h2. Ejer

Programmer {letter} — {scope}

h2. Konfliktregel

Delte filer koordineres via PR. Se REDMINE_SETUP.md.

h2. Kontrakter

{contracts}
"""


def row(
    *,
    tracker: str,
    subject: str,
    status: str = "New",
    priority: str = "Normal",
    assignee: str = "",
    parent: str = "",
    sprint: str = DEFAULT_SPRINT,
    hours: str = "",
    description: str = "",
    contract_id: str = "",
    owner: str = "",
    prompt_path: str = "",
    contract_status: str = "",
    depends_on: str = "",
) -> dict[str, str]:
    return {
        "Project": PROJECT,
        "Tracker": tracker,
        "Subject": subject,
        "Status": status,
        "Priority": priority,
        "Assignee": assignee,
        "Parent task": parent,
        "Target version": sprint,
        "Estimated hours": hours,
        "Contract ID": contract_id,
        "Owner": owner,
        "Prompt path": prompt_path,
        "Contract status": contract_status,
        "Depends on": depends_on,
        "Description": description,
    }


def build_rows(plan: dict) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []

    # Root epic
    rows.append(
        row(
            tracker="Feature",
            subject="[EIRA P1] Engineering kontrakter — oversigt",
            priority="High",
            sprint=DEFAULT_SPRINT,
            description=epic_description(),
        )
    )

    # Static epics from yaml
    for epic in plan.get("epics", []):
        subj = epic["subject"]
        if subj.startswith("[EIRA P1]"):
            continue
        desc = ""
        if "Onboarding" in subj:
            desc = onboarding_description()
        elif "[EIRA-A]" in subj:
            desc = owner_epic_description(
                "A",
                "CP-SESSION, CP-IPC, CP-INTENT, CP-IDENTITY, CP-GRAPH, CP-EXECUTOR",
                "daemons, IPC, session, intent, identity, graph, HTTP bridge",
            )
        elif "[EIRA-B]" in subj:
            desc = owner_epic_description(
                "B",
                "CP-FLEET, CP-GOVERNANCE-AGENT, CP-ADAPTER",
                "fleetd, eira-governance-agent, adapters, fleet-control alignment",
            )
        rows.append(
            row(
                tracker=epic.get("tracker", "Feature"),
                subject=subj,
                priority=epic.get("priority", "Normal"),
                assignee=epic.get("assignee", ""),
                parent=epic.get("parent", ""),
                sprint=epic.get("sprint", DEFAULT_SPRINT),
                hours=str(epic.get("hours", "")),
                description=desc,
            )
        )

    # Contracts from prompt files
    prompt_files = sorted(PROMPTS_DIR.glob("CP-*.prompt.md"))
    planned_ids = {p["contract_id"] for p in plan.get("planned", [])}

    for path in prompt_files:
        meta = parse_frontmatter(path)
        cid = meta.get("contract_id", path.stem.replace(".prompt", ""))
        if cid in planned_ids:
            continue  # planned section overrides until prompt exists

        owner_login = meta.get("owner", "programmer-a")
        title = parse_title(path)
        rel_prompt = f"contracts/prompts/{path.name}"
        proto = meta.get("prototype_ref", "").replace("\\", "/")
        if proto.startswith("../../"):
            proto = "prototype/phase1/" + proto.replace("../../prototype/phase1/", "")

        rows.append(
            row(
                tracker="Task",
                subject=f"{cid} — Verificer og freeze {title.lower()}",
                priority="High" if cid in ("CP-SESSION-001", "CP-IPC-001", "CP-INTENT-001", "CP-FLEET-001") else "Normal",
                assignee=owner_login,
                parent=OWNER_PARENT.get(owner_login, ""),
                sprint=DEFAULT_SPRINT,
                hours=_estimate_hours(cid),
                description=contract_description(
                    cid,
                    rel_prompt,
                    proto,
                    meta.get("schema"),
                    meta.get("depends_on"),
                ),
                contract_id=cid,
                owner=OWNER_LETTER.get(owner_login, ""),
                prompt_path=rel_prompt,
                contract_status=meta.get("status", "active"),
                depends_on=depends_str(meta.get("depends_on")),
            )
        )

    # Planned contracts without prompt file yet
    for item in plan.get("planned", []):
        cid = item["contract_id"]
        owner_login = item["owner"]
        suffix = item.get("subject_suffix", "implementer kontrakt")
        rel_prompt = item.get("prompt_path") or f"contracts/prompts/{cid}.prompt.md"
        rows.append(
            row(
                tracker="Task",
                subject=f"{cid} — {suffix}",
                priority=item.get("priority", "Normal"),
                assignee=owner_login,
                parent=item.get("parent", OWNER_PARENT.get(owner_login, "")),
                sprint=item.get("sprint", "P1 — Uge 2"),
                hours=str(item.get("hours", "")),
                description=contract_description(
                    cid,
                    rel_prompt,
                    item.get("prototype_ref", ""),
                    None,
                    item.get("depends_on"),
                    acceptance_hint="* Opret prompt først — se _TEMPLATE.prompt.md",
                ),
                contract_id=cid,
                owner=OWNER_LETTER.get(owner_login, ""),
                prompt_path=rel_prompt if item.get("prompt_path") else "",
                contract_status="draft",
                depends_on=depends_str(item.get("depends_on")),
            )
        )

    # Non-contract tasks
    for task in plan.get("tasks", []):
        owner_login = task.get("owner", "")
        rows.append(
            row(
                tracker="Task",
                subject=task["subject"],
                priority=task.get("priority", "Normal"),
                assignee=owner_login,
                parent=task.get("parent", ""),
                sprint=task.get("sprint", DEFAULT_SPRINT),
                hours=str(task.get("hours", "")),
                description=task.get("description", ""),
                owner=OWNER_LETTER.get(owner_login, ""),
            )
        )

    return rows


def _estimate_hours(contract_id: str) -> str:
    estimates = {
        "CP-SESSION-001": "4",
        "CP-IPC-001": "4",
        "CP-IDENTITY-001": "3",
        "CP-INTENT-001": "6",
        "CP-EXECUTOR-001": "4",
        "CP-FLEET-001": "6",
    }
    return estimates.get(contract_id, "4")


FIELDNAMES = [
    "Project",
    "Tracker",
    "Subject",
    "Status",
    "Priority",
    "Assignee",
    "Parent task",
    "Target version",
    "Estimated hours",
    "Contract ID",
    "Owner",
    "Prompt path",
    "Contract status",
    "Depends on",
    "Description",
]


def write_csv(rows: list[dict[str, str]], path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES, quoting=csv.QUOTE_MINIMAL)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync EIRA contracts to Redmine CSV")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--check", action="store_true", help="Verify prompt index vs files")
    parser.add_argument("--output", type=Path, default=CSV_PATH)
    args = parser.parse_args()

    plan = yaml.safe_load(SPRINT_PLAN.read_text(encoding="utf-8"))
    rows = build_rows(plan)

    contracts = [r for r in rows if r.get("Contract ID")]
    tasks = [r for r in rows if r["Tracker"] == "Task" and not r.get("Contract ID")]
    epics = [r for r in rows if r["Tracker"] == "Feature"]

    print(f"Epics: {len(epics)} | Contract tasks: {len(contracts)} | Other tasks: {len(tasks)}")
    for r in contracts:
        print(f"  {r['Contract ID']:30} sprint={r['Target version']:25} owner={r['Owner']}")

    if args.check:
        prompt_ids = {p.stem.replace(".prompt", "") for p in PROMPTS_DIR.glob("CP-*.prompt.md")}
        csv_ids = {r["Contract ID"] for r in contracts}
        missing_prompt = csv_ids - prompt_ids - {p["contract_id"] for p in plan.get("planned", [])}
        if missing_prompt:
            print(f"WARNING: CSV contracts without prompt file: {missing_prompt}")
        return

    if args.dry_run:
        return

    write_csv(rows, args.output)
    print(f"Wrote {len(rows)} rows → {args.output}")


if __name__ == "__main__":
    main()
