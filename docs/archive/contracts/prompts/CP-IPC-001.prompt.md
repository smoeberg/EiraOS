---
contract_id: CP-IPC-001
version: 1.0.0
owner: programmer-a
status: active
schema: ../schemas/ipc-transport-v1.json
prototype_ref: ../../prototype/phase1/app/ipc/
depends_on: [CP-SESSION-001]
forbidden:
  - unauthenticated bridge access in production config
  - JSON-RPC methods without registered handler
---

# CP-IPC-001 — IPC transport & authentication

## AGENT PROMPT

Du implementerer kontrakt **CP-IPC-001** for EIRA phase1.

**Kontekst:** Daemons kommunikerer via JSON-RPC over Unix sockets (Linux) eller TCP localhost (Windows dev). HTTP bridge er eneste eksterne indgang og forwarder til sockets.

**Din opgave:**
1. JSON-RPC 2.0 i `app/ipc/jsonrpc.py`: `JsonRpcServer`, `JsonRpcError`, line-delimited requests.
2. Transport i `app/ipc/transport.py`: daemons `intent` (18766), `identity` (18767), `graph` (18768), `fleet` (18769).
3. Auth i `app/ipc/auth.py`: hvis env `EIRA_IPC_TOKEN` er sat, kræv `params._eira.ipc_token` — ellers tillad (dev).
4. `strip_and_validate_ipc_auth` kaldes i `handle_line` FØR handler; `_eira` strippes fra params.
5. `app/ipc/client.py` sender `session_id` og `ipc_token` automatisk.
6. Fejl `-32010` (`ipc_auth_failed`) ved token mismatch.

**Invariants:**
1. Handlers modtager aldrig `_eira` metadata.
2. `EIRA_IPC_TOKEN` tom = auth disabled (kun dev).
3. Én daemon = én socket/port = én handler registry.
4. `health` method på hver daemon returnerer `{"daemon": "...", "ok": true}`.

**Out of scope:**
- mTLS mellem daemons
- Unix peer credentials (Linux prod — dokumentér som P2)
- gRPC
- Remote IPC over netværk

**Fejlkoder:**
| Kode | message |
|------|---------|
| -32010 | ipc_auth_failed |
| -32600 | invalid request |
| -32601 | method not found |
| -32602 | invalid params |
| -32603 | internal error |

**Acceptance:**
- GIVEN EIRA_IPC_TOKEN=secret WHEN call uden token THEN -32010
- GIVEN token korrekt WHEN intent.parse THEN success
- GIVEN daemon stopped WHEN client.call THEN ConnectionError

**Leverance:** `app/ipc/*`, `app/daemons/runner.py` — ingen ændring af business logic i handlers.

--- END PROMPT ---

## INVARIANTS

1. JSON-RPC `id` echoes i response.
2. Batch requests understøttes ikke (én request per linje).
3. Bridge (`http_bridge.py`) bruger samme `ipc_client` som interne kald.

## OUT OF SCOPE

- WebSocket transport
- IPC mellem hosts
- Rate limiting

## ACCEPTANCE

### S1 — Token required

- **GIVEN** `EIRA_IPC_TOKEN=test-secret`
- **WHEN** JSON-RPC uden `_eira.ipc_token`
- **THEN** error code `-32010`, message `ipc_auth_failed`

### S2 — Token accepted

- **GIVEN** `EIRA_IPC_TOKEN=test-secret`
- **WHEN** call med `_eira: {ipc_token: test-secret}`
- **THEN** handler kører; `_eira` ikke passed til handler

### S3 — Dev mode without token

- **GIVEN** `EIRA_IPC_TOKEN` unset
- **WHEN** vilkårligt IPC kald
- **THEN** success uden token
