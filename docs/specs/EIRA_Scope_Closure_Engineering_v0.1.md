# EIRA — Scope Closure & Engineering Gap Analysis v0.1

**Status:** Normativ — lukker kreativ fase, åbner kontrakt-fase  
**Dato:** 4. juli 2026  
**Formål:** Verificere kritiske huller før Architecture/Contract Freeze  
**Relateret:** [Document Map](../EIRA_Document_Map_v0.1.md), [phase1 README](../../prototype/phase1/README.md)

---

## Beslutning

| Fase | Status |
|------|--------|
| Vision | **LUKKET** — ingen nye visionsdocs |
| Arkitektur (koncept) | **LUKKET** — kun engineering gaps |
| Engineering (kontrakter) | **ÅBEN** — IPC schemas, events, states |
| Reference runtime | **ÅBEN** — phase1 = autoritativ indtil Rust |

> Udviklere bygger kontrakter — ikke arkitektur-beskrivelser.

---

## 1. Kritiske mangler — verifikation

### 1.1 Fleet Control — ingen implementering

| Påstand | Verifikat |
|---------|-----------|
| Ingen fleetd | ✅ Bekræftet — kun intent/identity/graph daemons |
| Ingen device-tabeller | ✅ Bekræftet i `database.py` (før P0-fix) |
| Spec findes | ✅ `eira-fleet-control/.../EIRA_Fleet_Agent_Protocol_v0.1.md` |

**Scope-beslutning:**

| Komponent | Hvor | Prototype P0 |
|-----------|------|----------------|
| Fleet API (cloud) | `eira-fleet-control` | Udenfor phase1 |
| `eira-governance-agent` | EIRA OS endpoint | P1 — heartbeat client |
| `fleetd` (lokal IPC) | phase1 reference | **P0 skeleton** — enroll, heartbeat, devices tabel |
| Bundle apply + snapshot | Fleet agent + OS | P2 — hook i executor, ikke btrfs i Windows-dev |

Fleet i phase1 er **reference-kontrakt** — ikke fuld 1.000-PC drift.

---

### 1.2 Multi-user & session isolation

| Påstand | Verifikat |
|---------|-----------|
| Global `_session` i identityd | ✅ |
| Global `_presentation_mode` | ✅ |
| Step-up påvirker alle | ✅ Konsekvens korrekt |

**P0-fix (implementeret):**

- `sessions` tabel — `session_id` scoped state
- Alle IPC-kald bærer `session_id` (HTTP: header `X-EIRA-Session-Id`)
- `identity.step_up` opdaterer kun én session

**Kontrakt-krav (P1):**

- Session oprettes ved login (Entra OIDC) — ikke hardcoded Mette
- Builder mode per session + policy

---

### 1.3 Stubs uden handling

| Påstand | Verifikat |
|---------|-----------|
| `intent_confirm` kun audit | ✅ |
| Ingen adapter-kald | ✅ |

**P0-fix:**

- `executor.execute_intent()` — dispatcher til adapter-stub med audit
- Returnerer `execution_id` + adapter_id — klar til rigtig transport

**P1:** HTTP/gRPC til adapter sidecar. **Ikke** i scope for kontrakt-freeze.

---

## 2. Tekniske fejl — verifikation

### 2.1 Race conditions — `_pending_intents` in-memory

| Påstand | Verifikat |
|---------|-----------|
| Dict mistes ved genstart | ✅ |

**P0-fix:** `pending_intents` tabel i SQLite med `session_id`, status, payload JSON.

---

### 2.2 Capability-validering

| Påstand | Verifikat |
|---------|-----------|
| Kun manifest lookup | ✅ `find_capability_match` |
| Ingen liveness | ✅ |

**P0-fix:** `adapter_health` tabel — `online` \| `offline` \| `degraded`. Match fejler hvis offline.

---

### 2.3 IPC autentificering bridge → sockets

| Påstand | Verifikat |
|---------|-----------|
| Ingen token | ✅ |

**P0-fix:** `EIRA_IPC_TOKEN` env — `_eira.ipc_token` i JSON-RPC params, valideret i `JsonRpcServer.handle_line`, strippes før handler.

**Produktion:** Unix socket permissions + peer cred + mTLS (Fleet Agent Protocol).

---

## 3. Arkitektoniske forbedringer — prioritering

| Forslag | Prioritet | Beslutning |
|---------|-----------|------------|
| Global state → DB | **P0** | Implementeret (sessions, pending_intents) |
| fleetd daemon | **P0** | Skeleton + devices tabel |
| Btrfs/ZFS snapshot ved bundle | **P2** | Executor returnerer `snapshot_required`; implementeres i governance-agent på Linux |
| Error catalogue | **P1** | `contracts/errors-v1.md` |
| Event catalog | **P1** | `contracts/events-v1.yaml` |
| Canonical model JSON | **P1** | `contracts/canonical-model-v1.json` |

---

## 4. Kontrakt-freeze leverancer (næste 2–4 uger)

**AI-first:** Kontrakter leveres som **prompts** (agent-instruktioner) + **schemas** (maskinvalidering).

```
eira-os/contracts/
  EIRA_Contract_Prompt_Framework_v0.1.md   ← metode
  README.md
  errors-v1.md                             ← leveret
  prompts/
    CP-SESSION-001.prompt.md               ← leveret
    CP-IPC-001.prompt.md
    CP-INTENT-001.prompt.md
    CP-IDENTITY-001.prompt.md
    CP-FLEET-001.prompt.md
    CP-EXECUTOR-001.prompt.md
  schemas/                                 ← TODO
    ipc-intent-v1.json
    ipc-identity-v1.json
    ipc-graph-v1.json
    ipc-fleet-v1.json
  events-v1.yaml
  canonical-model-v1.json
  state-machines/
    intent.md
    journey.md
    identity.md
    device.md
```

**Regel:** Schema først → CP-prompt → kode → pytest i `tests/contracts/`.

---

## 5. Acceptance — prototype P0 (efter denne leverance)

| # | Given | When | Then |
|---|-------|------|------|
| S1 | To session_id | Step-up på A | B assurance uændret |
| S2 | Pending intent i DB | Daemon genstart | intent_confirm stadig virker |
| S3 | Adapter offline | intent.plan | block_reason = adapter utilgængelig |
| S4 | fleet.enroll | heartbeat | device i DB med timestamp |
| S5 | Forkert ipc_token | IPC call | -32010 auth_failed |

---

## Relaterede dokumenter

| Dokument | Link |
|----------|------|
| Fleet Agent Protocol | [fleet-control spec](../../../eira-fleet-control/docs/specs/EIRA_Fleet_Agent_Protocol_v0.1.md) |
| Desktop IPC | [Desktop Architecture](EIRA_Desktop_Architecture_v1.0.md) |
| Document Map | [EIRA_Document_Map_v0.1.md](../EIRA_Document_Map_v0.1.md) |

---

*EIRA Scope Closure Engineering v0.1*
