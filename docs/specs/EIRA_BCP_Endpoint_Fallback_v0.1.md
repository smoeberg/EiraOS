# EIRA BCP — Endpoint Fallback v0.1

**Status:** Normativ — drift, IT, indkøb  
**Dato:** 4. juli 2026  
**Formål:** End-to-end plan for forretningskontinuitet når EIRA-endpoint fejler — inkl. midlertidig retur til legacy endpoint  
**Målgruppe:** IT-chef, drift, champion, indkøb  
**Relateret:**
- [EIRA_Enterprise_Endpoint_Transition_v1.0.md](../../../company/EIRA_Enterprise_Endpoint_Transition_v1.0.md) §9
- [EIRA_Strategic_Reality_Check_v0.1.md](EIRA_Strategic_Reality_Check_v0.1.md) §12
- [EIRA_Pilot_Validation_Plan_v0.1.md](EIRA_Pilot_Validation_Plan_v0.1.md) §6
- [EIRA_Support_Matrix_v0.1.md](EIRA_Support_Matrix_v0.1.md)
- [EIRA_Update_Release_Train_v0.1.md](../../eira-fleet-control/docs/specs/EIRA_Update_Release_Train_v0.1.md)

---

## 1. Kernebeslutning

> **Fallback til legacy endpoint er en planlagt capability — ikke et projektnederlag.**

Hybrid er ikke undskyldning; det er **forsikring**. Denne BCP definerer **hvornår**, **hvordan** og **hvem** der aktiverer fallback — og hvordan organisationen returnerer til EIRA når stabil.

---

## 2. Scope og mål

| Felt | Pilot (Fase 1) | Skala (Fase 3+) |
|------|----------------|-----------------|
| **Berørte PC** | ≤ 50 i én OU | Per ring / geografisk enhed |
| **RTO** (tid til bruger kan arbejde igen) | 4 arbejdstimer | 2 arbejdstimer |
| **RPO** (datatab på endpoint) | 0 (cloud-first arbejde) | 0 |
| **Identitet** | Entra uændret | Entra uændret |
| **SIEM** | Fortsat logging fra begge endpoint-typer | Samme |

**RPO-antagelse:** Vidensarbejde i M365/Public360 — lokal disk er cache, ikke sandhed.

---

## 3. Fallback-tier model

| Tier | Navn | Hvornår | Brugeroplevelse | Varighed |
|------|------|---------|-----------------|----------|
| **0** | Self-heal | Transient fejl | EIRA auto-recover (rollback, restart) | Minutter |
| **1** | Degraded EIRA | Én komponent død | EIRA med begrænsning (rule-only, ingen LLM) | Timer–dage |
| **2** | Hybrid session | Legacy app krævet | EIRA + RDP/Windows 365 session | Planlagt |
| **3** | **OU-flytning** | EIRA ubrugelig for profil | Legacy endpoint for denne PC | Dage–uger |
| **4** | Pilot pause | >25% PC i Tier 3 eller sikkerhedsincident | Hele pilot-OU tilbage | Uger |

**Princip:** Eskalér **gradvist** — spring ikke til Tier 4 uden champion + IT-chef.

---

## 4. Trigger-matrix (hvornår aktiveres fallback)

### 4.1 Automatiske triggers (Fleet / monitoring)

| Signal | Threshold | Default handling |
|--------|-----------|------------------|
| Bundle apply fejlrate | > 5% i ring | Stop rollout; auto rollback ring |
| Compliance drop | > 10% på 24t | Alert IT; hold nye enroll |
| VPN compliance | < 90% i pilot-OU 4t | Alert; Tier 1 vurdering |
| Agent heartbeat mangler | > 15% PC 2t | Drift-incident |
| Intent Audit pipeline stop | > 1t | CISO alert; Tier 1 |

### 4.2 Manuelle triggers (IT-chef eller champion)

