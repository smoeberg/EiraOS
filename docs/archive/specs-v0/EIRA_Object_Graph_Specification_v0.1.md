# EIRA Object Graph Specification v0.1

**Status:** Officiel specifikation (EIRA Open Architecture)  
**Dato:** 26. juni 2026  
**Relateret:** EIRA OS Whitepaper kap. 6

---

## 1. Scope

Definerer den **f�lles informationsmodel** � objekter, relationer og metadata � som Intent Protocol resolver mod, og adaptere synkroniserer til.

**Sp�rgsm�l:** *Hvilke entiteter og relationer findes i brugerens verden?*

**Princip:** Tynd cache � relationer og metadata, ikke dokumentindhold.

---

## 2. Objektmodel (normative)

### 2.1 Object

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

### 2.2 Relation

```json
{
  "id": "uuid",
  "from_id": "uuid",
  "to_id": "uuid",
  "relation_type": "belongs_to | generated_by | reviewed_by | delegates_to | ...",
  "weight": 1.0,
  "metadata": {}
}
```

---

## 3. Sync model

| Kilde | Retning | Hyppighed |
|-------|---------|-----------|
| Adaptere | Pull metadata ? graph | Event-driven + periodic |
| Identity | Person, org, delegation | Ved login / grant change |
| Intent engine | L�ring fra rettelser | Ved bruger-feedback |

**Ingen content sync** � kun IDs, navne, paths, relationer.

---

## 4. Query interface (CORE)

| Operation | Beskrivelse |
|-----------|-------------|
| `resolve(name, type, context)` | Entity resolution for Intent |
| `neighbors(id, relation_type)` | Graf-traversal |
| `search(fts_query)` | Full-text (FTS5) |

---

## 5. AI metadata

First-class `ai_metadata` p� objekter (whitepaper kap. 6) � p�kr�vet for EU AI Act conformance.

---

## 6. Conformance

| Niveau | Krav |
|--------|------|
| **CORE** | Objects + relations, resolve, soft delete |
| **STANDARD** | + FTS, adapter sync, AI metadata |
| **PREMIUM** | + Federeret graf, cross-org relations |

---

## 7. Reference implementation

SQLite + FTS5 i EIRA OS Lag 6. Schema i whitepaper kap. 6.

---

*EIRA Object Graph Specification v0.1*
