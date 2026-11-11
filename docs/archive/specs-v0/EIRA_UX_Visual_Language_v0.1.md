# EIRA OS — UX Visual Language v0.1

**Status:** Normativ — Explorer (eira-shell)  
**Dato:** 4. juli 2026  
**Kodename:** Calm Command (fase 0 — handling UI)  
**Horisont:** [Situation UI Vision](EIRA_Situation_UI_Vision_v0.1.md) — operativsystem for opmærksomhed  
**Relateret:** [UX Logic](EIRA_User_Experience_Logic_v0.1.md), [Prioritization Heuristics](EIRA_Prioritization_Heuristics_v0.1.md), [Desktop Architecture](EIRA_Desktop_Architecture_v1.0.md)

---

## 1. Design-intention

> **Morgenbriefing fra en rolig, skarp kollega — ikke et admin-panel.**

| Vi er | Vi er ikke |
|-------|------------|
| Typografi-først | Kasse-på-kasse cards |
| Ét fokuspunkt | Inbox med badges |
| Menneskeligt sprog | System-beskeder |
| Blød, varm mørk | Kold corporate navy |
| Tillid gennem klarhed | Tillid som procent-dashboard |

---

## 2. Layout-principper

```text
┌──────────────────────────────────────┐
│  EIRA          Arbejde · Fokus       │  ← minimal topbar
├──────────────────────────────────────┤
│                                      │
│  Hej {navn}                          │  ← stor luft
│  {dato} · {fokus}                    │
│                                      │
│  {conversational hero spørgsmål}     │  ← INGEN card-border
│  {1 linje kontekst}                  │
│  {tillids-linje — ikke %}            │
│                                      │
│      [ Primær handling ]             │  ← 80% af beslutningen
│        Se først    Ikke nu           │
│                                      │
│  2 godkendelser · 2 kræver svar   ›  │  ← klynge-rækker
│  8 opfølgninger                   ›  │
│                                      │
│  {forløb — kompakt, uden pills}      │
│                                      │
╰──────────────────────────────────────╯
│  ⌘  Hvad vil du opnå?                │  ← glass intent bar
╰──────────────────────────────────────╯
```

**Max bredde:** 640px. **Padding:** generøs (24–32px sider, 48px mellem sektioner).

---

## 3. Farver (varm mørk)

| Token | Hex | Brug |
|-------|-----|------|
| `--bg` | `#131210` | Baggrund |
| `--bg-elevated` | `#1c1a17` | Intent bar, sheets |
| `--text` | `#f5f2eb` | Primær tekst |
| `--text-muted` | `#9a948a` | Sekundær |
| `--text-faint` | `#6b6560` | Tertiær |
| `--accent` | `#5b8def` | Primær handling |
| `--accent-soft` | `rgba(91,141,239,0.15)` | Hover/focus |
| `--trust` | `#7ec9a0` | Verificeret (sparsomt) |
| `--urgent` | `#d4a054` | Deadline — max 1 per skærm |
| `--border` | `rgba(255,255,255,0.06)` | Subtile skillelinjer |

**Forbudt:** Venstre accent-striber, ALL CAPS sektionsoverskrifter, gul alarmtekst overalt.

---

## 4. Typografi

| Element | Størrelse | Vægt | Bemærkning |
|---------|-----------|------|------------|
| Hero-spørgsmål | 1.625–1.75rem | 500 | `letter-spacing: -0.02em` |
| Hilsen | 1.5rem | 500 | Fornavn kun |
| Klynge-række | 0.9375rem | 400 | Én linje |
| Kontekst | 0.875rem | 400 | muted |
| Intent placeholder | 1rem | 400 | |

**Font-stack (prototype):** `"Plus Jakarta Sans", system-ui, sans-serif`  
**Produktion:** Geist eller system UI — samme metrics.

---

## 5. Komponenter

### 5.1 Hero (ingen card)