| Situation | Anbefalet tier | Godkender |
|-----------|----------------|-----------|
| VPN rød i matrix efter 48t fix-forsøg | 3 for berørte brugere | IT-chef |
| Signaturpude/driver umulig | 3 for berørte arbejdsstationer | IT-chef |
| Bruger NPS kill (Validation Plan) | 4 eller 3 per bruger | Champion + IT-chef |
| Sikkerhedsincident (kompromit) | 4 + isolate | CISO |
| Leverandør-adapter nede > 5 dage | 2 for berørte workflow | IT-chef |
| Politisk stop | 4 | Sponsor |

**Dokumentér altid:** trigger, tidspunkt, tier, godkender, forventet review-dato.

---

## 5. Runbooks per tier

### Tier 0 — Self-heal (automatisk)

```
1. governance-agent: health check fejler efter bundle apply
2. btrfs snapshot rollback (Release Train)
3. Report apply-result: rolled_back
4. Fleet: hold ring; notify IT operator
5. Bruger: ingen handling (session genoptages)
```

**Ejer:** Fleet + governance-agent. **Bruger synlighed:** Ingen (eller kort “EIRA genstarter”).

### Tier 1 — Degraded EIRA

| Handling | Kommando / proces |
|----------|-------------------|
| Rule-only intent (ingen LLM) | Policy `intent.llm_enabled: false` |
| Disable Legacy Bridge | Policy `legacy_bridge.enabled: false` |
| Force VPN reconnect | governance NM reload |

**Kommunikation:** IT til champion — “pilot fortsætter med begrænsning”. **Review:** Daglig indtil grøn.

### Tier 2 — Hybrid session (planlagt capability)

Bruger forbliver på EIRA PC; legacy app via managed session.

```
1. Capability detect: kræver Win32/VBA
2. EIRA Legacy Runtime (KVM) ELLER Windows 365 / AVD
3. Resultat returneres i Explorer — ikke separat desktop
4. Intent Audit logger session-start/stop
```

**Dette er ikke nødfallback** — men **permanent hybrid** for specifikke workflows. Se Transition Fase 2.

### Tier 3 — OU-flytning (midlertidig legacy endpoint)

**Formål:** Bruger skal kunne arbejde **inden RTO** med kendt toolchain.

```
1. IT-chef (eller delegat) godkender skriftligt — 1 sætning i ticket
2. Fleet: flyt device_id til ring 0 / OU "legacy-fallback"
3. Governance-agent: suspend EIRA policies (snapshot før)
4. Drift:  
   a) Re-deploy legacy golden image ELLER  
   b) Flyt fysisk PC fra EIRA-pool ELLER  
   c) Bruger midlertidigt på reservelaptop (legacy)
5. Entra: samme bruger — ingen identity-ændring
6. Kommunikation: champion → bruger (skabelon §8)
7. Ticket: review-dato max 30 dage
```

**Data:** OneDrive/M365 synk antaget. Lokal `/home` på EIRA-PC — backup hvis ikke cloud.

**Tilbage til EIRA:**

```
1. Root cause lukket + dokumenteret i Support Matrix / VPN matrix
2. Fase 0 test genkørt for berørt profil
3. IT-chef godkender re-enroll
4. Fleet: flyt tilbage til EIRA OU; push bundle + policy
5. Bruger: 30 min re-onboarding
```

### Tier 4 — Pilot pause

```
1. Møde: IT-chef + champion + CISO + sponsor (24t)
2. Fleet: hele pilot-OU → ring 0; stop nye enroll
3. Alle berørte PC: Tier 3 runbook eller behold EIRA hvis isoleret incident
4. Post-mortem inden 5 arbejdsdage (skabelon §9)
5. Beslutning: fix + fortsæt / reducer scope / afslut pilot
```

**Kommunikation til organisation:** “Pilot sat på pause — produktion uændret” — **ikke** “EIRA fejlede”.

---

## 6. Roller (RACI)

