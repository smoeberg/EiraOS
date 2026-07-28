---
contract_id: CP-FLEET-001
version: 1.0.0
owner: programmer-b
status: active
schema: ../schemas/ipc-fleet-v1.json
prototype_ref: ../../prototype/phase1/app/daemons/fleetd.py
depends_on: [CP-IPC-001]
forbidden:
  - full fleet-control cloud API in phase1
  - bundle apply execution in fleetd
  - in-memory device registry
---

# CP-FLEET-001 — Fleet daemon (reference skeleton)

## AGENT PROMPT

Du implementerer kontrakt **CP-FLEET-001** for EIRA phase1 fleet daemon (`fleet.sock` / port 18769).

**Kontekst:** Dette er en **lokal reference** for Fleet Agent Protocol — ikke fuld 1.000-PC drift. Cloud Fleet API lever i `eira-fleet-control`. Endpoint agent (`eira-governance-agent`) kalder denne daemon i P1.

**Din opgave:**
1. Tabel `devices` i `database.py`: `device_id`, `hostname`, `tenant_id`, `bundle_applied`, `bundle_pending`, `compliance_pct`, `last_heartbeat`, `enrolled_at`, `status`.
2. Handlers i `fleetd.py`:
   - `fleet.enroll` — upsert device, return `device_id`, `status: enrolled`
   - `fleet.heartbeat` — kræv enrolled device, opdater `last_heartbeat`, optional `bundle_applied`, return `commands: []`
   - `fleet.device.get` — hent én device
   - `fleet.list` — liste med `limit` (default 50)
   - `health`
3. HTTP bridge endpoints: `POST /v1/fleet/enroll`, `POST /v1/fleet/heartbeat`, `GET /v1/fleet/devices/{id}`
4. Align feltnavne med `eira-fleet-control/docs/specs/EIRA_Fleet_Agent_Protocol_v0.1.md` CORE — afvigelser dokumentér i schema.

**Invariants:**
1. `device_id` er UUID string — stabil på re-enroll (ON CONFLICT update).
2. Heartbeat på ukendt device → `-32602 device not enrolled`.
3. `commands` array returneres altid (tom i prototype).
4. Devices persisteres i SQLite — ikke dict i memory.

**Out of scope:**
- Bundle download / apply
- Btrfs/ZFS snapshot
- Remote fleet-control HTTP (governance-agent's job)
- Device certificate enrollment
- Multi-tenant isolation beyond `tenant_id` column

**Fejlkoder:**
| Kode | message |
|------|---------|
| -32602 | device_id required / not enrolled / not found |

**Acceptance:**
- GIVEN enroll WHEN heartbeat THEN ack true
- GIVEN unknown device WHEN heartbeat THEN error
- GIVEN 3 devices WHEN fleet.list limit 2 THEN 2 rows

**Leverance:** `fleetd.py`, `devices` tabel, `http_bridge.py` fleet routes, `ipc/paths.py` fleet.sock.

**Reference spec:** `eira-fleet-control/docs/specs/EIRA_Fleet_Agent_Protocol_v0.1.md` — læs KUN CORE sektion, ikke vision.

--- END PROMPT ---

## INVARIANTS

1. `last_heartbeat` opdateres på hver heartbeat.
2. `status` er `active` efter enroll/heartbeat.
3. Programmer B ejer fleetd; ændringer i `database.py` koordineres med Programmer A via PR.

## OUT OF SCOPE

- Policy bundle compiler
- Staged rollout %
- Device quarantine workflow
- Fleet console UI

## ACCEPTANCE

### S1 — Enroll idempotent

- **GIVEN** `device_id=X` enrolled
- **WHEN** `fleet.enroll` med samme `device_id` og ny `hostname`
- **THEN** samme `device_id`, hostname opdateret

### S2 — Heartbeat ack

- **GIVEN** enrolled device
- **WHEN** `fleet.heartbeat` med `compliance_pct: 95`
- **THEN** `ack: true`, DB `compliance_pct == 95`

### S3 — Unknown device

- **GIVEN** random UUID ikke i DB
- **WHEN** `fleet.heartbeat`
- **THEN** `-32602` device not enrolled

### S4 — List ordering

- **GIVEN** flere devices med forskellige heartbeats
- **WHEN** `fleet.list`
- **THEN** sorteret `last_heartbeat DESC`
