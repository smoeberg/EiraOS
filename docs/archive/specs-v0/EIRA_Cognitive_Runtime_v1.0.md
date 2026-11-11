# EIRA Cognitive Runtime v1.0

**Status:** Gældende — runtime-evolution (v7)  
**Dato:** 3. juli 2026  
**Projekt:** EIRA OS  
**Relateret:**
- [EIRA Platform Principles v1.0](EIRA_Platform_Principles_v1.0.md)
- [EIRA OS Architecture Overview v1.0](EIRA_OS_Architecture_Overview_v1.0.md)
- [EIRA Open Architecture v1.0](EIRA_Open_Architecture_v1.0.md)
- [EIRA User Experience Logic v0.1](EIRA_User_Experience_Logic_v0.1.md)
- [EIRA Technical Blueprint v7.0](EIRA_Technical_Blueprint_v7.0.md) *(kort reference)*

---

## 1. Strategisk position

EIRA er en **enterprise-platform bygget på Ubuntu LTS**.

Version 7 udvikler **runtime-laget** til en **Cognitive Runtime Stack** — med trust-aware interfaces, reasoning, journeys og enterprise intelligence — uden at ændre Ubuntu-fundamentet eller Governance-planen.

> **Ubuntu remains the operating system. EIRA evolves the enterprise runtime.**

> EIRA erstatter ikke Linux. EIRA gør Linux **brugbar for vidensarbejdere og administrérbart for IT.**

**EIRA må ikke opføre sig som et nyt operativsystem.** v7 styrker laget oven på Ubuntu — det omdefinerer ikke hele produktet.

---

## 2. Fuld arkitektur (fire planer)

```
┌─────────────────────────────────────────────────────────┐
│  Governance Plane (uændret)                             │
│  Fleet · Policies · Compliance · Intent Audit · Portal  │
└──────────────────────────┬──────────────────────────────┘
                           │ policies ↑ audit
┌──────────────────────────▼──────────────────────────────┐
│  EIRA Cognitive Runtime (v7 — dette dokument)         │
│  Presentation · Reasoning · Intent · Journey · Trust  │
│  Graphs · Capability · Adapters · Identity · Storage  │
└──────────────────────────┬──────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────┐
│  Open Source Services (Ubuntu — ikke EIRA)              │
│  CUPS · systemd · NetworkManager · Flatpak · SSSD · …   │
└──────────────────────────┬──────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────┐
│  Ubuntu LTS + Linux Kernel                              │
└─────────────────────────────────────────────────────────┘
```

**Governance** og **Cognitive Runtime** udvikles uafhængigt. `eira-governance-agent` og Intent Audit forbliver uændrede i scope.

---

## 2.1 Epistemisk rod: Identity først (to arkitektur-views)

Runtime-stacken (§4) er **implementeringsrækkefølge** — bottom-up fra storage til UI.

**Epistemisk model** — hvad der faktisk bestemmer sandhed i platformen — er **top-down fra Identity**:

```
                    Identity
                        │
        ┌───────────────┼───────────────┐
        │               │               │
   Object Graph    Capability        Trust
   (kanter +         (hvad må         (aggregeret
    evidence)          kaldes?)         beslutning)
        │               │               │
        └───────────────┼───────────────┘
                        │
                   Reasoning
                        │
                      AI/LLM
```

| View | Besvarer | Bruges til |
|------|----------|------------|
| **Runtime stack** | Hvad bygges oven på hvad? | Engineering, deployment, IPC |
| **Epistemisk rod** | Hvad kan vi vide — og hvem må handle? | Reasoning, AI, compliance |

**Konsekvenser:**

1. **Identity** er autoritativ for `delegates_to`, `acts_for`, `member_of` og assurance ved step-up — ikke AI.
2. **Object Graph** kanter bærer `evidence` (confidence, source, verified) — se [Object Graph v0.3](EIRA_Object_Graph_Specification_v0.3.md).
3. **Trust** aggregerer kant-evidens + identity-kontekst — erstatter ikke kant-metadata.
4. **Intent** er brugerens sprog; **AI** er sidste led i kæden — ikke fundamentet.

> Platformen står og falder med Identity. AI uden identitet og evidens er en chatbot.

---

## 3. EIRAs differentiator: Intent → Capability → Adapter → System

De fleste AI-platforme:

```
Prompt → LLM → Svar
```

EIRA:

```
Intent → Capability → Adapter → System
```

**Capability Layer** er ikke et implementeringsdetalje — det er **kontrakten mellem intention og teknologi**. Den gør, at SAP, Business Central, SharePoint, printere og ERP kan udskiftes uden at agenten omskrives.

Capability er et **førsteklasses lag** i Cognitive Runtime (se §4).

---

## 4. Cognitive Runtime Stack (14 komponenter)

