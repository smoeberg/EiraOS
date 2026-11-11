# EIRA OS — Situation UI Vision v0.1

**Status:** Produktvision — normativ retning (ikke pilot-scope)  
**Dato:** 4. juli 2026  
**Nordstjerne:** *EIRA er et operativsystem for opmærksomhed — ikke for apps, filer eller vinduer.*  
**Relateret:** [UX Logic](EIRA_User_Experience_Logic_v0.1.md), [UX Visual Language](EIRA_UX_Visual_Language_v0.1.md), [Prioritization Heuristics](EIRA_Prioritization_Heuristics_v0.1.md), [Identity Strategy §10](EIRA_Identity_Strategy_v0.2.md), [Object Graph v0.3](EIRA_Object_Graph_Specification_v0.3.md)

---

## 1. Evolution: GUI → Handling → Situation

| Æra | Brugeren åbner | Skærmen viser | EIRA-status |
|-----|----------------|---------------|-------------|
| **Klassisk OS** | Programmer | Desktop, vinduer, mapper | Det vi erstatter |
| **Handling UI** (nu → pilot) | Prioriterede handlinger | Hero + klynger + intent bar | Calm Command, phase1 |
| **Situation UI** (horisont 5–10 år) | Intet — systemet kender kontekst | **Situationen** du er i | Produktmål |

```
Programmer  →  Handlinger  →  Situationer
   (1980)        (2026)         (2030+)
```

**Definition — Situation:** Et sammensat øjeblik af *tilstand + tid + sted + kalender + fokus + sociale forventninger*, som EIRA har høj nok confidence til at navngive og foreslå næste skridt — uden menu.

Eksempel:

> Godmorgen Søren. Du er hjemme. Der er ro. Du har 2 timer inden næste møde.  
> Jeg foreslår: Fortsæt EIRA Runtime · Besvar EU-mail · Review af API

Ingen dashboard. Ingen desktop. **Kun situation.**

---

## 2. Opmærksomhed som first-class object

Skærmen viser ikke *hvad computeren kan* — den viser *hvad der fortjener brugerens fokus lige nu*.

