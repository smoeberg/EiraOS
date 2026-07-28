# EIRA OS — Prioriteringsheuristik v0.1

**Status:** Normativ — Explorer og Cognitive Agent  
**Dato:** 4. juli 2026  
**Relateret:** [UX Logic](EIRA_User_Experience_Logic_v0.1.md) regel 4, [UX Visual Language](EIRA_UX_Visual_Language_v0.1.md)

---

## 1. Formål

Bestem **én hero-handling** og **foldede klynger** når volumen > 1. Uden heuristik bliver UI et inbox-feed (1:1 kort per hændelse).

**Regel:** *Én ting skriger. Resten hvisker.*

---

## 2. Input og output

### Input (fra agent / adapter-events)

| Felt | Type | Eksempel |
|------|------|----------|
| `item_id` | string | `trust-042` |
| `kind` | enum | `approval`, `followup`, `mail`, `journey_step`, `alert` |
| `title` | string | Budget 2026 afventer godkendelse |
| `focus_tags` | string[] | `Kommunepilot`, `Budget 2026` |
| `deadline_at` | ISO \| null | 2026-07-04T17:00:00+02:00 |
| `trust_score` | 0–100 | 91 |
| `trust_level` | band | confirmed |
| `requires_actor` | bool | true = bruger skal handle |
| `blocked` | bool | policy eller adapter nede |
| `created_at` | ISO | |

### Output

```json
{
  "hero": { "item_id": "...", "score": 87.2, "prompt": "Skal jeg godkende budgettet for Kommunepilot?" },
  "clusters": [
    { "kind": "approval", "label": "2 godkendelser", "hint": "2 kræver svar", "item_ids": ["a","b"], "expanded": false },
    { "kind": "followup", "label": "8 opfølgninger", "hint": "1 forsinket", "item_ids": ["..."], "expanded": false }
  ],
  "folded_count": 12
}
```

---

## 3. Scoringsmodel (hero)

```
score = w_deadline × deadline_urgency
      + w_focus × focus_match
      + w_action × action_required
      + w_trust × trust_gate
      − w_noise × informational_only
```

| Faktor | Vægt | Beregning |
|--------|------|-----------|
| `deadline_urgency` | 40 | 0 ingen frist; 50 i dag; 80 <4t; 100 overskredet |
| `focus_match` | 25 | 1.0 hvis tag matcher aktivt fokus; 0.3 ellers |
| `action_required` | 25 | 1.0 hvis `requires_actor`; 0.2 hvis kun informativ |
| `trust_gate` | 10 | 0 hvis `unconfirmed` uden bekræftelsesflow; 1.0 ellers |
| `informational_only` | −15 | 1.0 hvis `indisputable` og ikke `requires_actor` |

**Hero** = højeste `score` hvor `blocked = false`. Ved uafgjort: tidligste `deadline_at`, derefter `created_at`.

**Tie-break:** Samme `kind` som gårsdagens hero nedprioriteres 10% (undgå stagnation).

---

## 4. Klynger (resten)

1. Ekskluder hero-`item_id`.
2. Gruppér efter `kind`.
3. Sorter klynger efter max(score) i gruppen.
4. Max **4 synlige klynger** + én "X ting mere" hvis rest > 0.
5. Inden for klynge: sorter efter score desc; vis max **3 rækker** når foldet, alle når åbnet.

### Klynge-labels (dansk)

| kind | Label skabelon | hint ved urgency |
|------|----------------|------------------|
| approval | `{n} godkendelser` | `{m} kræver svar` hvis requires_actor |
| followup | `{n} opfølgninger` | `{m} forsinket` hvis deadline passeret |
| mail | `{n} mails` | `intet presserende` hvis max score < 30 |
| alert | `{n} advarsler` | kun hvis score ≥ 50 |
| journey_step | fold ind i `followup` | |

---

## 5. Tillids-gates (ingen silent execute)

| trust_level | UI-adfærd |
|-------------|-----------|
| `indisputable` / `confirmed` | Hero + direkte bekræftelsesflow |
| `probable` | Hero med "Vis først" fremhævet |
| `indicative` | Ikke hero — kun i klynge med advarsel |
| `unconfirmed` | Aldrig hero — klynge "Kræver afklaring" |

---

## 6. Conversational prompt (hero)

Systemet omskriver `title` til **spørgsmål**:

| kind | Skabelon |
|------|----------|
| approval | Skal jeg godkende {kort_titel}? |
| followup | Skal jeg følge op på {kort_titel}? |
| mail | Skal jeg svare på {afsender eller emne}? |
| alert | Skal vi kigge på {kort_titel}? |

`kort_titel` = max 6 ord, ingen systemnavne.

---

## 7. Refresh og stabilitet

| Event | Adfærd |
|-------|----------|
| Ny høj-score item | Hero skifter med 300ms cross-fade; ikke instant hop |
| Bruger udskyder hero | Nedprioriter 24t; næste i kø |
| Fokus skifter | Genberegn alle scores; hero må skifte |
| Adapter nede | Item `blocked`; vis i klynge med grå status |

**Anti-flap:** Hero skifter ikke oftere end 1× per 60 sek medmindre ny score > gammel + 20.

---

## 8. Reference-implementering

| Lag | Placering |
|-----|-----------|
| Normativ | Dette dokument |
| Agent (prod) | `eira-reasoning` / prioritizer modul (TBD) |
| Prototype | `prototype/phase1/ui/src/prioritize.ts` |

---

## 9. Acceptkriterier (pilot)

| # | Kriterie |
|---|----------|
| P1 | Ved 20+ items vises præcis 1 hero + ≤4 klynger |
| P2 | Hero skifter ikke ved scroll eller expand |
| P3 | `unconfirmed` optræder aldrig som hero |
| P4 | Udskyd holder item væk 24t (local policy) |
| P5 | Fokus-skift genberegner på < 200ms (client) |

---

## Relaterede dokumenter

| Spørgsmål | Dokument |
|-----------|----------|
| UX-regler | [UX Logic](EIRA_User_Experience_Logic_v0.1.md) |
| Visuelt udtryk | [UX Visual Language](EIRA_UX_Visual_Language_v0.1.md) |
| Performance | [Performance Acceptance](EIRA_Performance_Acceptance_v0.1.md) |
| Navigation | [Document Map](../EIRA_Document_Map_v0.1.md) |

---

*EIRA Prioritization Heuristics v0.1*
