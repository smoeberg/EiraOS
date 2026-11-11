# EIRA Intent Protocol v1.1

**Status:** Officiel specifikation (EIRA Open Architecture)  
**Dato:** 3. juli 2026  
**Forrige:** [EIRA_Intent_Protocol_v0.1.md](EIRA_Intent_Protocol_v0.1.md)  
**Relateret:** [EIRA_Cognitive_Runtime_v1.0.md](EIRA_Cognitive_Runtime_v1.0.md), EIRA Identity Specification v0.1

---

## 1. Scope

Definerer hvordan **brugerintentioner** udtrykkes, parses, valideres mod policy og eksekveres — uafhængigt af UI (Explorer Mode, API, stemme).

**Spørgsmål:** *Hvad ønsker brugeren at opnå — og i hvilken formålskategori?*

v1.1 tilføjer **`category`** (formål) ved siden af **`action`** (verb) fra v0.1. Alle v0.1-felter og actions forbliver gyldige.

---

## 2. Intent lifecycle

```
Input (natural language / structured)
  → Parse (rules + optional LLM)
  → Classify category (DECISION | DISCUSSION | …)
  → Resolve (Object Graph lookup)
  → Authorize (Identity: assurance + delegation)
  → Plan (Capability + Adapter selection)
  → Execute (Adapter call)
  → Audit (Intent Audit event)
  → Present result (UX)
```

---

## 3. Intent structure (normative)

```json
{
  "intent_id": "550e8400-e29b-41d4-a716-446655440000",
  "raw_input": "Godkend budget",
  "category": "DECISION",
  "action": "approve",
  "confidence": 0.94,
  "trust_level": "probable",
  "trust_score": 71,
  "entities": [
    { "type": "document", "id": "budget_2027", "score": 0.95 }
  ],
  "context": {
    "focus": "Kommunepilot",
    "state": "Arbejde"
  },
  "journey_id": "660e8400-e29b-41d4-a716-446655440001",
  "required_assurance": "org_acting",
  "status": "pending_confirmation"
}
```

### 3.1 Felter

| Felt | Type | Påkrævet | Beskrivelse |
|------|------|----------|-------------|
| `intent_id` | uuid | ja | Unik identifikator |
| `raw_input` | string | ja* | Original brugerinput (*valgfri ved structured API) |
| `category` | enum | ja (v1.1) | Formålskategori — se §3.2 |
| `action` | string | ja | Verb fra action taxonomy — se §3.3 |
| `confidence` | float 0–1 | ja | Parse-confidence |
| `trust_level` | enum | nej | Trust-niveau fra Cognitive Runtime — se §3.4 |
| `trust_score` | int 0–100 | nej | Numerisk tillid (UI + audit) |
| `entities` | array | nej | Resolved entities fra Object Graph |
| `context` | object | nej | focus, state, … |
| `journey_id` | uuid \| null | nej | Aktiv journey hvis handling er del af flow |
| `required_assurance` | string | nej | Fra Identity Spec |
| `status` | enum | ja | `pending_confirmation` \| `confirmed` \| `executed` \| `rejected` \| `clarification_needed` |

### 3.2 Category taxonomy (v1.1)

| Category | Formål | Typiske actions |
|----------|--------|-----------------|
| `DECISION` | Træffe eller registrere beslutning | `approve`, `reject`, `postpone` |
| `DISCUSSION` | Udforske, afklare | `explore`, `brainstorm`, `clarify` |
| `INFORMATION` | Modtage eller give status | `brief`, `status`, `report`, `read`, `search` |
| `ACTION` | Forpligte eller udføre opgave | `agree`, `promise`, `task`, `send`, `create` |
| `RELATION` | Etablere eller ændre relation | `build`, `maintain`, `close` |

**Regel:** Hver `action` skal tilhøre præcis én `category`. Parseren sætter begge; ved konflikt vinder eksplicit `category` fra structured API.

### 3.3 Action taxonomy (CORE — uændret fra v0.1)

