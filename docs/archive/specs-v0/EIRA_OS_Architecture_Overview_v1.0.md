# EIRA OS � Arkitekturoversigt v1.0

**Status:** G�ldende arkitektur (synkroniseret med strategidokumenter)  
**Dato:** 26. juni 2026  
**Projekt:** EIRA OS  
**Relateret:** [EIRA Platform Principles v1.0](EIRA_Platform_Principles_v1.0.md)
- [EIRA Cognitive Runtime v1.0](EIRA_Cognitive_Runtime_v1.0.md) — runtime evolution (v7)
- [EIRA Desktop Architecture v1.0](EIRA_Desktop_Architecture_v1.0.md) — eira-shell, IPC, Explorer/Builder
- EIRA Identity Strategy v0.2
- EIRA Enterprise IT Requirements v0.1
- EIRA OS v2.0 Whitepaper

---

## 1. Arkitektonisk kerne

EIRA OS er opdelt i **to planer**:

| Plan | Hvad | Hvor k�rer det |
|------|------|----------------|
| **Lag 0 � Management & Governance Plane** | IT-styring, policies, compliance | Centralt (cloud/on-prem portal) |
| **Lag 1�8 � Runtime Plane** | Brugeroplevelse, identitet, agenter, adaptere | EIRA PC (endpoint) |

**Intent Audit** er en **tv�rg�ende observabilitetsstr�m** � den forbinder runtime med Lag 0.

```
                    ???????????????????????????????????????
                    ?  LAG 0: MANAGEMENT & GOVERNANCE      ?
                    ?  Portal � Policies � Compliance      ?
                    ???????????????????????????????????????
                                       ? policies ?  audit ?
                    ???????????????????????????????????????
                    ?         INTENT AUDIT (tv�rg�ende)      ?
                    ???????????????????????????????????????
     ??????????????????????????????????????????????????????????????????????
     ?  LAG 1�8: RUNTIME PLANE (EIRA PC)                                  ?
     ?  Pr�sentation ? Identity ? Agent ? Intent ? Capability ? ...       ?
     ??????????????????????????????????????????????????????????????????????
```

---

## 2. Lag 0 � Management & Governance Plane

**Hjernen i IT-afdelingen.** Ikke en del af slutbrugerens oplevelse � det er kontrolplanet.

IT-chefen opererer her. Tusindvis af endpoints styres via **YAML-baserede policies** (versionerbare i git, reviewbare f�r udrulning).

### 2.1 Tre engines i Lag 0

| Engine | Ansvar | IT-rolle |
|--------|--------|----------|
| **Control** | Policies, app whitelist, AI-regler, focus states | IT-chef, sikkerhed |
| **Operations** | Enrollment, staged rollout, rollback, inventory, remote wipe | Drift |
| **Compliance** | NIS2/KL-rapporter, evidence store, SIEM-eksport, revision | CISO, revisor |

```
???????????????????????????????????????????????????????????????????
?              LAG 0: MANAGEMENT & GOVERNANCE PLANE                ?
?                    (EIRA Enterprise Portal)                      ?
???????????????????????????????????????????????????????????????????
?    CONTROL      ?     OPERATIONS      ?       COMPLIANCE        ?
?  policy.yaml    ?  staged channels    ?  NIS2 / KL / GDPR       ?
?  app whitelist  ?  5%?20%?50%?100%   ?  one-click reports      ?
?  AI governance  ?  golden image       ?  evidence store         ?
?  focus states   ?  remote wipe        ?  SIEM / webhook export  ?
???????????????????????????????????????????????????????????????????
         ? policies ?        ? commands ?            ? reports ?
         ?????????????????????????????????????????????
                              ?
                    ?????????????????????
                    ?  eira-governance-  ?
                    ?  agent (endpoint)    ?
                    ?????????????????????
                              ?
                    ?????????????????????
                    ?   1.000+ EIRA PC'er ?
                    ?????????????????????
```

