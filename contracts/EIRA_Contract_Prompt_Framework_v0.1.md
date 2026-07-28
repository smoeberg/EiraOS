# EIRA — Contract-as-Prompt Framework v0.1

**Status:** Normativ for al AI-assisteret udvikling  
**Dato:** 4. juli 2026  
**Målgruppe:** To hovedprogrammører + AI-agenter (Cursor, Claude, etc.)

---

## Beslutning

EIRA udvikles **AI-first** med to menneskelige ejere. Kontrakter skal kunne:

1. **Valideres maskinelt** — JSON Schema, pytest, JSON-RPC fejlkoder  
2. **Instruere AI direkte** — copy-paste prompt uden at læse 40 visiondocs  
3. **Dele ansvar** — hver kontrakt har én ejer (Programmer A eller B)  
4. **Fryse scope** — prompten siger eksplicit hvad der **ikke** må bygges

> Vision er lukket. AI bygger **kontrakter** — ikke nye arkitektur-narrativer.

---

## To lag — altid sammen

| Lag | Filtype | Formål | Hvem læser |
|-----|---------|--------|------------|
| **Maskin** | `schemas/*.json`, `events-v1.yaml` | Validering, CI, codegen | CI, linter, test |
| **Agent** | `prompts/CP-*.prompt.md` | Implementeringsinstruktion | AI-bot + menneske |

**Regel:** Ingen kode merges uden at begge lag findes. Schema først → prompt → kode → acceptance tests.

---

## Prompt-filformat (`CP-*.prompt.md`)

Hver kontrakt-prompt har:

```yaml
---
contract_id: CP-INTENT-001
version: 1.0.0
owner: programmer-a          # eller programmer-b
status: active               # draft | active | frozen
schema: ../schemas/ipc-intent-v1.json
prototype_ref: ../../prototype/phase1/app/daemons/intent_engine.py
depends_on: [CP-SESSION-001]
forbidden:                   # AI må ALDRIG
  - global session state
  - in-memory pending intents
---
```

Derefter fire obligatoriske sektioner:

| Sektion | Indhold |
|---------|---------|
| **AGENT PROMPT** | Copy-paste blok til AI — selvforsynende |
| **INVARIANTS** | Ufravigelige regler (nummererede) |
| **OUT OF SCOPE** | Eksplicit liste — stopper scope creep |
| **ACCEPTANCE** | Given/When/Then — bliver pytest |

---

## Workflow for hovedprogrammør + AI

```
1. Vælg kontrakt (CP-xxx) fra prompts/README.md
2. Læs schema + INVARIANTS (2 min)
3. Paste AGENT PROMPT i Cursor Agent / ny chat
4. AI implementerer KUN inden for OUT OF SCOPE-grænser
5. Kør acceptance tests (pytest tests/contracts/)
6. Programmer godkender → status: frozen
7. Næste kontrakt (respektér depends_on)
```

### Split mellem to programmører

| Rolle | Ejer | Kontrakter |
|-------|------|------------|
| **Programmer A** — Endpoint Runtime | `eira-os` daemons, IPC, session, intent, identity, graph, HTTP bridge, Explorer UI API | CP-SESSION, CP-IPC, CP-INTENT, CP-IDENTITY, CP-GRAPH, CP-EXECUTOR |
| **Programmer B** — Fleet & Integration | `fleetd`, `eira-governance-agent`, adapters, alignment med `eira-fleet-control` | CP-FLEET, CP-GOVERNANCE-AGENT, CP-ADAPTER |

**Konfliktregel:** Delte filer (`database.py`, `ipc/client.py`) — Programmer A ejer; B åbner PR med schema-diff først.

---

## Sådan bruger du prompten i Cursor

### Metode 1 — Agent chat (anbefalet)

1. Åbn `prompts/CP-INTENT-001.prompt.md`
2. Kopiér alt under `## AGENT PROMPT` til `--- END PROMPT ---`
3. Tilføj: *"Implementer i `eira-os/prototype/phase1`. Match eksisterende stil. Kør ikke vision-ændringer."*
4. Ved PR: brug `review-bugbot` skill mod acceptance-kriterier

### Metode 2 — Cursor Rule (vedvarende)

Opret `.cursor/rules/eira-contracts.mdc` med:

```markdown
When editing eira-os/prototype/phase1:
- Read contracts/prompts/ for active CP-* contracts
- Never introduce global session or presentation_mode
- session_id required on all user-scoped IPC calls
- Match JSON schemas in contracts/schemas/
```

### Metode 3 — Acceptance som skill

Konverter `ACCEPTANCE`-sektionen til pytest i `tests/contracts/test_cp_intent_001.py` — AI kan regenerere test fra prompt ved schema-ændring.

---

## Navngivning

| Præfiks | Betydning | Eksempel |
|---------|-----------|----------|
| `CP-` | Contract Prompt | `CP-FLEET-001.prompt.md` |
| `ipc-*-v1.json` | JSON-RPC schema | `ipc-intent-v1.json` |
| `EVT-` | Event i catalog | `EVT-intent.executed` |

Versions bump: **MINOR** = nyt felt (bagudkompatibelt), **MAJOR** = breaking IPC.

---

## Kvalitetskriterier for en god prompt

- [ ] AI kan implementere uden at læse Situation UI Vision  
- [ ] Filstier er absolutte eller repo-relative — ingen "et sted i koden"  
- [ ] Fejlkoder er listet med nummer og `data`-payload  
- [ ] OUT OF SCOPE har mindst 3 punkter  
- [ ] ACCEPTANCE har mindst 3 scenarier inkl. negativ test  
- [ ] `depends_on` er komplet — ingen skjulte rækkefølgekrav  

---

## Relation til andre dokumenter

| Dokument | Rolle efter framework |
|----------|----------------------|
| Vision / Situation UI | **Læses ikke af AI under implementering** |
| Scope Closure Engineering | Input til hvilke CP-* der oprettes |
| phase1 reference kode | Autoritativ indtil Rust — prompts matcher den |
| Fleet Agent Protocol | Input til CP-FLEET — ikke copy-paste til intent |

---

## Næste leverancer

1. `schemas/ipc-intent-v1.json` — genereres fra phase1 handlers  
2. `tests/contracts/` — pytest fra ACCEPTANCE-blokke  
3. `CP-GRAPH-001`, `CP-EXECUTOR-001`, `CP-GOVERNANCE-AGENT-001`  
4. CI: `jsonschema validate` + contract tests på PR  

---

*Companion: [prompts/README.md](prompts/README.md) · [Scope Closure](../docs/specs/EIRA_Scope_Closure_Engineering_v0.1.md)*
