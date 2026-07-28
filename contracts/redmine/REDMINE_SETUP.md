# Redmine — styring af kontrakter, sprint og kode

**Formål:** Redmine er jeres **operativt kontrolpanel** for EIRA-udvikling. Hver CP-kontrakt er et issue. Sprint = version/milestone. Kode kobles via Git commits og PR.

**Målgruppe:** Projektleder / hovedprogrammør der opsætter Redmine + de to programmører der arbejder dagligt i det.

---

## Overblik

```
┌─────────────────────────────────────────────────────────────┐
│  Redmine (eira-os projekt)                                  │
│  ├── Sprint: P1 — Kontrakt-freeze  (uge 1)                  │
│  ├── Sprint: P1 — Uge 2          (uge 2)                    │
│  ├── Epics: [EIRA-A] / [EIRA-B]                             │
│  └── Tasks: CP-SESSION-001, CP-IPC-001, …                  │
└─────────────────────────────────────────────────────────────┘
         ▲                              │
         │ sync_contracts.py            │ refs #issue
         │ (fra prompts/*.prompt.md)    ▼
┌─────────────────┐              ┌─────────────────┐
│ contracts/      │              │ Git repo        │
│ prompts/CP-*.md │◄─────────────│ phase1/ kode    │
└─────────────────┘   PR/merge   └─────────────────┘
```

| Redmine begreb | EIRA begreb |
|----------------|-------------|
| **Version** (milestone) | Sprint |
| **Feature** tracker | Epic (A-spor / B-spor) |
| **Task** tracker | CP-kontrakt eller leverance |
| **Status Closed** | Prompt `status: frozen` |
| **Custom field Contract ID** | `CP-SESSION-001` |
| **Repository commit** | `refs #42` kobler kode til issue |

---

## Trin 1 — Opret projekt (admin, 15 min)

### Projekt

| Felt | Værdi |
|------|-------|
| Navn | EIRA OS |
| Identifier | `eira-os` |
| Beskrivelse | Contract-as-Prompt engineering — phase1 |

Aktivér moduler: **Issue tracking**, **Time tracking**, **Repository**, **Calendar** (valgfrit).

### Trackers

| Tracker | Brug |
|---------|------|
| **Feature** | Epics og sprint-oversigt |
| **Task** | CP-kontrakter, schemas, CI |
| **Bug** | Fejl fundet under kontrakt-arbejde (valgfrit) |

### Versioner (= sprint)

Opret under **Project → Settings → Versions**:

| Navn | Due date | Beskrivelse |
|------|----------|-------------|
| `P1 — Kontrakt-freeze` | Uge 1 slut | Verificér og fryse eksisterende CP-* |
| `P1 — Uge 2` | Uge 2 slut | Nye kontrakter: GRAPH, GOVERNANCE, ADAPTER, CI |

### Brugere og roller

| Login | Rolle | Redmine-rolle |
|-------|-------|---------------|
| `programmer-a` | Endpoint Runtime | Developer |
| `programmer-b` | Fleet & Integration | Developer |
| (dig) | Projektleder | Manager |

**Developer** kan: oprette/redigere issues, logge tid, committe til repo, ændre status New → In Progress → Resolved.

**Manager** kan: lukke issues (Closed), ændre sprint, tildele opgaver.

### Custom fields (obligatorisk for kontraktstyring)

**Administration → Custom fields → Issues → New custom field:**

| Navn | Format | Mulige værdier | Issues |
|------|--------|----------------|--------|
| `Contract ID` | Text | f.eks. `CP-SESSION-001` | Task |
| `Owner` | List | `A`, `B` | Task |
| `Prompt path` | Text | `contracts/prompts/CP-….md` | Task |
| `Contract status` | List | `draft`, `active`, `frozen` | Task |
| `Depends on` | Text | kommasepareret CP-id'er | Task |

Notér **felt-ID'erne** efter oprettelse (står i URL ved redigering, f.eks. `custom_fields/5/edit` → id `5`). Brug dem i `redmine.env` (se nedenfor).

