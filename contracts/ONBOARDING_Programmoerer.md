# Velkommen til EIRA — onboarding for hovedprogrammører

**Dato:** 4. juli 2026  
**Formål:** Klar besked I kan dele internt (Slack / mail / møde)  
**Repo:** `eira-os/` under `Businessplans/Eira`

---

## Kopiér-klar besked (send til teamet)

---

**Emne: EIRA udvikling — AI-first med kontrakter som prompts**

Hej,

Vi går nu fra kreativ fase til **engineering**. Vision og arkitektur-narrativer er lukket. Fremover bygger vi **kontrakter** — ikke nye beskrivelser af hvad EIRA *kunne* blive.

Udviklingen er **AI-first**: I to hovedprogrammører ejer domæner, styrer AI-agenter (Cursor), og godkender leverancer mod acceptance tests.

### North star (uændret)

> *Ubuntu remains the operating system. EIRA evolves the enterprise runtime.*

### Hvad I skal læse først (30 min)

1. [`contracts/EIRA_Contract_Prompt_Framework_v0.1.md`](EIRA_Contract_Prompt_Framework_v0.1.md) — metoden
2. [`contracts/prompts/README.md`](prompts/README.md) — hvilke kontrakter findes
3. [`prototype/phase1/README.md`](../prototype/phase1/README.md) — kør reference runtime
4. [`docs/specs/EIRA_Scope_Closure_Engineering_v0.1.md`](../docs/specs/EIRA_Scope_Closure_Engineering_v0.1.md) — hvad der er lukket vs. åbent

**Læs ikke** Situation UI Vision, Cognitive Runtime m.m. medmindre en kontrakt-prompt henviser eksplicit.

### Rollefordeling

| | **Programmer A — Endpoint Runtime** | **Programmer B — Fleet & Integration** |
|---|-------------------------------------|----------------------------------------|
| **Ejer** | `eira-os/prototype/phase1` daemons, IPC, session, intent, identity, graph, HTTP bridge, Explorer API | `fleetd`, `eira-governance-agent`, adapters, alignment med `eira-fleet-control` |
| **Kontrakter** | CP-SESSION, CP-IPC, CP-INTENT, CP-IDENTITY, CP-GRAPH, CP-EXECUTOR | CP-FLEET, CP-GOVERNANCE-AGENT, CP-ADAPTER |
| **Første opgave** | CP-GRAPH-001 + `schemas/ipc-intent-v1.json` | CP-GOVERNANCE-AGENT-001 (heartbeat client) |

**Konfliktregel:** Delte filer (`database.py`, `ipc/client.py`) ejes af **A**. B ændrer dem kun via PR med schema-diff og As godkendelse.

### Sådan arbejder I med AI (hver opgave)

```
1. Vælg kontrakt (CP-xxx) fra prompts/README.md
2. Læs INVARIANTS + OUT OF SCOPE (2 min)
3. Kopiér AGENT PROMPT-blokken → paste i Cursor Agent
4. Tilføj: "Implementer i phase1. Respekter OUT OF SCOPE. Match eksisterende stil."
5. Kør: pytest tests/contracts/
6. Godkend → sæt status: frozen i prompt frontmatter
```

Cursor har en vedvarende regel: `.cursor/rules/eira-contracts.mdc` (aktiveres automatisk i `phase1/`).

### Reference runtime — kom i gang

```powershell
cd eira-os/prototype/phase1
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
# Én gang efter opgradering:
Remove-Item data/eira.db -ErrorAction SilentlyContinue
uvicorn app.http_bridge:app --reload --port 8765
```

UI (valgfrit): `cd ui && npm install && npm run dev`

Daemons: intent (18766), identity (18767), graph (18768), fleet (18769). Bridge starter dem automatisk.

Valgfri IPC-auth: `$env:EIRA_IPC_TOKEN = "dev-secret"`

### Hvad der allerede virker (P0 — ikke genopfind)

- Session isolation per `session_id` (ingen global state)
- Pending intents i SQLite (overlever genstart)
- `intent.confirm` → executor + audit
- Adapter offline blokerer plan/execute
- `fleetd` enroll + heartbeat
- Fejlkatalog: [`contracts/errors-v1.md`](errors-v1.md)

### Hvad I ikke skal bygge (endnu)

- Entra OIDC login (hardcoded demo-session OK)
- Fuld Fleet cloud API i phase1
- Btrfs/ZFS snapshots (kun `snapshot_required` flag)
- Situation UI / Intent Canvas
- Nye vision- eller arkitekturdocs

### Definition of Done (én kontrakt)

- [ ] Kode matcher `prototype_ref` i prompten
- [ ] INVARIANTS overholdt (ingen global session)
- [ ] OUT OF SCOPE respekteret
- [ ] Acceptance tests grønne i `tests/contracts/`
- [ ] JSON schema opdateret (når relevant)
- [ ] Prompt `status: frozen`

### Kommunikation

- **Spørgsmål om scope** → Scope Closure doc eller spørg — ikke improvisér i AI-chat
- **Ny fejlkode** → opdater `errors-v1.md` + relevant CP-prompt før merge
- **Breaking IPC** → MAJOR version bump på kontrakt
- **Opgavestyring** → Redmine issue per CP-kontrakt — se [`redmine/REDMINE_SETUP.md`](redmine/REDMINE_SETUP.md)

Vi ses i koden. Start med jeres første CP-* fra indeks — spørg hvis `depends_on` er uklar.

---

## Vedhæftninger i repo

| Fil | Indhold |
|-----|---------|
| [`prompts/CP-SESSION-001.prompt.md`](prompts/CP-SESSION-001.prompt.md) | Session isolation |
| [`prompts/CP-INTENT-001.prompt.md`](prompts/CP-INTENT-001.prompt.md) | Intent engine |
| [`prompts/CP-FLEET-001.prompt.md`](prompts/CP-FLEET-001.prompt.md) | Fleet daemon (B) |
| [`errors-v1.md`](errors-v1.md) | Fejlkoder |
| [`../docs/EIRA_Document_Map_v0.1.md`](../docs/EIRA_Document_Map_v0.1.md) | Navigation |

*EIRA Engineering — Contract-as-Prompt v0.1*
