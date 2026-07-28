# EIRA Contract Prompts — indeks

**Brug:** Vælg kontrakt → paste AGENT PROMPT → implementer → kør acceptance.

Framework: [EIRA_Contract_Prompt_Framework_v0.1.md](../EIRA_Contract_Prompt_Framework_v0.1.md)

---

## Aktive kontrakter (P1)

| ID | Ejer | Status | Beskrivelse |
|----|------|--------|-------------|
| [CP-SESSION-001](CP-SESSION-001.prompt.md) | A | active | Session isolation — ingen global state |
| [CP-IPC-001](CP-IPC-001.prompt.md) | A | active | JSON-RPC transport + token auth |
| [CP-INTENT-001](CP-INTENT-001.prompt.md) | A | active | Intent engine daemon + pending intents |
| [CP-IDENTITY-001](CP-IDENTITY-001.prompt.md) | A | active | Identity daemon — step-up per session |
| [CP-FLEET-001](CP-FLEET-001.prompt.md) | B | active | fleetd — enroll, heartbeat, devices |
| [CP-EXECUTOR-001](CP-EXECUTOR-001.prompt.md) | A | active | Intent execute path + adapter dispatch |

## Planlagt (P1 uge 2+)

| ID | Ejer | Beskrivelse |
|----|------|-------------|
| CP-GRAPH-001 | A | graph.context + temporal query |
| CP-GOVERNANCE-AGENT-001 | B | Heartbeat client → fleet-control |
| CP-ADAPTER-001 | B | Adapter sidecar transport |
| CP-EVENTS-001 | A | Event catalog implementation |

---

## Rækkefølge (depends_on)

```
CP-SESSION-001
    ├── CP-IPC-001
    ├── CP-IDENTITY-001
    └── CP-INTENT-001
            └── CP-EXECUTOR-001

CP-FLEET-001  (parallel med A-sporet efter CP-IPC-001)
    └── CP-GOVERNANCE-AGENT-001
```

---

## Template

Ny kontrakt: kopiér [_TEMPLATE.prompt.md](_TEMPLATE.prompt.md) → `CP-XXX-001.prompt.md`.
