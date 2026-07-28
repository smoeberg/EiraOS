# EIRA Object Graph Specification v0.3

**Status:** Officiel specifikation (EIRA Open Architecture)  
**Dato:** 4. juli 2026  
**Forrige:** [EIRA_Object_Graph_Specification_v0.2.md](EIRA_Object_Graph_Specification_v0.2.md)  
**Relateret:** [EIRA_Identity_Strategy_v0.2.md](EIRA_Identity_Strategy_v0.2.md), [EIRA_Cognitive_Runtime_v1.0.md](EIRA_Cognitive_Runtime_v1.0.md)

---

## 1. Scope

v0.2 besvarede **hvornår** en relation var gyldig (`valid_from` / `valid_to`).

v0.3 tilføjer **hvor sikker** vi er på relationen, og **hvor den kom fra** — på **næsten alle relationer**.

**Spørgsmål (udvidet):** *Hvilke entiteter og relationer findes — hvornår var de gyldige — og med hvilken evidens?*

Uden evidens på kanter kan Reasoning og AI ikke vægte stier i grafen. Temporal alene er nødvendig men ikke tilstrækkelig.

---

## 2. Relation (v0.3)

```json
{
  "id": "uuid",
  "from_id": "uuid",
  "to_id": "uuid",
  "relation_type": "belongs_to | reports_to | delegates_to | reviewed_by | ...",
  "weight": 1.0,
  "valid_from": "2023-01-01T00:00:00Z",
  "valid_to": "2024-06-30T23:59:59Z | null",
  "evidence": {
    "confidence": 0.92,
    "source": "Exchange",
    "verified": true,
    "observed_at": "2026-07-04T10:15:00Z",
    "method": "adapter_sync",
    "adapter_id": "eira-adapter-m365",
    "assurance_level": "session"
  },
  "metadata": {}
}
```

### 2.1 Evidence (normativt — påkrævet v0.3 STANDARD)

| Felt | Type | Påkrævet | Beskrivelse |
|------|------|----------|-------------|
| `confidence` | float 0.0–1.0 | ja | Epistemisk sikkerhed på denne kant |
| `source` | string | ja | Menneskeligt læsbart systemnavn (`Exchange`, `Entra ID`, `Public360`) |
| `verified` | boolean | ja | `true` hvis kilden bekræftede direkte (ikke ren inferens) |
| `observed_at` | ISO 8601 UTC | ja | Seneste observation/sync |
| `method` | enum | ja | Se §2.2 |
| `adapter_id` | string \| null | nej | EIRA adapter der skrev kanten |
| `assurance_level` | string \| null | nej | Identity assurance ved observation (`session`, `eid_high`, …) |

**Regler:**

1. **STANDARD** conformance kræver `evidence` på alle nye relationer.
2. `confidence < 0.5` → kant må ikke bruges som eneste grundlag for auto-handling.
3. `verified: false` → Reasoning skal foreslå bekræftelse før execute.
4. Ved opdatering: opret ny relation eller opdater `evidence` — bevar historik via temporal (§2.3 v0.2).

### 2.2 Evidence `method`

| method | Typisk confidence | verified |
|--------|-------------------|----------|
| `identity_grant` | 0.95–1.0 | true |
| `adapter_sync` | 0.80–0.98 | true hvis kilde ACK |
| `user_confirmed` | 0.90–1.0 | true |
| `hr_authoritative` | 0.95–1.0 | true |
| `inferred` | 0.20–0.70 | false |
| `ai_extracted` | 0.15–0.65 | false |

### 2.3 Identity-satte kanter (højeste prioritet)

Disse relationstyper **skal** have `method: identity_grant` eller `hr_authoritative` når de kommer fra Identity/HR:

| relation_type | Kilde |
|---------------|-------|
| `delegates_to` | Identity Bridge |
| `reports_to` | HR / Entra |
| `acts_for` | Identity Bridge (org-handling) |
| `member_of` | Entra groups |

> Identity er den autoritative rod for *hvem der må handle på vegne af hvem* — se [Identity Strategy §10](EIRA_Identity_Strategy_v0.2.md).

---

## 3. Relation til Trust Layer (lag 9)

| Lag | Ansvar |
|-----|--------|
| **Object Graph evidence** | Epistemisk metadata **på kanten** (fakta i verden) |
| **Trust & Evidence** | Aggregering + policy + brugerkontekst → **handlings-beslutning** |

Trust traverserer grafen og vægter stier:

```
path_confidence = min(edge.confidence) × context_boost(identity, focus)
```

UI-facade ("Kilde verificeret") kommer fra Trust — rå `confidence` på kanter er **maskinintern**.

---

## 4. Query interface (v0.3 udvidelser)

| Operation | Beskrivelse |
|-----------|-------------|
| `neighbors(id, relation_type, min_confidence=0.5)` | Traversal med evidens-gulv |
| `best_path(a_id, b_id, as_of)` | Sti med højeste samlede confidence |
| `evidence_refresh(id)` | Hent seneste evidens fra adapter/identity |

v0.2 temporal-operationer uændret.

---

## 5. Sync model (opdateret)

| Kilde | evidence.method | confidence typisk |
|-------|-----------------|-------------------|
| Identity Bridge | `identity_grant` | 0.98 |
| M365/Exchange adapter | `adapter_sync` | 0.85–0.95 |
| Public360 adapter | `adapter_sync` | 0.90–0.98 |
| Bruger rettelse | `user_confirmed` | 0.95 |
| LLM udtræk | `ai_extracted` | 0.20–0.60 |

---

## 6. Schema migration (v0.2 → v0.3)

```sql
ALTER TABLE relations ADD COLUMN evidence TEXT NOT NULL DEFAULT '{}';

CREATE INDEX idx_relations_confidence
  ON relations(json_extract(evidence, '$.confidence'));
```

Migration af eksisterende rækker:

```json
{
  "confidence": 0.75,
  "source": "legacy_migration",
  "verified": false,
  "observed_at": "<migration_timestamp>",
  "method": "inferred"
}
```

---

## 7. Conformance

| Niveau | Krav |
|--------|------|
| **CORE** | v0.1 (uden evidence) — kun legacy |
| **STANDARD** | v0.2 temporal + **v0.3 evidence på alle nye kanter** |
| **PREMIUM** | + `best_path`, federeret evidens, cross-org |

---

## 8. Changelog

| Version | Ændring |
|---------|---------|
| v0.1 | Objects + relations |
| v0.2 | + temporal (`valid_from`, `valid_to`) |
| v0.3 | + `evidence` på relationer; confidence-baseret traversal |

---

## Relaterede dokumenter

| Spørgsmål | Dokument |
|-----------|----------|
| Identity som rod | [Identity Strategy §10](EIRA_Identity_Strategy_v0.2.md) |
| Epistemisk vs runtime stack | [Cognitive Runtime §2.1](EIRA_Cognitive_Runtime_v1.0.md) |
| Navigation | [Document Map](../EIRA_Document_Map_v0.1.md) |

---

*EIRA Object Graph Specification v0.3*
