---
contract_id: CP-EXECUTOR-001
version: 1.0.0
owner: programmer-a
status: active
schema: null
prototype_ref: ../../prototype/phase1/app/executor.py
depends_on: [CP-INTENT-001]
forbidden:
  - silent no-op on confirm
  - execute without adapter_health check
  - skip audit_events on execute
---

# CP-EXECUTOR-001 — Intent execution path

## AGENT PROMPT

Du implementerer kontrakt **CP-EXECUTOR-001** for EIRA phase1 execute path.

**Kontekst:** `intent.confirm` kalder `execute_intent(pending)`. Prototype bruger stub-dispatch — men kontrakten definerer den rigtige struktur for produktion (adapter transport, snapshot hook).

**Din opgave:**
1. `app/executor.py` — `execute_intent(pending: dict) -> dict`
2. Pre-conditions:
   - `capability_match` skal findes — ellers `-32002 cannot_execute`
   - `is_adapter_online(adapter_id)` — ellers `-32014 capability_unavailable`
3. Returnér:
   - `execution_id` (UUID)
   - `intent_id`, `adapter_id`, `action`, `resource`
   - `status`: `executed_stub` (prototype) eller `executed` (prod)
   - `message` — menneskelig tekst
   - `snapshot_required: true` når `action in ("apply_bundle", "approve_bundle")`
   - `snapshot_note` — tekst om btrfs/zfs i prod
4. INSERT audit `capability.executed` med fuld result JSON.
5. Ingen ekstern HTTP i prototype — men struktur skal tillade `adapter_transport.call()` senere.

**Invariants:**
1. Executor kaldes KUN fra `intent.confirm` — ikke fra parse/plan.
2. Offline adapter blokerer altid — uanset manifest findes.
3. `snapshot_required` sættes — governance-agent implementerer snapshot (P2).
4. Hver execution får unikt `execution_id`.

**Out of scope:**
- Faktisk btrfs/zfs snapshot (Linux agent)
- Adapter sidecar gRPC/HTTP
- Retry / idempotency keys
- Compensation / rollback

**Fejlkoder:**
| Kode | message |
|------|---------|
| -32002 | cannot_execute |
| -32014 | capability_unavailable |

**Acceptance:**
- GIVEN valid pending + online adapter WHEN execute THEN execution_id + audit row
- GIVEN offline adapter WHEN execute THEN -32014
- GIVEN action approve_bundle WHEN execute THEN snapshot_required true

**Leverance:** `executor.py`, evt. `adapter_transport.py` stub — ingen ændring af UI.

--- END PROMPT ---

## INVARIANTS

1. Audit payload er JSON med alle execution felter.
2. Executor er pure function modulo DB audit write — ingen session global state.
3. `pending` dict er den persisted payload fra `pending_intents`.

## OUT OF SCOPE

- Real Public360 / SAP / BC API calls
- Transaction saga across adapters
- Execution queue / worker

## ACCEPTANCE

### S1 — Happy path stub

- **GIVEN** pending med `capability_match.adapter_id` online
- **WHEN** `execute_intent(pending)`
- **THEN** `execution_id` UUID, `status == executed_stub`, audit `capability.executed`

### S2 — Offline adapter

- **GIVEN** adapter `status=offline` i `adapter_health`
- **WHEN** `execute_intent`
- **THEN** `JsonRpcError -32014`

### S3 — Snapshot flag

- **GIVEN** `action: approve_bundle`
- **WHEN** `execute_intent`
- **THEN** `snapshot_required is True`

### S4 — No match

- **GIVEN** pending uden `capability_match`
- **WHEN** `execute_intent`
- **THEN** `-32002`
