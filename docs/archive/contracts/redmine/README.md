# Redmine — kontrakter, sprint og kode (P1 basis)

Redmine er EIRAs **operative kontrolpanel** for udvikling i fase 1.

**Fuld AI-orkestrering** lever i sideprojektet:  
[**adeo** — AI Development Orchestrator](../../../adeo/README.md)

(Legacy: [eira-pm-ai](../../../eira-pm-ai/README.md))

---

## Start her

**Fuld opsætningsguide:** [`REDMINE_SETUP.md`](REDMINE_SETUP.md)

Kort version:

1. Opret Redmine-projekt `eira-os` med trackers, sprint-versioner og custom fields
2. `python sync_contracts.py` — generér CSV fra prompts
3. `python import_to_redmine.py` — importér til Redmine
4. Tilslut Git-repo og brug `refs #issue` i commits

---

## Filer

| Fil | Formål |
|-----|--------|
| [`REDMINE_SETUP.md`](REDMINE_SETUP.md) | Komplet guide: projekt, sprint, workflow, Git |
| [`sprint_plan.yaml`](sprint_plan.yaml) | Sprint-tildeling og planlagte kontrakter |
| [`sync_contracts.py`](sync_contracts.py) | Generér `eira-p1-issues.csv` fra prompts |
| [`eira-p1-issues.csv`](eira-p1-issues.csv) | Issues klar til import |
| [`import_to_redmine.py`](import_to_redmine.py) | REST API-import med custom fields |
| [`coordinator.py`](coordinator.py) | API-koordinator: allokér, rapport, hold fremdrift |

---

## Hurtig import

```powershell
cd eira-os/contracts/redmine
pip install requests pyyaml

python sync_contracts.py
copy redmine.env.example redmine.env
# Udfyld REDMINE_URL, REDMINE_API_KEY og custom field IDs

python import_to_redmine.py --dry-run
python import_to_redmine.py
```

---

## Issue-struktur

```
[EIRA P1] Engineering kontrakter — oversigt     ← sprint epic
├── [EIRA] Onboarding
├── [EIRA-A] Endpoint Runtime — Programmer A
│   ├── CP-SESSION-001
│   ├── CP-IPC-001
│   └── ...
└── [EIRA-B] Fleet & Integration — Programmer B
    ├── CP-FLEET-001
    └── ...
```

---

## Vedligehold

Når ny CP-prompt oprettes:

1. Tilføj i `prompts/CP-XXX-001.prompt.md`
2. Opdatér `sprint_plan.yaml` hvis ny sprint
3. `python sync_contracts.py && python import_to_redmine.py`

*Relateret: [ONBOARDING_Programmoerer.md](../ONBOARDING_Programmoerer.md)*
