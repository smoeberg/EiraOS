---
contract_id: CP-INTENT-001
version: 1.0.0
owner: programmer-a
status: active
schema: ../schemas/ipc-intent-v1.json
prototype_ref: ../../prototype/phase1/app/daemons/intent_engine.py
depends_on: [CP-SESSION-001, CP-IPC-001]
forbidden:
  - in-memory _pending_intents dict
  - intent_confirm without executor call
  - capability match without adapter liveness check
---

# CP-INTENT-001 — Intent engine daemon

## AGENT PROMPT

Du implementerer kontrakt **CP-INTENT-001** for EIRA phase1 intent daemon (`intent.sock` / port 18766).

**Kontekst:** Brugeren formulerer intentioner i naturligt sprog. Daemon parser, planlægger, og ved bekræftelse udfører via executor. Pending intents skal overleve daemon-genstart.

**Din opgave:**
1. Registrer handlers i `register_intent_handlers`:
   - `dashboard.get`, `intent.parse`, `intent.plan`, `intent.confirm`
   - `journey.list`, `journey.get`, `journey.advance`
   - `capability.list`, `presentation.mode_get`, `presentation.mode_set`, `health`
2. Alle metoder (undtagen `health`, `journey.*`, `capability.list`) kalder `_session_id(params)` først.
3. `intent.parse` / `intent.plan` gemmer resultat i `pending_intents` tabel via `app/pending_intents.py`.
4. `intent.confirm` validerer assurance, kalder `execute_intent`, `mark_executed`, audit `intent.executed`, `delete_pending`.
5. `plan_intent` / `parse_intent_request` i `intent_parser.py` skal fejle match hvis `adapter_health.status != online`.

**Invariants:**
1. `pending_intents` keyed by `intent_id` + scoped by `session_id`.
2. `intent.confirm` med `clarification_needed` status → `-32002 cannot_execute`.
3. `required_assurance == org_acting` uden step-up → `-32001 assurance_required` (ASSURANCE_REQUIRED).
4. Efter confirm slettes pending intent fra DB.

**Out of scope:**
- Mistral/LLM prompt engineering
- Prioritization heuristics i daemon (UI/client kan score)
- Real adapter HTTP
- Event bus publish (kun audit_events INSERT)

**Fejlkoder:**
| Kode | message | data |
|------|---------|------|
| -32001 | assurance_required | required, current, user_message |
| -32002 | cannot_execute | user_message |
| -32014 | capability_unavailable | adapter_id (via executor) |

**Acceptance:**
- GIVEN pending intent WHEN daemon restart THEN get_pending virker
- GIVEN offline adapter WHEN intent.plan THEN capability_match null eller block_reason
- GIVEN to sessions WHEN confirm på A THEN B pending uændret

**Leverance:** `intent_engine.py`, `pending_intents.py`, `intent_parser.py` integration — match phase1 reference.

--- END PROMPT ---

## INVARIANTS

1. `intent_id` er UUID genereret ved parse/plan.
2. `session_id` i response på alle session-scoped methods.
3. Audit events skrives til `audit_events` ved successful confirm.

## OUT OF SCOPE

- Intent Canvas UI
- Multi-step wizard state machine (beyond journeys table)
- Cross-session intent delegation

## ACCEPTANCE

### S1 — Persistent pending

- **GIVEN** `intent.parse` returnerer `intent_id`
- **WHEN** proces genstartes (simuleret ny DB connection)
- **THEN** `get_pending(intent_id, session_id)` returnerer payload

### S2 — Assurance gate

- **GIVEN** pending med `required_assurance: org_acting` og session `eid_low`
- **WHEN** `intent.confirm`
- **THEN** `-32001` med `user_message` om MitID

### S3 — Session scope

- **GIVEN** intent oprettet under `session_a`
- **WHEN** `intent.confirm` med `session_b`
- **THEN** `-32602` intent not found

### S4 — Execute on confirm

- **GIVEN** valid pending med online adapter
- **WHEN** `intent.confirm`
- **THEN** response `status: executed`, `execution.execution_id` sat, audit `intent.executed`
