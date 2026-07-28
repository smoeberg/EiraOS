# EIRA Engineering Contracts

**Status:** Contract-as-Prompt fase (AI-first udvikling)  
**Autoritativ runtime:** `../prototype/phase1/`

---

## To lag — begge obligatoriske

| Lag | Mappe | Formål |
|-----|-------|--------|
| **Agent prompts** | [`prompts/`](prompts/) | Copy-paste instruktioner til AI-bot |
| **Maskin schemas** | [`schemas/`](schemas/) | JSON Schema, events, fejlkatalog |

Framework: **[EIRA_Contract_Prompt_Framework_v0.1.md](EIRA_Contract_Prompt_Framework_v0.1.md)**

---

## Hurtig start (hovedprogrammør)

1. Åbn [`prompts/README.md`](prompts/README.md) — vælg kontrakt (CP-*)
2. Kopiér **AGENT PROMPT**-blokken til Cursor Agent
3. Implementer → kør acceptance (pytest `tests/contracts/` når klar)
4. Markér kontrakt `frozen` i frontmatter

### Rollefordeling

| Programmer | Domæne |
|------------|--------|
| **A** — Endpoint Runtime | Session, IPC, Intent, Identity, Graph, Executor, HTTP bridge |
| **B** — Fleet & Integration | fleetd, governance-agent, adapters, fleet-control alignment |

---

## Redmine (kontrakter, sprint, kode)

Styr udvikling i Redmine: [`redmine/REDMINE_SETUP.md`](redmine/REDMINE_SETUP.md)

| Trin | Kommando |
|------|----------|
| Generér issues fra prompts | `python redmine/sync_contracts.py` |
| Import til Redmine | `python redmine/import_to_redmine.py` |
| Koordinator-rapport | `python redmine/coordinator.py report` |
| Auto-allokér opgaver | `python redmine/coordinator.py allocate` |

---

## Aktive kontrakt-prompts

| ID | Fil |
|----|-----|
| CP-SESSION-001 | [prompts/CP-SESSION-001.prompt.md](prompts/CP-SESSION-001.prompt.md) |
| CP-IPC-001 | [prompts/CP-IPC-001.prompt.md](prompts/CP-IPC-001.prompt.md) |
| CP-INTENT-001 | [prompts/CP-INTENT-001.prompt.md](prompts/CP-INTENT-001.prompt.md) |
| CP-IDENTITY-001 | [prompts/CP-IDENTITY-001.prompt.md](prompts/CP-IDENTITY-001.prompt.md) |
| CP-FLEET-001 | [prompts/CP-FLEET-001.prompt.md](prompts/CP-FLEET-001.prompt.md) |
| CP-EXECUTOR-001 | [prompts/CP-EXECUTOR-001.prompt.md](prompts/CP-EXECUTOR-001.prompt.md) |

---

## Maskin-kontrakter (under opbygning)

| Fil | Status |
|-----|--------|
| `schemas/ipc-intent-v1.json` | TODO — generér fra phase1 |
| `schemas/ipc-identity-v1.json` | TODO |
| `schemas/ipc-fleet-v1.json` | TODO |
| `schemas/ipc-graph-v1.json` | TODO |
| `events-v1.yaml` | TODO |
| `errors-v1.md` | TODO |

---

## P0 prototype alignment

| Kontrakt-element | Prototype |
|------------------|-----------|
| `session_id` scoped state | `sessions` + `X-EIRA-Session-Id` |
| Persistent pending intents | `pending_intents` |
| `fleet.enroll` / `fleet.heartbeat` | `fleetd` |
| Adapter liveness | `adapter_health` |
| IPC token | `EIRA_IPC_TOKEN` + `_eira.ipc_token` |
| Intent execute | `executor.execute_intent()` |

Se [Scope Closure](../docs/specs/EIRA_Scope_Closure_Engineering_v0.1.md).

---

## Regel for AI-agenter

> Læs **CP-*.prompt.md** for opgaven. Læs **ikke** visiondocs medmindre prompten henviser eksplicit.
