# EIRA Object Graph Specification v0.2

**Status:** Officiel specifikation (EIRA Open Architecture)  
**Dato:** 3. juli 2026  
**Forrige:** [EIRA_Object_Graph_Specification_v0.1.md](EIRA_Object_Graph_Specification_v0.1.md)  
**Relateret:** [EIRA_Cognitive_Runtime_v1.0.md](EIRA_Cognitive_Runtime_v1.0.md)

---

## 1. Scope

Definerer den **fælles informationsmodel** — objekter, relationer og metadata — som Intent Protocol resolver mod, og adaptere synkroniserer til.

**Spørgsmål:** *Hvilke entiteter og relationer findes i brugerens verden — og hvornår var de gyldige?*

v0.2 tilføjer **validity windows** på relationer (Temporal Graph, Cognitive Runtime lag 7). Alle v0.1-felter forbliver gyldige.

**Princip:** Tynd cache — relationer og metadata, ikke dokumentindhold.

---

## 2. Objektmodel (normative)

### 2.1 Object

Uændret fra v0.1:

```json
{
  "id": "uuid",
  "type": "person | project | document | meeting | task | organisation | ai_generation | prompt",
  "name": "string",
  "owner_id": "uuid | null",
  "metadata": {},
  "ai_metadata": {},
  "created_at": "unix_ts",
  "updated_at": "unix_ts",
  "deleted_at": "unix_ts | null"
}
```

### 2.2 Relation (v0.2)

```json
{
  "id": "uuid",
  "from_id": "uuid",
  "to_id": "uuid",
  "relation_type": "belongs_to | generated_by | reviewed_by | delegates_to | reports_to | ...",
  "weight": 1.0,
  "valid_from": "2023-01-01T00:00:00Z",
  "valid_to": "2024-06-30T23:59:59Z | null",
  "metadata": {}
}
```

### 2.3 Validity windows

| Felt | Type | Påkrævet | Beskrivelse |
|------|------|----------|-------------|
| `valid_from` | ISO 8601 UTC | ja (v0.2) | Tidspunkt relationen blev gyldig |
| `valid_to` | ISO 8601 UTC \| null | ja | `null` = stadig aktiv |

**Regler:**

1. To relationer med samme `(from_id, to_id, relation_type)` må overlappe kun hvis `metadata.supersedes` peger på forrige relation.
2. Query uden tidsfilter returnerer kun **aktive** relationer (`valid_to IS NULL OR valid_to > now()`).
3. Historisk query kræver eksplicit `as_of` parameter.

### 2.4 Relation types (udvidet)

| relation_type | Beskrivelse | Temporal typisk |
|---------------|-------------|-----------------|
| `belongs_to` | Objekt tilhører projekt/sag | Ja |
| `reports_to` | Organisatorisk reporting | **Ja — kræver validity** |
| `delegates_to` | Midlertidig delegation | **Ja — kræver validity** |
| `reviewed_by` | Review-ansvar | Ja |
| `generated_by` | AI-generering | Nej (punkt-i-tid) |

---

## 3. Query interface

### 3.1 CORE (v0.1 — uændret)

| Operation | Beskrivelse |
|-----------|-------------|
| `resolve(name, type, context)` | Entity resolution for Intent |
| `neighbors(id, relation_type)` | Graf-traversal (aktive relationer) |
| `search(fts_query)` | Full-text (FTS5) |

### 3.2 TEMPORAL (v0.2 — ny)

| Operation | Beskrivelse |
|-----------|-------------|
| `neighbors_at(id, relation_type, as_of)` | Traversal på historisk tidspunkt |
| `relations_between(a_id, b_id, as_of)` | Alle relationer mellem to noder på tidspunkt |
| `history(id, relation_type)` | Alle versioner af relation (inkl. afsluttede) |

**Eksempel:** *"Hvem var Lars i forhold til Mette i marts 2024?"*

```
relations_between(lars_id, mette_id, as_of=2024-03-15T12:00:00Z)
→ reports_to (valid_from: 2023-01-01, valid_to: 2024-06-30)
```

### 3.3 SQL-eksempel (SQLite)

```sql
SELECT * FROM relations
WHERE from_id = ? AND to_id = ?
  AND valid_from <= ?
  AND (valid_to IS NULL OR valid_to > ?);
```

---

## 4. Sync model

| Kilde | Retning | Hyppighed | v0.2 note |
|-------|---------|-----------|-----------|
| Adaptere | Pull metadata → graph | Event-driven + periodic | — |
| Identity | Person, org, delegation | Ved login / grant change | `delegates_to` med validity |
| Intent engine | Læring fra rettelser | Ved bruger-feedback | — |
| HR/org-system | `reports_to` | Ved org-ændring | Afslut gammel + opret ny relation |

Ved org-ændring: **afslut** eksisterende relation (`valid_to = now`) — slet ikke historik.

---

## 5. AI metadata

Uændret fra v0.1 — first-class `ai_metadata` på objekter (EU AI Act).

---

## 6. Schema migration (v0.1 → v0.2)

```sql
ALTER TABLE relations ADD COLUMN valid_from TEXT NOT NULL DEFAULT '1970-01-01T00:00:00Z';
ALTER TABLE relations ADD COLUMN valid_to TEXT NULL;

CREATE INDEX idx_relations_temporal
  ON relations(from_id, to_id, relation_type, valid_from, valid_to);
```

Eksisterende rækker får `valid_from = created_at` ved migration.

---

## 7. Conformance

| Niveau | Krav |
|--------|------|
| **CORE** | Objects + relations, resolve, soft delete |
| **STANDARD** | + FTS, adapter sync, AI metadata, **validity windows** |
| **PREMIUM** | + `neighbors_at`, federeret graf, cross-org relations |

v0.1 STANDARD-implementeringer opgraderes til v0.2 ved at tilføje `valid_from`/`valid_to`.

---

## 8. Reference implementation

SQLite + FTS5 i EIRA OS. Phase 1 mockup: `eira-os/prototype/phase1/`.

---

## 9. Changelog fra v0.1

| Ændring | Beskrivelse |
|---------|-------------|
| + `valid_from`, `valid_to` | Validity windows på relationer |
| + `neighbors_at`, `relations_between`, `history` | Temporal queries |
| + `reports_to` | Eksplicit org-relation med temporal krav |
| = objects | Uændret |
| = sync | HR/identity skal afslutte relationer ved ændring |
| → v0.3 | + relation `evidence` — [Object Graph v0.3](EIRA_Object_Graph_Specification_v0.3.md) |

---

*EIRA Object Graph Specification v0.2*
