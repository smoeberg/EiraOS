# EIRA Risk & Sprint 0�1 Focus v0.1

**Status:** Aktiv risikostyring  
**Dato:** 26. juni 2026  
**Horisont:** Sprint 0 (uge 0�4) � Sprint 1 (uge 5�8)

---

## 1. Executive summary

Fundamentet (Open Architecture, Identity Spec, Lag 0 Governance) er solidt. To risici kan stadig stoppe projektet f�r pilot:

| # | Risiko | Type | Sprint |
|---|--------|------|--------|
| **R1** | Adapter-adoption � leverand�rer bygger ikke | Marked / politisk | 0�1 |
| **R2** | Intent parsing confidence � maskinen g�tter forkert | Teknisk / UX | 1 |

**Make-or-break i Sprint 1:** Rationale Extraction PoC (del af R2).

---

## 2. Risiko R1 � Adapter-adoption

### 2.1 Problem

EIRA Adapter Specification er teknisk korrekt, men **v�rdien realiseres f�rst n�r kildesystemer er koblet**. Uden adaptere er EIRA OS et smart desktop uden data.

```
Uden leverand�r-adaptere:
  EIRA bygger N adaptere ? umuligt at skalere

Med standard + udbud:
  Hver leverand�r bygger 1 ? muligt
```

**Afh�ngighed:** KMD, Visma, TietoEvry, Microsoft (SharePoint) m.fl. skal have incitament og deadline.

### 2.2 Hvorfor det er h�rdt

| Barriere | Realitet |
|----------|----------|
| Leverand�r-prioritet | Adapter er cost center � ikke revenue |
| Ingen installerede EIRA-kunder endnu | H�nen og �gget |
| Udbud tager 12�24 m�neder | For langsomt til Sprint 1 |
| Politisk kapital | KL/KOMBIT kr�ver reference + ministeriel/interkommunal opbakning |

### 2.3 Mitigation � Sprint 0

| Aktivitet | Output | Ejer |
|-----------|--------|------|
| **EIRA bygger 2 reference-adaptere** | SharePoint (Entra) + �n kommunal (Public360 *eller* fil-share) | Tech |
| **Adapter Test Suite v1.0** | Leverand�r kan certificere lokalt | Tech |
| **Udbudstekst-kladder** | "EIRA Adapter STANDARD jf. spec v1.0" � copy-paste til indk�b | Legal/Sales |
| **1:1 med KOMBIT/KL** | Forst�else af f�llesindk�b-timeline � ikke commitment endnu | Sales |
| **Adapter SDK + docs** | `github.com/eira-os/adapter-sdk` � minimerer leverand�rindsats | Tech |

**Princip Sprint 0:** *Vis v�rdi uden at vente p� leverand�rer.* EIRA ejer de f�rste 2 adaptere.

### 2.4 Mitigation � Sprint 1

| Aktivitet | Output |
|-----------|--------|
| **Pilot-kommune v�lger 2 systemer** | De systemer de allerede hader at skifte mellem |
| **Letter of intent fra 1 leverand�r** | Ikke kontrakt � vilje til test-adapter |
| **Capability manifest demo** | Vis at Public360 *kunne* eksponere STANDARD p� 2 uger |
| **Hybrid-narrativ** | "EIRA samler � erstatter ikke. Adapter er jeres API-wrapper." |

### 2.5 Politisk spor (parallel, ikke Sprint 1-bloker)

```
Fase A: Pilot-reference (50 PC, 1 kommune)          ? Sprint 1�3
Fase B: KL Sikkerhedsprogram / minimumskrav-align    ? M�ned 6+
Fase C: KOMBIT f�llesindk�b med adapter-krav       ? M�ned 12+
Fase D: Leverand�r-benchmark ("KMD har EIRA Adapter") ? M�ned 18+
```

**Sprint 0�1 krav:** Politisk spor **startes** (m�der, tekst) � ikke **l�ses**.

### 2.6 Go / no-go kriterier (adapter)

| Metrik | Sprint 1 go | Red flag |
|--------|-------------|----------|
| Reference-adaptere i drift | ? 2 | 0 |
| Pilot-kommune systemer d�kket | ? 80% af daglige opgaver | < 50% |
| Leverand�r-dialog | ? 2 m�der booket | Ingen respons |
| Udbudstekst | Kladde reviewed af jurist | Ingen tekst |

