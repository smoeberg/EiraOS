---
contract_id: CP-XXX-001
version: 0.1.0
owner: programmer-a
status: draft
schema: ../schemas/ipc-xxx-v1.json
prototype_ref: ../../prototype/phase1/app/...
depends_on: []
forbidden: []
---

# CP-XXX-001 — [Kort titel]

## AGENT PROMPT

Du implementerer kontrakt **CP-XXX-001** for EIRA phase1 reference runtime.

**Kontekst:** EIRA er enterprise runtime på Ubuntu. Du arbejder i `eira-os/prototype/phase1/`.
Reference: `prototype_ref` i frontmatter. Match eksisterende Python-stil (typed, sqlite3, pydantic).

**Din opgave:**
1. [Konkret opgave 1]
2. [Konkret opgave 2]

**Invariants (bryd aldrig):**
1. [Invariant]
2. [Invariant]

**Out of scope — implementer IKKE:**
- [Punkt]
- [Punkt]

**Fejlkoder du skal bruge:**
| Kode | message | data |
|------|---------|------|
| -32602 | invalid params | `{...}` |

**Acceptance (skal bestå som pytest):**
- GIVEN … WHEN … THEN …
- GIVEN … WHEN … THEN …

**Leverance:** Kun filer listet i opgaven. Ingen nye visiondocs. Ingen global session state.

--- END PROMPT ---

## INVARIANTS

1. …

## OUT OF SCOPE

- …

## ACCEPTANCE

### S1 — [navn]

- **GIVEN** …
- **WHEN** …
- **THEN** …