Nummerering er **bottom-up** (lag 1 = fundament). Lag 0a–0c er Governance (se Architecture Overview).

| # | Lag | Kerneansvar |
|---|-----|-------------|
| **1** | Local-First Storage | Sikker, persistent lokal cache (SQLite, filer) |
| **2** | Cryptographic Layer | Signing, local-first sikkerhed |
| **3** | Transport Abstractor | Multi-protocol adapter-support |
| **4** | Identity Bridge | Entra, eID (eIDAS 2.0), step-up, delegation |
| **5** | Object Graph | Base-primitiver: Person, Document, Interaction, … |
| **6** | Knowledge Graph | Org-hukommelse, skills, mønstre |
| **7** | Temporal Graph | Validity windows, time-travel queries |
| **8** | Agency Layer | Sporbarhed, accountability (hvem handlede?) |
| **9** | Trust & Evidence | Sandsynlighed 0–100%, kilder, evidens |
| **10** | **Capability Layer** | Hvad kan hvert kildesystem? (manifest) |
| **11** | Journey Orchestrator | Hierarkiske flows (Super/Sub-Journeys) |
| **12** | Intent Engine | Formålsdetektion (hvorfor?) |
| **13** | Reasoning Engine | Inference, rationale til UI |
| **14** | Cognitive Interface | Trust-aware dashboard (Explorer) |

```
LAG 14  Cognitive Interface     Beslutningsdashboard — ikke filbrowser
   ↓
LAG 13  Reasoning Engine       "Fordi: frist i dag kl. 17"
LAG 12  Intent Engine          Parse, kategori + action
LAG 11  Journey Orchestrator   ████░░░░ 2 af 5 trin
   ↓
LAG  9  Trust & Evidence       ✓ Indisputable 96% · ≈ Probable 71%
LAG  8  Agency Layer           Hvem handlede, med hvilken delegation?
   ↓
LAG  6–7 Knowledge + Temporal  "Hvem var Lars i marts 2024?"
LAG  5  Object Graph           Budget → Sag → Person
   ↓
LAG 10  Capability             Public360 kan godkende? Ja.
LAG  3  Transport              Kald adapter
   ↓
LAG  4  Identity Bridge        Session + step-up
LAG  1–2 Storage + Crypto      Local-first, signed evidence
```

**Intent Audit** (tværgående) emitteres fra Identity, Intent, Agency, Capability, Transport og Governance — uændret i rolle.

---

## 5. Mapping til Architecture Overview v1.0

| Architecture Overview (Lag 1–8) | Cognitive Runtime v1.0 |
|--------------------------------|--------------------------|
| 1 Præsentation | 14 Cognitive Interface |
| 2 Identity | 4 Identity Bridge + 8 Agency |
| 3 Agent Engine | 13 Reasoning + 11 Journey |
| 4 Intent Interface | 12 Intent Engine + Intent Audit |
| 5 Capability | **10 Capability Layer** |
| 6 Objektgraf | 5 Object + 6 Knowledge + 7 Temporal |
| 7 Adapter | 3 Transport Abstractor |
| 8 Kildesystemer | (ekstern, uændret) |
| — | 1–2 Storage + Crypto (nyt fundament) |

Lag 0 (Control, Operations, Compliance) og `eira-governance-agent` er **uden for** dette dokument — se [EIRA_OS_Architecture_Overview_v1.0.md](EIRA_OS_Architecture_Overview_v1.0.md).

---

## 6. Core primitives

### 6.1 Trust Levels (normative)

| Niveau | Score | Betydning | UI-eksempel |
|--------|-------|-----------|-------------|
| **Unconfirmed** | 0–20% | AI-gæt, ukendt kilde | `? Needs confirmation` |
| **Indicative** | 21–50% | Én svag kilde | `≈ Indicative 34%` |
| **Probable** | 51–79% | Flere kilder, uverificeret | `≈ Probable 71%` |
| **Confirmed** | 80–95% | Manuelt verificeret eller signeret | `✓ Confirmed 88%` |
| **Indisputable** | 96–100% | Kryptografisk bevist | `✓ Indisputable 96%` |

Trust er den nye **Explorer**: brugeren navigerer efter tillid og beslutning — ikke efter mapper.

```
✓ Indisputable 96%
  Budget godkendt

──────────────

≈ Probable 71%
  Leverandør forventes at levere fredag

──────────────

? Needs confirmation
  Tre forskellige adresser fundet
```

### 6.2 Intent Taxonomy (udvidelse af Intent Protocol v0.1)

v1.0 introducerer **kategori** (formål) **ved siden af** action (verb) fra Intent Protocol v0.1:

| Kategori | Eksempler (actions) |
|----------|---------------------|
| `DECISION` | approve, reject, postpone |
| `DISCUSSION` | explore, brainstorm, clarify |
| `INFORMATION` | brief, status, report |
| `ACTION` | agree, promise, task, send, create |
| `RELATION` | build, maintain, close |