- Conversational prompt fra [Prioritization Heuristics](EIRA_Prioritization_Heuristics_v0.1.md) §6.
- Kontekstlinje: relationer som løbende tekst — `Budget 2026 · Sag 2024-15 · Økonomikontoret`.
- Tillidslinje: `Kilde verificeret · 2 har set det` — **ikke** "Tillid: 91%".

### 5.2 Primær knap

- Fuld bredde, `border-radius: 14px`, højde ~52px.
- Blød gradient `#5b8def` → `#4a7ad9`.
- Subtil `box-shadow` ved hover — ikke flat Material.

### 5.3 Sekundære handlinger

- Tekst-links under primær knap — ikke konkurrerende knapper.
- `Se det først` · `Ikke nu`

### 5.4 Bekræftelses-sheet

- `backdrop-filter: blur(12px)` over indhold — hero synlig bagved.
- Sheet ind fra bund eller fade — ikke erstat hele skærmen.
- Tekst: *"Jeg vil godkende … Kilden er verificeret."*
- Step-up: *"Kræver MitID Erhverv i næste trin."* — amber, én linje.
- Knapper: `Fortsæt` (primær) · `Vælg andet` · `Annuller`

### 5.5 Klynger

- Én `<button>` per klynge — hele rækken klikbar.
- Chevron `›` højre — ikke "Åbn/Luk" tekst.
- Expand: indre rækker uden card — `border-top` separator.
- Max 3 inline handlinger i foldet klynge.

### 5.6 Forløb (journeys)

- Ingen workflow-pills i v0.1 visual language.
- Format: `{titel}` + tynd progress-bar + `Trin 2 af 5 — Gennemgå`
- Afslut-trin: diskret tekstknap.

### 5.7 Intent bar

- Fast bund, glass (`bg-elevated` + blur).
- Afrundet `border-radius: 16px` inde i bar.
- `⌘` eller EIRA-mark som hint — ikke chat-avatar.
- Ingen "Plan"-knap synlig — Enter udfører.

---

## 6. Motion

| Element | Varighed | Easing |
|---------|----------|--------|
| Hero ind | 300ms | ease-out |
| Klynge expand | 250ms | spring-ish |
| Sheet ind | 350ms | ease-out |
| Hero skift | 300ms cross-fade | |

**Ingen** animation på lists scroll. Respekter `prefers-reduced-motion`.

---

## 7. Tillid — visuelt sprog

| Band | Visning |
|------|---------|
| confirmed+ | Grøn prik + "Kilde verificeret" |
| probable | "Baseret på {kilde} — vil du se først?" |
| indicative | Kun i klynge |
| unconfirmed | "Kræver afklaring" — aldrig hero |

---

## 8. Anti-patterns (afvis i review)

- [ ] ALL CAPS labels
- [ ] Venstre farvestribe på cards
- [ ] Flere end 2 farvede accents på én skærm
- [ ] Tillid som stor procent
- [ ] Document-ikoner i klynger
- [ ] Outline "Godkend" i lister
- [ ] Chatbobler / avatar

---

## 9. Reference-implementering

| Artefakt | Sti |
|----------|-----|
| Prototype UI | `prototype/phase1/ui/src/App.tsx` |
| Styles | `prototype/phase1/ui/src/index.css` |
| Prioritering | `prototype/phase1/ui/src/prioritize.ts` |
| Replit reference (ældre stil) | ekstern — erstattes af phase1 v2 |

---

## Relaterede dokumenter

| Spørgsmål | Dokument |
|-----------|----------|
| Brugerlogik | [UX Logic](EIRA_User_Experience_Logic_v0.1.md) |
| Prioritering | [Prioritization Heuristics](EIRA_Prioritization_Heuristics_v0.1.md) |
| IPC / shell | [Desktop Architecture](EIRA_Desktop_Architecture_v1.0.md) |
| Navigation | [Document Map](../EIRA_Document_Map_v0.1.md) |

---

*EIRA UX Visual Language v0.1 — Calm Command*
