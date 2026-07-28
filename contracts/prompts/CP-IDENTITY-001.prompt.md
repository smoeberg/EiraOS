---
contract_id: CP-IDENTITY-001
version: 1.0.0
owner: programmer-a
status: active
schema: ../schemas/ipc-identity-v1.json
prototype_ref: ../../prototype/phase1/app/daemons/identityd.py
depends_on: [CP-SESSION-001, CP-IPC-001]
forbidden:
  - global session state
  - step_up affecting all users
---

# CP-IDENTITY-001 — Identity daemon

## AGENT PROMPT

Du implementerer kontrakt **CP-IDENTITY-001** for EIRA phase1 identity daemon (`identity.sock` / port 18767).

**Kontekst:** Identity håndterer session snapshot og step-up (MitID Erhverv → `org_acting`). Ingen global state.

**Din opgave:**
1. Handlers: `identity.session`, `identity.step_up`, `health`
2. `identity.session` — returner `get_session(session_id)` efter `ensure_session`
3. `identity.step_up` — `update_assurance(session_id, "org_acting")`, returner opdateret session
4. Kræv `session_id` i params (via `ensure_session` hvis mangler ved session call)

**Invariants:**
1. Step-up opdaterer KUN den angivne `session_id` i `sessions` tabel.
2. `identity.session` returnerer: `session_id`, `actor_id`, `actor_name`, `org_unit`, `assurance_level`, `delegated_for`, `presentation_mode`.
3. Ingen OIDC token validering i prototype — step_up er trust-on-first-use (demo).

**Out of scope:**
- MitID / OID4VP integration
- Wallet / EUDI
- `eira-identity-core` Rust crate
- Assurance downgrade API
- Session logout / revoke

**Acceptance:**
- GIVEN session A og B WHEN step_up A THEN kun A er org_acting
- GIVEN ny session WHEN identity.session THEN assurance_level eid_low

**Leverance:** `identityd.py` kun — brug `session_store.py`, opret ikke parallel identity state.

--- END PROMPT ---

## INVARIANTS

1. Identity daemon læser/skriver kun via `session_store` — ikke direkte SQL i handlers (medmindre allerede i reference).
2. `health` returnerer `{"daemon": "eira-identityd", "ok": true}`.

## OUT OF SCOPE

- Credential verification
- ARF / HAIP
- Audit af step-up (kan tilføjes P2)

## ACCEPTANCE

### S1 — Isolated step-up

- **GIVEN** `session_a`, `session_b`
- **WHEN** `identity.step_up` med `session_id=session_a`
- **THEN** A: `org_acting`, B: `eid_low`

### S2 — Session read

- **GIVEN** eksisterende session
- **WHEN** `identity.session`
- **THEN** alle session felter returneres

### S3 — No global bleed

- **GIVEN** module reload (ny Python process)
- **WHEN** step_up på session A, derefter læs B fra DB
- **THEN** B unaffected (state kun i SQLite)