Normativ intent-struktur (udvidet):

```json
{
  "intent_id": "uuid",
  "category": "DECISION",
  "action": "approve",
  "confidence": 0.94,
  "trust_level": "probable",
  "entities": [{ "type": "document", "id": "budget_2027", "score": 0.95 }],
  "journey_id": "uuid | null",
  "required_assurance": "org_acting",
  "status": "pending_confirmation"
}
```

**Intent Protocol v0.1 actions forbliver gyldige.** Kategori er et tillæg — ikke en erstatning.

### 6.3 Temporal Graph (udvidelse af Object Graph v0.1)

Relationer får **validity windows**:

```json
{
  "id": "uuid",
  "from_id": "uuid",
  "to_id": "uuid",
  "relation_type": "reports_to",
  "valid_from": "2023-01-01T00:00:00Z",
  "valid_to": "2024-06-30T23:59:59Z",
  "metadata": {}
}
```

Query-eksempel: *"Hvem var Lars i forhold til Mette i marts 2024?"*

### 6.4 Journey (UX)

I stedet for isoleret `Godkend budget`:

```
Budget 2027
████░░░░
2 af 5 trin

✓ Controller
✓ Leder
→ Dig (Økonomichef)
```

Journey Orchestrator styrer Super/Sub-Journeys. UI følger UX-regel 4 (*én ting skriger ad gangen*) — journey-progress giver kontekst uden støj.

---

## 7. UX-principper (uændrede, beriget)

De seks normative regler fra [EIRA_User_Experience_Logic_v0.1](EIRA_User_Experience_Logic_v0.1.md) gælder for Cognitive Interface:

| # | Regel | v1.0 berigelse |
|---|-------|----------------|
| 1 | Ét system | Kun "EIRA" |
| 2 | Brugeren handler | Intent + Journey |
| 3 | Relationer, ikke stier | Object + Temporal Graph |
| 4 | Én ting skriger | Prioritering + journey-trin |
| 5 | Forklar hvorfor | Reasoning Engine + Trust |
| 6 | Altid overstyre | Inputfelt uændret |

Bekræftelsesflow forbliver: **Foreslå → Forklar → Bekræft → Udfør → Resultat**. Aldrig silent execute.

---

## 8. BI og enterprise intelligence

| Komponent | Bruger-BI | IT-BI |
|-----------|-----------|-------|
| Trust & Evidence | Badges på handlingskort | Audit + compliance evidens |
| Temporal Graph | Historisk kontekst | Delegation/revision |
| Knowledge Graph | (bag kulissen) | Mønstre, flaskehalse |
| Journey Orchestrator | Flow-status | Fleet Console analytics |
| Intent Audit | — | NIS2/KL-rapporter (uændret) |

---

## 9. Prototype roadmap

Kører **på Ubuntu reference-PC** — ikke isoleret mockup.

| Fase | Uger | Leverance |
|------|------|-----------|
| **1** | 1–3 | Trust Layer + Journey prototype (Python/FastAPI); Intent Audit → Wazuh stub |
| **2** | 4–6 | Intent + Agency; lokal Mistral; Capability manifest (én adapter) |
| **3** | 7–9 | Cognitive Dashboard (Tauri/React); `eira-shell` vertical slice |

Governance-spor (`eira-governance-agent`, Fleet enroll) kan køre **parallelt** — se [Sprint_Plan_v0.1.md](../Sprint_Plan_v0.1.md).

---

## 10. Dokumenthierarki

```
EIRA_Platform_Principles_v1.0.md           ← må aldrig brydes
EIRA_Open_Architecture_v1.0.md             ← fire specs + certificering
EIRA_OS_Architecture_Overview_v1.0.md      ← Lag 0 + 8 + Intent Audit
EIRA_Cognitive_Runtime_v1.0.md             ← dette dokument (runtime evolution)
??? EIRA_Intent_Protocol_v1.1.md           ← actions + category (v1.1)
??? EIRA_Object_Graph_Specification_v0.2.md ← validity windows (v0.2)
??? EIRA_User_Experience_Logic_v0.1.md
??? EIRA_Desktop_Architecture_v1.0.md      ← eira-shell, IPC, Explorer/Builder
```

---

## 11. Positionering

| Til publikum | Budskab |
|--------------|---------|
| **IT-chef / CIO** | Ubuntu bliver stående. EIRA tilføjer intelligent runtime. |
| **Enterprise Architect** | Ikke et nyt OS — en platform med åbne specs og løs kobling via Capability. |
| **Slutbruger** | Beslutningsdashboard: tillid, journeys, handlinger — ikke filer. |
| **CISO** | Trust-scores + Intent Audit = stærkere evidens end fil-logs. |

---

*EIRA Cognitive Runtime v1.0 — Fortroligt udviklingsdokument*