### 2.2 Policy som kode

```yaml
# Udgivet fra Portal ? pushed til endpoints via governance-agent
version: "1.0"
org_unit: "OU=Skoleforvaltning,DC=kommune,DC=dk"

updates:
  channel: stable
  staged_rollout: [5, 20, 50, 100]
  security_patch_max_hours: 48

apps:
  allowed: [public360-adapter, kmd-opus-adapter, chrome, teams]
  blocked: [tor-browser, telegram]

audit:
  log_intents: true
  retention_days: 365

compliance:
  frameworks: [nis2, kl-minimumskrav, gdpr]
```

### 2.3 Staged rollout (Operations)

IT-chefen ruller opdateringer ud i kanaler � ikke big bang:

```
stable-2.1.4 (sikkerhedspatch)
  ??? Ring 0: IT-test (5 PC)
  ??? Ring 1: 5% (62 PC)
  ??? Ring 2: 20% (249 PC)
  ??? Ring 3: 50% (623 PC)
  ??? Ring 4: 100% (1.247 PC)
         ??? Rollback til 2.1.3 hvis fejlrate > threshold
```

---

## 3. Runtime Plane � Lag 1 til 8

Oplevelses- og integrationslaget p� EIRA PC. Opdateret fra whitepaper (7 lag) + Identity som eget lag.

| Lag | Navn | Kerneansvar |
|-----|------|-------------|
| **1** | Pr�sentation | Explorer Mode, Builder Mode (Tauri) |
| **2** | Identity | EIRA Identity Bridge, Authenticator, step-up |
| **3** | Agent Engine | Analyzer, Prioritizer, Suggester, Executor |
| **4** | Intent Interface | Parsing, entity resolution, **Intent Audit emission** |
| **5** | Capability Layer | Hvad kan hvert kildesystem? |
| **6** | Objektgraf | Tynd cache � relationer, ikke content |
| **7** | Adapter Layer | EIRA Adapter Standard |
| **8** | Kildesystemer | SharePoint, Public360, KMD OPUS, SAP, � |

```
LAG 1  Pr�sentation     "Godmorgen Mette. Budget mangler godkendelse."
   ?
LAG 2  Identity         Entra-session + step-up ved behov
   ?
LAG 3  Agent Engine     Prioriterer, foresl�r handling
   ?
LAG 4  Intent Interface "Godkend budget" ? approve(budget_2026.docx)
   ?                    ??? Intent Audit event emit ???
LAG 5  Capability       Public360 kan godkende? Ja.
   ?
LAG 6  Objektgraf       budget_2026 ? sag_2024-15 ? Lars
   ?
LAG 7  Adapter          Kald Public360 API
   ?
LAG 8  Kildesystem      Public360 udf�rer godkendelse
```

---

## 4. Intent Audit � den unikke differentiator

**Tv�rg�ende observabilitet.** Ikke et lag brugeren ser � det er evidenslaget der g�r EIRA attraktivt for CISO og revisor.

### 4.1 Windows vs. EIRA

| | Windows / M365 | EIRA Intent Audit |
|---|----------------|-------------------|
| Log | Lars �bnede Budget.xlsx | Lars fors�gte at **godkende** Budget.xlsx |
| Kontekst | Filsti, tidspunkt | Intention, m�l-objekt, fokus, rolle |
| Resultat | (ofte intet) | Succes / blokeret / step-up kr�vet |
| Rationale | (ingen) | "Manglende MitID Erhverv � bruger informeret" |
| Policy | (adskilt system) | Hvilken policy-regel der greb ind |

### 4.2 Audit event � struktur

