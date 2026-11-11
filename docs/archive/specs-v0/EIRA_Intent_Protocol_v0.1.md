# EIRA Intent Protocol v0.1

**Status:** Officiel specifikation (EIRA Open Architecture)  
**Dato:** 26. juni 2026  
**Relateret:** EIRA OS Whitepaper kap. 7, EIRA Identity Specification v0.1

---

## 1. Scope

Definerer hvordan **brugerintentioner** udtrykkes, parses, valideres mod policy og eksekveres � uafh�ngigt af UI (Explorer Mode, API, stemme).

**Sp�rgsm�l:** *Hvad �nsker brugeren at opn�?*

---

## 2. Intent lifecycle

```
Input (natural language / structured)
  ? Parse (rules + optional LLM)
  ? Resolve (Object Graph lookup)
  ? Authorize (Identity: assurance + delegation)
  ? Plan (Capability + Adapter selection)
  ? Execute (Adapter call)
  ? Audit (Intent Audit event)
  ? Present result (UX)
```

---

## 3. Intent structure (normative)

```json
{
  "intent_id": "uuid",
  "raw_input": "Godkend budget",
  "action": "approve",
  "confidence": 0.94,
  "entities": [
    { "type": "document", "id": "budget_2026.docx", "score": 0.95 }
  ],
  "context": {
    "focus": "Kommunepilot",
    "state": "Arbejde"
  },
  "required_assurance": "org_acting",
  "status": "pending_confirmation"
}
```

### 3.1 Action taxonomy (CORE)

| Action | Beskrivelse |
|--------|-------------|
| `read` | Vis / �bn |
| `approve` | Godkend |
| `reject` | Afvis |
| `send` | Send til akt�r |
| `create` | Opret ressource |
| `search` | Find |
| `switch_focus` | Skift fokus |

Udvidelser via capability manifest per adapter.

---

## 4. Parsing

| Mode | Teknologi | Confidence |
|------|-----------|------------|
| **Rule-based** (PRIMARY) | Regex + grammatik | 0.6�0.85 |
| **LLM fallback** | Lokal model (Gemma 2B) | 0.7�0.95 |
| **Structured API** | JSON intent direkte | 1.0 |

Under 0.6 confidence ? clarification UI (obligatorisk).

---

## 5. Policy integration

F�r execute: Identity Spec leverer assurance; Governance leverer `step_up_rules`.

Intent Protocol **emitter** Intent Audit events med Who/When/Policy/Outcome (se Identity Spec �5).

---

## 6. Conformance

| Niveau | Krav |
|--------|------|
| **CORE** | Parse, action taxonomy, confidence threshold |
| **STANDARD** | + Execute via adapter, audit emission |
| **PREMIUM** | + Multi-step plans, LLM fallback, learning |

---

## 7. Reference implementation

`eira-intent-engine` (Rust) � EIRA OS Lag 4.

---

*EIRA Intent Protocol v0.1 � udvides i v0.2 med fuld grammatik og API*