### Issue statuses (workflow)

Standard Redmine-statuser er nok. Brug denne mapping:

| Status | Hvem sætter | Betyder |
|--------|-------------|---------|
| **New** | Import / ledelse | Kontrakt ikke startet |
| **In Progress** | Programmør | Arbejder med AI/kode |
| **Resolved** | Programmør | Acceptance grøn — afventer review |
| **Closed** | Ledelse | Godkendt — prompt `frozen` |
| **Rejected** | Ledelse | Acceptance fejler — tilbage til In Progress |

---

## Trin 2 — Importér issues (30 min)

### A. Sync kontrakter fra repo

```powershell
cd eira-os/contracts/redmine
python sync_contracts.py
```

Dette opdaterer `eira-p1-issues.csv` fra `prompts/CP-*.prompt.md` frontmatter + `sprint_plan.yaml`.

### B. Import til Redmine

**Valg 1 — API (anbefalet):**

```powershell
# Kopiér og udfyld:
copy redmine.env.example redmine.env

pip install requests

python import_to_redmine.py --dry-run
python import_to_redmine.py
```

**Valg 2 — CSV-import i Redmine UI:**

Upload `eira-p1-issues.csv` via **Project → Issues → Import**.

---

## Trin 3 — Git repository (kodekobling)

### Tilslut repo

**Project → Settings → Repositories → Git**

| Felt | Værdi |
|------|-------|
| SCM | Git |
| Main repository | Ja |
| Path eller URL | Sti til `eira-os` eller clone-URL |

### Commit-konvention

Programmører **skal** referere issue i commits:

```
CP-SESSION-001: verify session isolation tests

refs #12
```

| Nøgleord | Effekt |
|----------|--------|
| `refs #12` | Linker commit til issue #12 |
| `fixes #12` | Linker + kan lukke issue (brug kun ved godkendt merge) |

### Branch-navngivning

```
cp/CP-SESSION-001-verify
cp/CP-INTENT-001-pending-intents
```

Én branch per kontrakt-issue. PR titel: `[CP-SESSION-001] Verify session isolation`.

---

## Trin 4 — Sprint-overblik (gratis — ingen plugin påkrævet)