```json
{
  "event_id": "uuid",
  "timestamp": "2026-06-26T10:23:01Z",
  "actor": {
    "user_id": "lars@kommune.dk",
    "org_unit": "Skoleforvaltningen",
    "assurance_level": "eid_low",
    "focus": "Kommunepilot"
  },
  "intent": {
    "raw": "Godkend budget",
    "parsed_action": "approve",
    "confidence": 0.94,
    "target_objects": ["budget_2026.docx", "sag_2024-15"]
  },
  "outcome": {
    "status": "blocked_step_up_required",
    "required_assurance": "org_acting",
    "current_assurance": "eid_low"
  },
  "rationale": {
    "policy_rule": "step_up_rules.approve.budget",
    "user_message": "Denne handling kr�ver MitID Erhverv",
    "user_action": "pending"
  },
  "adapter": null,
  "ai_metadata": {
    "model": "gemma-2b",
    "local": true
  }
}
```

### 4.3 Hvor Intent Audit emitteres

| Lag | Event-type |
|-----|------------|
| 2 Identity | Login, step-up, step-up afvist, session revoke |
| 4 Intent | Intention parsed, confidence, bruger rettede intention |
| 3 Agent | Handling foresl�et, bruger accepterede/afviste |
| 5 Capability | Capability mangler, fallback valgt |
| 7 Adapter | API-kald, svar, fejl |
| 0 Governance | Policy push, rollout, compliance scan |

Alle events str�mmer til **Compliance Engine** (Lag 0) og kan forwardes til SIEM.

### 4.4 V�rdi for incident response

```
CISO-sp�rgsm�l: "Hvad skete der med budget-filen i g�r?"

Windows-svar:  Lars �bnede filen kl. 10:23. (M�ske.)

EIRA-svar:     10:23 � Lars fors�gte godkendelse (intention)
               10:23 � Blokeret: kr�ver org_acting
               10:24 � Step-up med MitID Erhverv gennemf�rt
               10:24 � Godkendelse udf�rt i Public360 (adapter-log)
               10:24 � Rationale vist til bruger (logget)
```

---

## 5. Compliance Engine � NIS2-ready med �t klik

Del af **Lag 0 (Compliance engine)**. Systemet ved selv hvilke policies der er aktive � revision dokumenterer sig selv.

### 5.1 Hvorfor det virker

Traditionelt: IT samler manuelt screenshots, policy-dokumenter og Excel-ark i m�nedsvis.

EIRA: Policies er **maskinl�sbare YAML**. Endpoints rapporterer **faktisk tilstand**. Intent Audit giver **adf�rds-evidens**.

```
????????????????     ????????????????     ????????????????
? Policy       ?     ? Endpoint     ?     ? Intent Audit ?
? (desired)    ? +   ? (actual)     ? +   ? (behaviour)  ?
????????????????     ????????????????     ????????????????
       ?                    ?                    ?
       ???????????????????????????????????????????
                            ?
                 ???????????????????????
                 ?  COMPLIANCE ENGINE   ?
                 ?  gap analysis        ?
                 ?  evidence bundle     ?
                 ?  NIS2 / KL report    ?
                 ???????????????????????
```

### 5.2 Rapport-eksempel (uddrag)

```
EIRA COMPLIANCE RAPPORT � Hvidovre Kommune
Periode: Q2 2026 | Frameworks: NIS2, KL minimumskrav, GDPR

ENHEDEROVERSIGT
  Total PC'er:     1.247
  Compliant:       1.221 (98,0%)
  Non-compliant:      26 (2,0%)

KL-S4 ENDPOINT-BESKYTTELSE
  Status: OPFYLDT ?
  Evidens: EDR aktiv p� 1.247/1.247 enheder

KL-S15 OPDATERINGER ? 30 DAGE
  Status: OPFYLDT ?
  Evidens: Seneste sikkerhedspatch ? 12 dage (median)

NIS2 �6 FORANSTALTNINGER
  Risikostyring:        Dokumenteret (policy v1.3)
  H�ndelsesh�ndtering:  3 h�ndelser logget, 0 kritiske
  Adgangskontrol:       Entra + step-up aktiv

INTENT AUDIT (unik evidens)
  Blokerede handlinger (step-up):     342
  Gennemf�rte godkendelser:           1.891
  Policy-afvigelser:                    0

[Eksporter PDF] [Eksporter til revisor] [Send til SIEM]
```