| Rolle | Tier 0–1 | Tier 3 | Tier 4 |
|-------|----------|--------|--------|
| **IT-chef** | I | **A** godkender OU-flyt | **A** pause |
| **Champion** | I | **R** brugerkommunikation | **R** |
| **CISO** | I (SEC) | C | **A** ved sikkerhed |
| **EIRA support** | **R** L1 triage | C | **R** post-mortem |
| **Drift** | **R** re-image | **R** | **R** |
| **Sponsor** | I | I | C |

---

## 7. Integration med support (L0/L1/L2)

| Lag | Fallback-relateret |
|-----|-------------------|
| **L1 EIRA** | Afgør: EIRA-bug vs. Ubuntu vs. hybrid-krav |
| **L0 Canonical** | Driver/kernel — hvis L0 ikke løser på 48t → eskalér Tier 3 |
| **L2** | Root-cause før re-enroll til EIRA |

**Support Matrix regel:** EIRA ejer **triage og beslutning** om tier — ikke printer-driver-debug.

---

## 8. Kommunikationsskabeloner

### Til bruger (Tier 3)

> *"Din arbejdsstation skifter midlertidigt tilbage til den standard I kender, mens vi løser [kort årsag — fx VPN]. Din login og filer i M365 er uændret. Champion [navn] kontakter dig inden [dato]."*

### Til organisation (Tier 4)

> *"Piloten med den nye arbejdsflade er sat på pause i én afdeling. Resten af kommunen er uændret. Dette er en planlagt sikkerhedsprocedure — ikke et sikkerhedsbrud."* (tilpas ved incident)

---

## 9. Post-mortem (obligatorisk ved Tier 3+)

| Felt | Indhold |
|------|---------|
| Trigger | Hvad aktiverede fallback? |
| Tier | Hvilket tier? |
| RTO faktisk | Timer til bruger produktiv |
| Root cause | Teknisk + proces |
| Matrix-opdatering | Support/VPN/EDR ændret? |
| Re-enroll kriterier | Hvad skal være grønt? |
| Anbefaling | Fortsæt / reducer scope / stop |

---

## 10. Indkøb og kontrakt

**Klausul (copy-paste):**

> *"Kunden har ret til midlertidig brug af eksisterende endpoint-platform for berørte arbejdsstationer i henhold til EIRA BCP Endpoint Fallback v0.1, uden at det udgør kontraktmæssig misligholdelse af leverandøren. Fallback aktiveres efter skriftlig godkendelse af IT-chef."*

**Dette sænker politisk risiko** og gør hybrid til **feature i kontrakten**.

---

## 11. Relation til hybrid-strategi

| Strategi | BCP-tier |
|----------|----------|
| Planlagt hybrid (VBA, signaturpude) | Tier 2 — **ikke** incident |
| Uplanlagt EIRA-fejl | Tier 3–4 |
| Bundle-fejl | Tier 0 |
| Brugerafvisning | Tier 3 per bruger eller Tier 4 |

Se [Strategic Reality Check](EIRA_Strategic_Reality_Check_v0.1.md) §2 — hybrid-fase er normal i Fase 0–2.

---

## 12. Test (validation)

Mindst **én tabletop-øvelse** før Fase 1:

| Øvelse | Deltagere | Varighed |
|--------|-----------|----------|
| “VPN rød 48t — hvad gør vi?” | IT-chef, champion, EIRA | 60 min |
| “Bundle 5% fejlrate — rollback” | Drift + Fleet | 30 min |
| “Én bruger Tier 3 — re-enroll” | L1 + drift | 30 min |

Log: dato, deltagere, gaps → Validation Plan opdatering.

---

## 13. Metrics (pilot)

| Metric | Mål |
|--------|-----|
| Tier 3 aktiveringer | ≤ 2 PC i 90 dage |
| Tier 4 | 0 (eller 1 med dokumenteret post-mortem) |
| Gennemsnitlig RTO Tier 3 | ≤ 4t |
| Re-enroll success første forsøg | ≥ 90% |

---

*EIRA BCP Endpoint Fallback v0.1 — gennemgås ved hver fase-gate og årligt derefter.*