| Action | Category (default) | Beskrivelse |
|--------|-------------------|-------------|
| `read` | INFORMATION | Vis / åbn |
| `approve` | DECISION | Godkend |
| `reject` | DECISION | Afvis |
| `postpone` | DECISION | Udskyd |
| `send` | ACTION | Send til aktør |
| `create` | ACTION | Opret ressource |
| `search` | INFORMATION | Find |
| `switch_focus` | ACTION | Skift fokus |
| `explore` | DISCUSSION | Udforsk emne |
| `brainstorm` | DISCUSSION | Idégenerering |
| `clarify` | DISCUSSION | Afklar uklarhed |
| `brief` | INFORMATION | Briefing |
| `status` | INFORMATION | Statusforespørgsel |
| `report` | INFORMATION | Rapport |
| `agree` | ACTION | Accepter aftale |
| `promise` | ACTION | Forpligtelse |
| `task` | ACTION | Opret/fuldfør opgave |
| `build` | RELATION | Etabler relation |
| `maintain` | RELATION | Vedligehold relation |
| `close` | RELATION | Afslut relation |

Udvidelser via capability manifest per adapter. Nye actions skal deklarere default `category`.

### 3.4 Trust integration (v1.1)

`trust_level` og `trust_score` kommer fra Trust & Evidence Layer ([Cognitive Runtime §6.1](EIRA_Cognitive_Runtime_v1.0.md)).

| trust_level | trust_score | UX-adfærd |
|-------------|-------------|-----------|
| `unconfirmed` | 0–20 | `clarification_needed` — ingen execute |
| `indicative` | 21–50 | Vis kandidater, kræv bekræftelse |
| `probable` | 51–79 | Rationale + bekræft |
| `confirmed` | 80–95 | Kort bekræftelse |
| `indisputable` | 96–100 | Kan auto-foreslå (stadig ikke silent execute for DECISION) |

---

## 4. Parsing

| Mode | Teknologi | Confidence |
|------|-----------|------------|
| **Rule-based** (PRIMARY) | Regex + grammatik + category map | 0.6–0.85 |
| **LLM fallback** | Lokal model (Gemma 2B / Mistral) | 0.7–0.95 |
| **Structured API** | JSON intent direkte | 1.0 |

Under 0.6 confidence → `status: clarification_needed` (obligatorisk).

Category infereres fra action default map (§3.3) hvis ikke eksplicit angivet.

---

## 5. Policy integration

Før execute: Identity Spec leverer assurance; Governance leverer `step_up_rules`.

`DECISION` + `approve`/`reject` kræver typisk step-up — uændret fra v0.1.

Intent Protocol **emitter** Intent Audit events med category, action, trust_score, journey_id (se Identity Spec §5).

### 5.1 Audit event (udvidet)

```json
{
  "event_id": "uuid",
  "timestamp": "2026-07-03T09:00:00Z",
  "intent": {
    "category": "DECISION",
    "action": "approve",
    "confidence": 0.94,
    "trust_level": "probable",
    "trust_score": 71,
    "journey_id": "660e8400-e29b-41d4-a716-446655440001"
  }
}
```

---

## 6. Conformance

| Niveau | Krav |
|--------|------|
| **CORE** | Parse, action taxonomy, confidence threshold |
| **STANDARD** | + category taxonomy, execute via adapter, audit emission |
| **PREMIUM** | + trust_level, journey_id, multi-step plans, LLM fallback |

v0.1 CORE-implementeringer er **bagudkompatible** — `category` kan defaultes fra action map.

---

## 7. Reference implementation

`eira-intent-engine` (Rust) — EIRA OS Lag 12 (Intent Engine).

Phase 1 mockup: `eira-os/prototype/phase1/` (Python/FastAPI).

---

## 8. Changelog fra v0.1

| Ændring | Beskrivelse |
|---------|-------------|
| + `category` | Formålskategori (5 værdier) |
| + `trust_level`, `trust_score` | Trust & Evidence integration |
| + `journey_id` | Journey Orchestrator binding |
| + actions | `postpone`, discussion/relation/information-verb udvidet |
| = lifecycle | Category step efter parse |
| = audit | Udvidede intent-felter i events |

---

*EIRA Intent Protocol v1.1 — udvides i v1.2 med fuld grammatik og REST API*