EIRA-sprint styres med **Redmines indbyggede funktioner**. I behøver **ikke** betale for [redmine-kanban.com](https://redmine-kanban.com/en/plugins/kanban) eller RedmineUP Agile.

### Anbefalet: native Redmine (0 kr.)

| Behov | Hvor i Redmine |
|-------|----------------|
| Aktiv sprint | **Project → Roadmap** eller filter **Target version** = `P1 — Kontrakt-freeze` |
| Mine opgaver | **Issues** → filter Assignee = mig + Target version |
| A/B-spor | Filter **Parent task** = `[EIRA-A]…` eller `[EIRA-B]…` |
| Afhængigheder | Custom field **Depends on** + tjek parent-issue er Closed |
| Status-flow | New → In Progress → Resolved → Closed |

**Gem filter som forespørgsel** (f.eks. "Sprint P1 — Programmer A") så programmører kan åbne den med ét klik.

### Valgfrit: gratis Kanban-plugin

Hvis I vil have drag-and-drop board uden licensomkostninger:

| Plugin | Licens | Repo | Bemærkning |
|--------|--------|------|------------|
| **[kanban](https://github.com/happy-se-life/kanban)** | MIT (gratis) | `happy-se-life/kanban` | Mest brugte gratis valg; WIP-limits, filtre |
| **[redmine_kanban](https://github.com/tiohsa/redmine_kanban)** | GPL-2.0 (gratis) | `tiohsa/redmine_kanban` | Nyere; React-baseret |

Installation (eksempel med happy-se-life):

```bash
cd /path/to/redmine/plugins
git clone https://github.com/happy-se-life/kanban.git
# Rediger lib/kanban/constants.rb efter README
# Genstart Redmine
# Project → Settings → Modules → aktivér Kanban
```

Board-opsætning for EIRA:

1. Kolonner = statuses: New | In Progress | Resolved | Closed
2. Filter: Target version = aktiv sprint
3. Gruppér efter parent epic (`[EIRA-A]` / `[EIRA-B]`)

### Betalte plugins (ikke nødvendige)

| Plugin | Pris | Kommentar |
|--------|------|-----------|
| [redmine-kanban.com](https://redmine-kanban.com/en/plugins/kanban) | Kommerciel licens | Godt produkt — men **ikke** et krav for EIRA |
| [RedmineUP Agile](https://www.redmineup.com/pages/plugins/agile) | Kommerciel | Scrum/Kanban + charts — overkill til 2 programmører i P1 |

**Konklusion:** Start med native Redmine + gemte filtre. Tilføj kun et gratis Kanban-plugin hvis teamet savner visuelt board.

---

## Daglig workflow — programmør

```
1. Åbn Redmine → filter sprint + din assignee
2. Vælg næste Task (tjek Depends on — parent skal være Closed)
3. Sæt status → In Progress
4. Åbn Prompt path fra custom field → kopiér AGENT PROMPT til Cursor
5. Implementer i phase1 på branch cp/CP-XXX-001-...
6. Kør: pytest tests/contracts/
7. Commit med refs #<issue-id>
8. PR → review → merge
9. Sæt issue → Resolved
10. Ledelse reviewer → Closed + opdater prompt status: frozen
```

### Definition of Done (checkliste på issue)

Hver CP-task i CSV har indbygget checkliste. I Redmine kan I tilføje **Checklists plugin** for interaktiv afkrydsning:

- [ ] Kode matcher `prototype_ref`
- [ ] INVARIANTS overholdt
- [ ] OUT OF SCOPE respekteret
- [ ] `pytest tests/contracts/` grøn
- [ ] JSON schema opdateret (hvis relevant)
- [ ] Prompt `status: frozen`
- [ ] Issue status: Closed

---

## Sprint-plan (P1)

### Sprint: P1 — Kontrakt-freeze

| Issue | Owner | Est. timer |
|-------|-------|------------|
| Onboarding | begge | 2 |
| CP-SESSION-001 | A | 4 |
| CP-IPC-001 | A | 4 |
| CP-IDENTITY-001 | A | 3 |
| CP-INTENT-001 | A | 6 |
| CP-EXECUTOR-001 | A | 4 |
| CP-FLEET-001 | B | 6 |
| Schema ipc-intent-v1.json | A | 3 |
| Schema ipc-fleet-v1.json | B | 3 |

**Sprint-mål:** Alle ovenstående Closed. Alle prompts `frozen`.

### Sprint: P1 — Uge 2

| Issue | Owner | Est. timer |
|-------|-------|------------|
| CP-GRAPH-001 | A | 8 |
| CP-GOVERNANCE-AGENT-001 | B | 16 |
| CP-ADAPTER-001 | B | 12 |
| EVENTS-001 | A | 4 |
| CI — contract tests | A | 6 |

**Sprint-mål:** Nye prompts oprettet og frozen. CI blokerer røde PRs.

---

## Ny kontrakt — proces

1. Opret `prompts/CP-XXX-001.prompt.md` fra `_TEMPLATE.prompt.md`
2. Tilføj entry i `sprint_plan.yaml`
3. Kør `python sync_contracts.py`
4. Kør `python import_to_redmine.py` (opretter nyt issue)
5. Tildel til programmør A eller B
6. Programmør følger daglig workflow

---

## Projektkoordinator via API (`coordinator.py`)

**Kort svar:** Denne chat kan **ikke** direkte styre jeres Redmine uden `redmine.env` og netværk til jeres server. Men med API-nøgle kan **`coordinator.py`** fungere som automatisk projektkoordinator — og du kan bede mig køre den i Cursor, når `redmine.env` er sat op.

### Hvad koordinatoren kan

| Kommando | Hvad den gør |
|----------|--------------|
| `report` | Sprint-fremdrift, blokerede opgaver, anbefalet næste per A/B |
| `allocate` | Tildel klar opgave til programmør (respekterer `depends_on`) |
| `assign CP-XXX programmer-a` | Manuel tildeling |
| `start CP-XXX` | Sæt In Progress (blokerer hvis afhængighed mangler) |
| `next A` / `next B` | Vis næste klar kontrakt + prompt-sti |
| `push` | Sync prompts → CSV → Redmine (opret/opdatér issues) |
| `sync-prompts` | Redmine Closed → sæt `status: frozen` i prompt-fil |

### Opsætning (én gang)

1. Opret API-nøgle i Redmine: **Min konto → API access key**
2. Brug en konto med **Manager**-rolle (kan tildele og ændre status)
3. Kopiér `redmine.env.example` → `redmine.env` og udfyld

### Daglig koordinator-rutine

```powershell
cd eira-os/contracts/redmine

# Morgen: status + auto-allokering
python coordinator.py report --sprint "P1 — Kontrakt-freeze"
python coordinator.py allocate

# Efter merge / godkendelse
python coordinator.py sync-prompts

# Ny kontrakt-prompt oprettet i repo
python coordinator.py push
```

### Allokeringslogik

```
1. Hvis programmør allerede har In Progress → spring over
2. Find kontrakter hvor alle depends_on er Closed
3. Prioritér High før Normal
4. Tildel til Owner (A/B) og sæt In Progress
```

### Arbejd med mig (Cursor) som koordinator

Når `redmine.env` findes, kan du skrive:

> "Kør coordinator report og allokér opgaver"

Så kører jeg scriptet og fortæller dig hvem der skal arbejde på hvad. Jeg **opretter/redigerer prompts** i repo; `push` synkroniserer dem til Redmine.

**Grænser:**
- Jeg kan ikke se Redmine uden at scriptet kører (ingen live forbindelse fra chatten)
- Programmører implementerer stadig kode — koordinatoren styrer issues og prompts, ikke selve koden
- `allocate` ændrer kun Redmine — ikke git branches

---

## redmine.env — custom field mapping

Efter custom fields er oprettet i Redmine, udfyld `redmine.env`:

```env
REDMINE_URL=https://redmine.jeresdomæne.dk
REDMINE_API_KEY=din-api-nøgle
REDMINE_PROJECT=eira-os

# Custom field IDs (fra Administration → Custom fields)
REDMINE_CF_CONTRACT_ID=5
REDMINE_CF_OWNER=6
REDMINE_CF_PROMPT_PATH=7
REDMINE_CF_CONTRACT_STATUS=8
REDMINE_CF_DEPENDS_ON=9
```

---

## Fejlsøgning

| Problem | Løsning |
|---------|---------|
| Kan ikke starte CP-INTENT (afhængighed) | Tjek parent CP-SESSION og CP-IPC er Closed |
| Custom fields tomme efter import | Udfyld `redmine.env` med felt-ID'er |
| Commit vises ikke på issue | Tjek `refs #id` syntaks og repo sync |
| Programmør ser ikke sprint | Filter Target version + Assignee = mig |

---

## Filer i denne mappe

| Fil | Formål |
|-----|--------|
| [`REDMINE_SETUP.md`](REDMINE_SETUP.md) | Denne guide |
| [`sprint_plan.yaml`](sprint_plan.yaml) | Sprint-tildeling for kontrakter |
| [`sync_contracts.py`](sync_contracts.py) | Generér CSV fra prompts |
| [`eira-p1-issues.csv`](eira-p1-issues.csv) | Issues til import |
| [`import_to_redmine.py`](import_to_redmine.py) | API-import med custom fields |
| [`coordinator.py`](coordinator.py) | Projektkoordinator via API |
| [`redmine_api.py`](redmine_api.py) | Delt Redmine API-klient |
| [`redmine.env.example`](redmine.env.example) | Konfigurationsskabelon |

*Relateret: [ONBOARDING_Programmoerer.md](../ONBOARDING_Programmoerer.md) · [EIRA_Contract_Prompt_Framework_v0.1.md](../EIRA_Contract_Prompt_Framework_v0.1.md)*