### 2.7 R1 opdeling � demo vs. eksistentiel (v0.1 opdatering)

External review: reference-adaptere l�ser demo, ikke skalering. Se [EIRA_Strategic_Reality_Check_v0.1.md](EIRA_Strategic_Reality_Check_v0.1.md).

| | R1a (pilot) | R1b (marked) |
|---|-------------|--------------|
| Horisont | Sprint 0�1 | 2�3 �r |
| L�sning | EIRA ejer adaptere til pilot-systemer | Wedges + politik + evt. betalt integration |
| Indt�gt | Pilot-commitment | M� ikke v�re eneste vej til m�ned 6 |

**Wedges (R1b):** M365-first pilot � Intent Audit/Fleet standalone � EIRA som betalt integrator.

--- � Intent parsing confidence

### 3.1 Problem

EIRA's l�fte er **opm�rksomhedscentrisk computing** � brugeren beskriver intention, systemet finder vej.

Hvis maskinen g�tter forkert for ofte:

- Brugeren mister tillid ? tilbage til SharePoint/Public360 manuelt
- **Oplevelseslaget kollapser** (Pr�sentation + Intent � ikke IT's Governance Lag 0)
- "Lag 0" i brugerens forstand = **attention/fokus** � ikke Management Plane

```
Forkert intention:
  "Godkend budget" ? forkert fil ? bruger retter ? retter igen ? opgiver
```

### 3.2 Make-or-break: Rationale Extraction PoC (Sprint 1)

**M�l:** Bevise at systemet kan forklare *hvorfor* det foresl�r en handling � og stoppe f�r fejl.

| Uden rationale | Med rationale |
|--------------|---------------|
| "Send budget?" [Ja] | "Send budget_2026.docx til Lars � fordi sag 2024-15, 94% match" [Ja] [V�lg anden] |
| Bruger blindt klikker | Bruger informeret consent |
| Fejl = katastrofe | Fejl = korrektion uden skade |

**Rationale Extraction** er UX regel 5 ("Forklar hvorfor") + teknisk confidence gate kombineret.

### 3.3 Arkitektur for confidence (Sprint 1)

```
Input
  ? Rule parser (PRIMARY)     confidence 0.6�0.85
  ? LLM fallback (SECONDARY)  confidence 0.7�0.95
  ? Entity resolution (graph) justerer �0.1
        ?
Confidence bands:
  ? 0.85  ? Foresl� handling + rationale (auto-present)
  0.60�0.84 ? Foresl� + tving valg (clarification UI)
  < 0.60  ? Sp�rg � udf�r ALDRIG silent
        ?
Rationale object (obligatorisk ved ? 0.60):
  - matched_entities + scores
  - policy_context (fokus, rolle)
  - alternative_candidates (min 1)
  - human_readable_why
```

### 3.4 Sprint 1 PoC � testprotokol

**Datas�t:** 50 reelle intentioner fra pilot-kommune (anonymiseret).

| Intentionstype | Antal | Eksempel |
|----------------|-------|----------|
| Godkend | 10 | "Godkend budget" |
| �bn / vis | 15 | "�bn sagen om skolebyggeri" |
| Send | 10 | "Send til Lars" |
| S�g | 15 | "Find referat fra sidste m�de" |

**Succeskriterier:**

| Metrik | M�l | Kill threshold |
|--------|-----|----------------|
| Top-1 entity resolution korrekt | ? 85% | < 70% |
| Korrekt action type | ? 90% | < 75% |
| Bruger rettede (i test) | ? 15% | > 30% |
| Silent wrong execution | **0** | **? 1** |
| Rationale forst�et (brugertest, n=10) | ? 8/10 | < 6/10 |
| P95 latency (rule path) | < 500ms | > 2s |

**Kill criterion:** �n silent wrong execution i PoC ? stop feature rollout; rule-only mode indtil fix.

### 3.5 Mitigation � rule-first strategi

| Beslutning | Begrundelse |
|------------|-------------|
| **Regelbaseret PRIMARY** | Deterministisk, auditerbar, fungerer offline |
| **LLM kun ved h�j confidence eller explicit fallback** | Reducerer hallucination-risiko |
| **Aldrig execute under 0.60** | Fail safe |
| **Bruger-rettelse ? graph learning** | Systemet l�rer � men ikke silent |
| **Intent Audit logger rationale** | CISO kan se *hvorfor* fejl skete |

### 3.6 Hvad vi IKKE beviser i Sprint 1

- Fuld naturligt sprog for alle edge cases
- Multi-step flows ("godkend og send til borgmester")
- Stemmeinput
- LLM uden lokal model

**Sprint 1 scope:** 5�7 action-typer, rule-dominant, rationale obligatorisk.

---

## 4. Sprint 0�1 plan (konsolideret)

### Sprint 0 (uge 0�4)

| Track | Leverance |
|-------|-----------|
| **Adapter** | Adapter SDK skeleton; SharePoint adapter started; udbudstekst kladde |
| **Identity** | Entra OIDC PoC; audit schema implementeret |
| **Intent** | Rule parser for 5 actions; confidence bands; rationale schema |
| **Governance** | Policy YAML parser; governance-agent stub |
| **Politik** | KL/KOMBIT intro-m�de booket |

### Sprint 1 (uge 5�8)

| Track | Leverance |
|-------|-----------|
| **Adapter** | 2 reference-adaptere i demo; Test Suite v1.0 |
| **Intent** | **Rationale Extraction PoC** � 50-intention evaluering |
| **Identity** | Step-up mock (Entra ? blocked ? UI) |
| **Pilot** | 1 kommune committed; intentioner indsamlet til testdatas�t |
| **Go/no-go** | PoC-rapport + adapter demo til IT-chef |

---

## 5. Risiko-matrix (opdateret)

| Risiko | Sandsynlighed | Impact | Mitigation status |
|--------|---------------|--------|-------------------|
| R1 Adapter-adoption | H�j | Kritisk | Sprint 0: EIRA ejer 2 adaptere |
| R2 Intent confidence | Medium | Kritisk | Sprint 1: Rationale PoC + kill criteria |
| Leverand�r passivitet | H�j | H�j | Parallel politisk spor |
| Linux-kompetence i kommune | Medium | Medium | Managed EIRA PC + premium support |
| NIS2 dokumentation | Lav | Medium | Compliance engine design (Lag 0) |

---

## 6. Beslutninger der skal tr�ffes i Sprint 0

| # | Beslutning | Deadline |
|---|------------|----------|
| 1 | Hvilke 2 reference-adaptere? (SharePoint + ?) | Uge 1 |
| 2 | Pilot-kommune kandidat (navn) | Uge 2 |
| 3 | Rule-only vs LLM i Sprint 1 demo | Uge 2 |
| 4 | Confidence kill threshold (0.60 confirm) | Uge 3 |
| 5 | KL/KOMBIT kontaktperson | Uge 4 |

---

## 7. Relaterede dokumenter

- [EIRA_Strategic_Reality_Check_v0.1.md](EIRA_Strategic_Reality_Check_v0.1.md) — R1a/R1b, hybrid vs. paritet, blindvinkler

- EIRA_Open_Architecture_v1.0.md
- EIRA_Intent_Protocol_v0.1.md
- EIRA_Adapter_Specification_v1.0.docx
- EIRA_OS_Architecture_Overview_v1.0.md (Intent Audit)

---

## Relaterede dokumenter (operationalisering)

| Spørgsmål | Dokument |
|-----------|----------|
| Hybrid, R1a/R1b, blindvinkler | [Strategic Reality Check](EIRA_Strategic_Reality_Check_v0.1.md) |
| Pilot go/no-go | [Pilot Validation Plan](EIRA_Pilot_Validation_Plan_v0.1.md) |
| Rollback | [BCP Endpoint Fallback](EIRA_BCP_Endpoint_Fallback_v0.1.md) |
| Tailwinds/headwinds | [Success/Failure Matrix](EIRA_Success_Failure_Matrix_v0.1.md) |
| Navigation | [Document Map](../EIRA_Document_Map_v0.1.md) |

---

*EIRA Risk & Sprint 0�1 Focus v0.1*