Alt andet (programmer, dokumenter, API'er, mapper, vinduer) er **usynlig infrastruktur**.

| Koncep | Teknisk hjem i EIRA |
|--------|---------------------|
| Situation | `Tilstand` + `Fokus` + temporal + kalender + prioritizer |
| Fortjener fokus | [Prioritization Heuristics](EIRA_Prioritization_Heuristics_v0.1.md) hero-score |
| Forsvinder | Fokus-mode (§6) + ambient idle (§10) |
| Hvorfor | Reasoning Engine + relation evidence (§3) |
| Hukommelse | Agency + preference graph (§6) — ikke chat-log |

---

## 3. De 12 principper (normative)

### 3.1 Situation UI — systemet kender konteksten

**Princip:** Brugeren vælger ikke handlinger — EIRA navngiver situationen og foreslår 2–4 veje.

| Krav | Implementering |
|------|----------------|
| Situationstekst er conversational | Reasoning + Identity (hjemme/kontor) + kalender |
| Max 4 forslag | Samme som cluster-cap i prioritizer |
| Ingen menu som default | Explorer fullscreen; Builder er undtagelse |

**Fase:** Pilot = manuel `Tilstand`/`Fokus`; Horizon = auto-situation fra sensorer + kalender + mønster.

---

### 3.2 Levende GUI — personlighed skifter med dagen

**Princip:** Layout og *tone* ændrer sig — ikke kun indhold.

| Tid | Personlighed | UI-adfærd |
|-----|--------------|-------------|
| Morgen | Energi, orientering | Stor hero, "dagens vigtigste" |
| Eftermiddag | Flow, opfølgning | Kompakt, aktør-fokus ("Lars venter") |
| Sen aften | Beskyttelse | "Gemmer vi resten til i morgen?" |

**Fase:** v0.1 Visual Language = morgen-briefing; næste = `time_persona` i shell-theme.

---

### 3.3 Alt har "Hvorfor?" — ekstremt tydeligt

**Princip:** AI må aldrig virke magisk. Hver foreslået handling har foldbar **Hvorfor ser jeg dette?**

```
Fordi
• Lars sendte det kl. 10.14
• Deadline er i dag
• Du godkendte tilsvarende sidste måned
```

| Krav | Kilde |
|------|-------|
| Bullet-rationale | Reasoning Engine |
| Tidsstempler | Temporal graph + adapter events |
| Mønster-reference | Preference / digital twin (§12) |

**Fase:** Pilot = statisk rationale; STANDARD = evidens-link til Object Graph kanter.

---

### 3.4 Relationer visualiseres — levende kort, ikke mapper

**Princip:** Brugeren ser Object Graph som **træ/kort** omkring hero — ikke filstier.

```
Budget
├── Lars
├── Projekt Alpha
├── Kommune
└── Deadline
```

| Krav | Teknik |
|------|--------|
| Max dybde 2 i default view | Graph traversal med `min_confidence` |
| Kanter viser kilde | [Object Graph v0.3](EIRA_Object_Graph_Specification_v0.3.md) `evidence.source` |
| Tap = fold rationale | UX — ikke navigation væk |

**Fase:** Ikke i phase1 endnu — P1 UX-komponent `RelationTree`.

---

### 3.5 Fokus-mode — cockpit, ikke filter

**Princip:** Ved "Arbejd på Projekt X" **forsvinder** alt andet — ikke filtreres.

| Forsvinder | Mekanisme |
|------------|-----------|
| Støj-notifikationer | Policy + prioritizer hard gate |
| Irrelevante klynger | `focus_match` → score 0 |
| Telefon/mail (hvor muligt) | DND integration / OS-level (horizon) |

**Regel:** Exit fokus = én gestus eller intent ("Skift fokus") — aldrig fanget.

**Fase:** Pilot = soft fokus (genberegn liste); Horizon = hard cockpit med OS-integration.

---

### 3.6 GUI-hukommelse — muskelhukommelse, ikke chat

**Princip:** EIRA lærer **handlingspræference** per bruger — ikke samtalehistorik.

| Observeret | Effekt |
|------------|--------|
| Søren åbner altid dokument før godkend | Primær knap → "Åbn først" |
| Mette godkender direkte | Primær knap → "Godkend" |

| Lag | Ansvar |
|-----|--------|
| Preference store | Local-first, per `actor_id` |
| Identity | Hvem er preference bundet til |
| Ingen global model | Enterprise — data forbliver på device/tenant |

**Fase:** P2 efter pilot — kræver Agency audit trail.

---

### 3.7 Timeline i stedet for filer

**Princip:** Ingen dokumentliste. Historien er **events** på objektet.

```
Budget → Lars oprettede → Anna rettede → Du kommenterede → Godkendt → Sendt
```

| Krav | Teknik |
|------|--------|
| Events er append-only | Intent Audit + adapter webhooks |
| Objekt = ankker | Object Graph node |
| Filer er implementation detail | Adapters — aldrig vist i Explorer |

**Fase:** P1 for hero-objekt; fuld timeline P2.

---

### 3.8 GUI der tør være tom

**Princip:** Når intet fortjener opmærksomhed:

> Alt er klaret. Nyd kaffen.

**Forbudt:** `0 notifikationer · 0 mails · 0 tasks` — det er inbox-sprog.

| Tilstand | UI |
|----------|-----|
| `hero == null` && clusters tom | Empty state — ro, ikke statistik |
| Ambient mode | §3.10 |

**Fase:** Calm Command kan implementere nu — prioritizer returnerer empty hero.

---

### 3.9 AI viser usikkerhed — aldrig falsk selvsikkerhed

**Princip:** Ved tvivl — vis valg, ikke én knap.

```
Jeg tror dette er den rigtige kontrakt.
• Navnet matcher · Projekt matcher
Men: Der findes to versioner.
[Vælg A] [Vælg B]
```

| Gate | Regel |
|------|-------|
| `confidence < 0.7` | Ingen single-hero — klynge "Kræver valg" |
| `evidence.verified == false` | "Vis først" fremhævet |
| Object Graph | To kanter med lignende score → disambiguation UI |

Aligner med [Prioritization Heuristics](EIRA_Prioritization_Heuristics_v0.1.md) trust gates.

---

### 3.10 Ambient computing — skærmen behøver ikke fylde

**Princip:** Når intet sker — minimal tilstedeværelse.

```
──────────────────────
EIRA
Alt er under kontrol.
──────────────────────
```

Ingen widgets. Ingen dashboard. **Ro som default.**

**Fase:** Horizon — kræver shell idle state + hardware presence (optional).

---

### 3.11 Intent Canvas — EIRAs signatur

**Princip:** Intent-input er ikke et søgefelt — det er et **lærred** der udfolder planen.

```
Planlæg møde → Hvem? → Lars → Hvornår? → Onsdag → Book lokale? → Ja
```

| Krav | Teknik |
|------|--------|
| Slot-filling visuelt | Intent Engine partial parse |
| Hvert led bekræftes | Journey micro-flow |
| Ikke chatbobler | Canvas-noder (Visual Language v2) |

**Fase:** P1 efter hero+klynger stabilt — erstatter nederste intent-bar i v2.

---

### 3.12 Digital tvilling — arbejdsmønster, ikke regel

**Princip:** Efter måneder kan EIRA sige:

> "Hvis du var logget ind nu, ville du sandsynligvis starte med budgettet, så svare Lars, så Runtime-spec. Skal jeg gøre det klar?"

| Krav | Begrænsning |
|------|-------------|
| Baseret på **observerede sequences** | Ikke hardcoded rules |
| Local-first / tenant-bound | GDPR — ingen cloud twin uden DPA |
| Forklarbar | "Baseret på dine sidste 14 tirsdage" |
| Bruger kan slå fra | Policy + indstilling |

**Fase:** Horizon — kræver Agency history + preference model.

---

## 4. Arkitektur-kobling (ikke kun design)

```
                    Identity
                        │
         Situation = f(tilstand, tid, sted, fokus)
                        │
        ┌───────────────┼───────────────┐
        │               │               │
   Object Graph    Prioritizer       Preferences
   (relationer +   (hero/klynger)    (muskelhukommelse)
    evidence)
        │               │               │
        └───────────────┼───────────────┘
                        │
              Reasoning ("Hvorfor?")
                        │
              Situation UI / Canvas
```

**Vigtigt:** Situation UI virker kun hvis Identity + Graph evidence + Prioritizer er solide. AI alene giver chatbot.

---

## 5. Faseplan (realistisk)

| Fase | Horizon | Leverancer | Principper dækket |
|------|---------|------------|-------------------|
| **0** Pilot | Nu | Calm Command, hero, klynger, Hvorfor (basic), fokus soft | 3, 8, 9 (delvist) |
| **1** | 6–12 mdr | RelationTree, timeline på hero, Hvorfor fold, fokus hard | 3, 4, 5, 7 |
| **2** | 12–24 mdr | Levende persona, preference knapper, Intent Canvas v1 | 2, 6, 11 |
| **3** | 3–5 år | Auto-situation, ambient idle, twin (local) | 1, 10, 12 |
| **4** | 5–10 år | Fuld Situation UI — menu dør | 1, 10 |

---

## 6. Guardrails (enterprise)

| Risiko | Modgift |
|--------|---------|
| Auto-situation føles overvågende | Transparent "hvorfor denne situation"; slå fra |
| Fokus-mode skjuler kritisk alert | Policy override — sikkerhed > fokus |
| Twin er forkert | Altid confirm; lær kun fra explicit feedback |
| Tom skærm skjuler SLA-brud | IT alerts bypasser ambient via Governance |
| Builder/IT skal se logs | Builder Mode uændret |

---

## 7. Forhold til eksisterende specs

| Eksisterende | Situation UI udvider |
|--------------|---------------------|
| UX Logic §2 Opmærksomhedskæde | Kæden bliver **situation** som output |
| Calm Command | Fase 0 — ikke slutmål |
| Trust layer | Understøtter §3.3 og §3.9 |
| Object Graph v0.3 | Understøtter §3.4 og §3.7 |
| Identity §10 | Understøtter §3.1 og §3.6 |

---

## 8. Én sætning til produkt og investorer

> **Windows organiserer apps. EIRA organiserer opmærksomhed. Situation UI er øjeblikket hvor det bliver synligt for brugeren.**

---

## Relaterede dokumenter

| Dokument | Link |
|----------|------|
| UX Logic | [EIRA_User_Experience_Logic_v0.1.md](EIRA_User_Experience_Logic_v0.1.md) |
| Visual Language (fase 0) | [EIRA_UX_Visual_Language_v0.1.md](EIRA_UX_Visual_Language_v0.1.md) |
| Document Map | [EIRA_Document_Map_v0.1.md](../EIRA_Document_Map_v0.1.md) |

---

*EIRA Situation UI Vision v0.1*
