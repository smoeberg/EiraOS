# EIRA Error Catalogue v0.1

**Brug:** Alle IPC handlers og AI-kontrakter refererer disse koder.

## JSON-RPC standard

| Kode | message | Hvornår |
|------|---------|---------|
| -32600 | invalid request | Malformed JSON-RPC |
| -32601 | method not found | Ukendt method |
| -32602 | invalid params | Manglende/forkert param |
| -32603 | internal error | Uventet exception |

## EIRA domæne

| Kode | message | data felter | Kontrakt |
|------|---------|-------------|----------|
| -32001 | assurance_required | `required`, `current`, `user_message` | CP-INTENT-001 |
| -32002 | cannot_execute | `user_message`, optional `block_reason` | CP-INTENT-001, CP-EXECUTOR-001 |
| -32003 | builder_not_allowed | `user_message` | CP-INTENT-001 |
| -32010 | ipc_auth_failed | `user_message` | CP-IPC-001 |
| -32014 | capability_unavailable | `adapter_id`, `user_message` | CP-EXECUTOR-001 |

## Konventioner

- `user_message` er dansk, brugervenlig — vises i Explorer UI.
- `data` objekt sendes altid ved domænefejl (ikke ved -32603).
- Nye koder: MINOR bump af contract version; breaking: MAJOR.

## AI-regel

Når du implementerer en handler: **genbrug eksisterende kode** — opfind ikke nye fejlkoder uden at opdatere denne fil og relevant CP-*.prompt.md.