### 5.3 Framework-mapping

| Framework | EIRA-evidenskilde |
|-----------|-------------------|
| **NIS2 �6** | Policy YAML + endpoint state + audit |
| **KL tekniske minimumskrav** | Per-krav mapping (S4, S14, S15, �) |
| **GDPR** | Dataminimering, retention, intent log |
| **ISO 27001** | Kontrol-mapping (ved certificering) |
| **EU AI Act** | AI metadata i audit events |

---

## 6. De 12 arkitekturkomponenter

*"12 lag"* refererer til den **fulde komponentmodel** � ikke 12 runtime-lag p� endpoint.

| # | Komponent | Type |
|---|-----------|------|
| 0a | Control Engine | Lag 0 |
| 0b | Operations Engine | Lag 0 |
| 0c | Compliance Engine | Lag 0 |
| 1 | Pr�sentation | Runtime |
| 2 | Identity | Runtime |
| 3 | Agent Engine | Runtime |
| 4 | Intent Interface | Runtime |
| 5 | Capability Layer | Runtime |
| 6 | Objektgraf | Runtime |
| 7 | Adapter Layer | Runtime |
| 8 | Kildesystemer | Ekstern |
| � | **Intent Audit** | Tv�rg�ende (forbinder 1�8 med 0c) |

**Lag 0 (3 engines) + Runtime (8) + Intent Audit (1) = 12 komponenter.**

---

## 7. Endpoint-agenten

`eira-governance-agent` k�rer p� hver EIRA PC og er bindeleddet mellem Lag 0 og runtime:

| Funktion | Retning |
|----------|---------|
| Modtag policies | Lag 0 ? endpoint |
| Rapport�r compliance state | endpoint ? Lag 0 |
| Emit Intent Audit events | runtime ? Lag 0 |
| Udf�r remote commands | wipe, lock, force refresh |
| Staged rollout kanal | hvilken ring PC'en tilh�rer |

---

## 8. Produktdifferentiering � opsummering

| Stakeholder | EIRA's unikke v�rdi |
|-------------|---------------------|
| **Slutbruger** | �n flade, intentioner frem for systemer |
| **IT-chef** | Lag 0 Portal = Intune-lignende kontrol |
| **CISO** | Intent Audit � intention + rationale, ikke kun fil-events |
| **Revisor** | NIS2/KL-rapport med �t klik |
| **DPO** | Local-first, EU, dataminimering |
| **Indk�b** | Exitklausul, hybrid med Windows |

---

## 9. Implementeringsprioritet

| Prioritet | Komponent | Begrundelse |
|-----------|-----------|-------------|
| P0 | Lag 0 Portal (Control + Operations) | IT gatekeeper |
| P0 | `eira-governance-agent` | Policy push + state report |
| P0 | Intent Audit pipeline | Differentiator � design fra dag �t |
| P0 | Identity (Lag 2) | Entra + step-up |
| P1 | Compliance Engine + NIS2/KL mapping | Revisor-v�rdi |
| P1 | SIEM export | CISO-krav |
| P2 | Full framework certificering | ISO 27001 |

---

## 10. Dokumenthierarki

```
EIRA_OS_Architecture_Overview_v1.0.md     ? dette dokument (master)
??? EIRA_Identity_Strategy_v0.2.md        ? Lag 2 detaljer
??? EIRA_Enterprise_IT_Requirements_v0.1.md ? Lag 0 krav fra IT
??? EIRA OS v2.0 Whitepaper                 ? oprindelig vision (kap. 4, 18)
```

---

*EIRA OS Arkitekturoversigt v1.0 � Fortroligt udviklingsdokument*
