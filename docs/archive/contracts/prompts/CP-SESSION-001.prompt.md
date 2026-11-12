---
contract_id: CP-SESSION-001
version: 1.0.0
owner: programmer-a
status: active
schema: null
prototype_ref: ../../prototype/phase1/app/session_store.py
depends_on: []
forbidden:
  - global _session variable
  - global _presentation_mode
  - module-level mutable user state
---

# CP-SESSION-001 — Session isolation (database-backed)

## AGENT PROMPT

Du implementerer kontrakt **CP-SESSION-001** for EIRA phase1.

**Kontekst:** EIRA skal understøtte flere samtidige brugere. Al bruger-tilstand lever i SQLite — aldrig i globale Python-variabler.

**Din opgave:**
1. Vedligehold `app/session_store.py` med: `ensure_session`, `get_session`, `update_assurance`, `get_presentation_mode`, `set_presentation_mode`.
2. Tabel `sessions` i `app/database.py` med kolonner: `session_id`, `actor_id`, `actor_name`, `org_unit`, `assurance_level`, `delegated_for`, `presentation_mode`, `created_at`, `updated_at`.
3. Alle daemons der håndterer bruger-state skal kalde `ensure_session(params.get("session_id"), params.get("actor_id"))` før logik.
4. HTTP bridge sender `session_id` via header `X-EIRA-Session-Id`; IPC client inkluderer `session_id` i JSON-RPC params.

**Invariants:**
1. Step-up (`assurance_level`) på session A må ALDRIG ændre session B.
2. `presentation_mode` (`explorer` | `builder`) er per `session_id`.
3. Ny session får `assurance_level = eid_low`, `presentation_mode = explorer`.
4. Ingen `global` eller module-level dict for sessions.

**Out of scope:**
- Entra OIDC login flow (hardcoded DEFAULT_ACTOR OK i prototype)
- JWT / cookie parsing
- Session expiry / TTL
- Redis eller ekstern session store

**Fejlkoder:** Brug `-32602` for manglende/ugyldige params i kaldere — ikke i session_store selv.

**Acceptance:**
- GIVEN session A og B WHEN step_up på A THEN B assurance_level uændret
- GIVEN session A WHEN presentation_mode_set builder THEN kun A er builder
- GIVEN ingen session_id WHEN dashboard.get THEN ny session_id returneres og persisteres

**Leverance:** `session_store.py`, `database.py` (sessions tabel), opdater kaldere — ingen visiondocs.

--- END PROMPT ---

## INVARIANTS

1. Én række per `session_id` i `sessions`.
2. Alle user-scoped IPC methods kræver `session_id` efter første `dashboard.get`.
3. `update_assurance` opdaterer kun den angivne `session_id`.

## OUT OF SCOPE

- OIDC / Entra integration
- Cross-device session sync
- Admin session revocation API

## ACCEPTANCE

### S1 — Step-up isolation

- **GIVEN** `session_a` og `session_b` med `eid_low`
- **WHEN** `identity.step_up` kaldes med `session_id=session_a`
- **THEN** `get_session(session_a).assurance_level == org_acting` og `get_session(session_b).assurance_level == eid_low`

### S2 — Presentation mode isolation

- **GIVEN** to aktive sessions
- **WHEN** `presentation.mode_set` med `mode=builder` på session A
- **THEN** session B `presentation_mode` forbliver `explorer`

### S3 — Auto-provision

- **GIVEN** ukendt `session_id` UUID
- **WHEN** `ensure_session(sid, actor_id)` kaldes
- **THEN** række oprettes og samme `session_id` returneres ved gentaget kald
