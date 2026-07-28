# EIRA Strategic Reality Check v0.1

**Status:** Normativ — intern strategi, salg, arkitektur  
**Dato:** 4. juli 2026  
**Formål:** Én sandhed om kommerciel risiko, adaptere, identity scope, hybrid vs. paritet — og hvad der **ikke** er løst endnu  
**Målgruppe:** Founders, arkitektur, salg, IT-partnere  
**Relateret:**
- [EIRA_Success_Failure_Matrix_v0.1.md](EIRA_Success_Failure_Matrix_v0.1.md)
- [EIRA_Risk_Sprint_0-1_v0.1.md](EIRA_Risk_Sprint_0-1_v0.1.md)
- [EIRA_Windows_Technical_Parity_v0.1.md](EIRA_Windows_Technical_Parity_v0.1.md)
- [EIRA_Windows_Parity_Architecture_v0.1.md](EIRA_Windows_Parity_Architecture_v0.1.md)
- [EIRA_Enterprise_Endpoint_Transition_v1.0.md](../../../company/EIRA_Enterprise_Endpoint_Transition_v1.0.md)

---

## 1. Én sætning

> **EIRA vinder på wedges, audit og staged overgang — ikke på at love fuld Windows-erstatning dag 1. Paritet er integrationsmålet; hybrid er den teknisk korrekte strategi i fase 0–2.**

Dette dokument afklarer den interne spænding mellem *ærlig gap-analyse* og *integrationsarkitektur*, så salg, IT og produkt ikke divergerer.

---

## 2. To parallelle sandheder (hybrid-fase vs. paritetsmål)

| Perspektiv | Dokument | Budskab | Gælder hvornår |
|------------|----------|---------|----------------|
| **Ærlig gap** | [Technical Parity](EIRA_Windows_Technical_Parity_v0.1.md) | Windows vinder på modenhed, GPO, Win32, MDM-dybde | Fase 0–2, IT-review, pilot-gates |
| **Integrationsmål** | [Parity Architecture](EIRA_Windows_Parity_Architecture_v0.1.md) | Match via OSS + EIRA orkestrering — ikke permanent underlegenhed | Fase 3–4, arkitektur, bundle-design |
| **Kommerciel overgang** | [Enterprise Transition](../../../company/EIRA_Enterprise_Endpoint_Transition_v1.0.md) | Staged rollout, rollback, hybrid som capability — ikke big bang | Alle kundemøder |

**Regel for salg:** Sig aldrig *"EIRA erstatter Windows fuldt ud i fase 1"*. Sig: *"EIRA er standard-PC for vidensarbejde hvor profilen passer; legacy forbliver tilgængelig via session eller hybrid indtil capability dækker det."*

**Regel for arkitektur:** Design som om paritet er slutmålet — men ship kun det der er testet på reference-PC.

---

## 3. R1 — Adapter-adoption (R1a vs. R1b)

Se [EIRA_Risk_Sprint_0-1_v0.1.md](EIRA_Risk_Sprint_0-1_v0.1.md) §2.7.

| | **R1a (pilot)** | **R1b (marked)** |
|---|----------------|------------------|
| **Horisont** | Sprint 0–1, ~50 PC | 2–3 år, national skalering |
| **Problem** | Pilot skal vise værdi uden leverandører | Leverandører bygger ikke adaptere frivilligt |
| **Løsning** | EIRA ejer 2 reference-adaptere (M365 + Public360/fil) | Wedges + politik + betalt integration |
| **Indtægt** | Pilot-commitment | Må **ikke** være eneste vej til måned 6 |
| **Go/no-go** | ≥ 2 adaptere i demo; ≥ 80% daglige opgaver | Udbudstekst + ≥ 2 leverandør-møder booket |

**Wedges (R1b — kontrollerbare nu):**

1. **M365-first pilot** — Entra, SharePoint, Teams via reference-adapter  
2. **Intent Audit / Fleet standalone** — sælg compliance uden fuld OS-udrulning  
3. **EIRA som betalt integrator** — adapter-bygning som projekt, ikke vente på KMD  
4. **ECK** — compatibility kernel for eksisterende miljøer  

**Realitet:** Reference-adaptere beviser demo — ikke skalering. Politisk spor (KL/KOMBIT) tager 12–24 måneder og må køre **parallel** med indtægts-wedges.

---

## 4. Identity scope — Entra-first (Sprint 1)

Arkitekturen forbliver EUDI-ready i dokumentation. **Implementering i Sprint 1 er Entra-first.**

| In scope (pilot) | Deferred |
|------------------|----------|
| Entra OIDC login + session | OID4VP / OID4VCI |
| MitID Erhverv step-up (mock → prod) | `dk-pack`, `de-pack` wallets |
| Intent Audit med session identity | SAML legacy IdP |
| Policy YAML læses og håndhæves | Delegation-model i produktion |

Se [EIRA_Identity_Strategy_v0.2.md](EIRA_Identity_Strategy_v0.2.md) §11.

**Risiko hvis scope kryber:** Identity bliver et parallelprodukt der forsinker Explorer og Fleet MVP. **Hold linjen.**

---

## 5. Windows-paritet — hvad vi lover og ikke lover

### 5.1 Vi lover ikke

| Løfte | Hvorfor ikke |
|-------|--------------|
| 1:1 GPO-import | Linux er ikke GPO-native — EIRA YAML er alternativet |
| WINE som generel Win32-løsning | Ufuldstændig; VM/RDP/session er paritetspath |
| Fuldt SCCM/Intune-paritet i fase 1 | Fleet Control er design — MVP er enroll + bundle + compliance % |
| "Bring your own PC" i pilot | Kun [EIRA Certified PC](EIRA_Support_Matrix_v0.1.md) / reference-hardware |
| EIRA bygger manglende drivere | Ubuntu/Canonical ejer drivere — EIRA ejer politik og certificering |

### 5.2 Vi lover (fase 0–1)

| Løfte | Bevis |
|-------|-------|
| Samme Entra-identitet som Windows-flåden | Entra OIDC på reference-PC |
| Intent Audit i samme SIEM | CEF/Wazuh demo |
| Staged rollout med rollback | [Enterprise Transition](../../../company/EIRA_Enterprise_Endpoint_Transition_v1.0.md) §9 |
| Print/VPN/smartcard på godkendt hardware | [Support Matrix v0.1](EIRA_Support_Matrix_v0.1.md) |
| Hybrid uden big bang | Legacy session som capability |

---

## 6. De 10 blindvinkler — status og ejerskab

Krydsreference til ekstern paritetsanalyse og interne specs.

| # | Blindvinkel | Status | Ejerskab / dokument |
|---|-------------|--------|---------------------|
| 1 | **Langsigtet vedligeholdelse** | Dækket | [OSS Operations Model](EIRA_OSS_Operations_Model_v0.1.md), [Update Release Train](../../eira-fleet-control/docs/specs/EIRA_Update_Release_Train_v0.1.md), [OSS Manifest](EIRA_OSS_Integration_Manifest_v0.1.md) |
| 2 | **Hardware / drivere** | Pilot klar | [Support Matrix v0.1](EIRA_Support_Matrix_v0.1.md) — v1.0 (bred hardware) efter pilot |
| 3 | **Ydeevne under stress** | Dækket | [Performance Acceptance](EIRA_Performance_Acceptance_v0.1.md) + Validation Plan V-PERF |
| 4 | **Sikkerhed i praksis** | Design stærkt | [EDR Requirements](EIRA_EDR_Partner_Requirements_v0.1.md) + Validation Plan §7 — red-team fuld P2 |
| 5 | **Brugeradoption** | Dækket | [Change Management Pilot](EIRA_Change_Management_Pilot_v0.1.md) + Transition |
| 6 | **Fejl og fallback** | Dækket | [BCP Endpoint Fallback](EIRA_BCP_Endpoint_Fallback_v0.1.md), Transition §9, Release Train rollback |
| 7 | **Fremtidssikring** | Roadmap findes | Parity Architecture P0–P3 — mangler: Windows feature watch-proces |
| 8 | **Compliance** | Stærk på NIS2/KL | Compliance Engine design — mangler: Schrems II dataflow-vedlæg, DPA-skabelon |
| 9 | **Test & validering** | Dækket | [Pilot Validation Plan](EIRA_Pilot_Validation_Plan_v0.1.md) |
| 10 | **Leverandør & TCO** | Delvist | Vendor §7 — playbook P2; TCO i [Business Plan](../../../company/EIRA_Business_Plan_Sprint_v0.1.md) Spor 3 |

---

## 7. Vendor engagement — beslutningstræ

Når proprietær protokol eller manglende Linux-klient blokerer:

```
1. Open source wedge (OpenConnect, IPP Everywhere, WireGuard)
        ↓ fejler
2. Vendor Linux-klient (test i VPN/EDR matrix)
        ↓ fejler
3. Managed session (RDP / Windows 365 / AVD) som capability
        ↓ fejler
4. Hybrid arbejdsstation (denne PC forbliver legacy endpoint)
        ↓ fejler
5. Pilot aflyses for denne profil — dokumentér i salg
```

**Incitament til leverandør:** "EIRA Adapter Standard — I beholder kunden; vi er integrationslag." Betalt pilot-integration som fallback.

---

## 8. VBA, Access og Win32-legacy

| Scenario | Strategi | Pilot |
|----------|----------|-------|
| Makro-tung Excel (.xlsm) | Legacy Runtime (KVM) eller hybrid PC | **Undgå** i pilot-afdeling |
| Access-database | VM eller behold Windows | **Undgå** |
| Win32 + egen driver-DLL | Fejler på EIRA — hybrid | Dokumentér i pilot-selektion |
| Browser-only SaaS | Native — ingen issue | **Foretrukket** pilot-profil |

**Pilot-selektion (normativ):** Vælg afdeling med M365-tung, browser-first arbejdsdag — ingen kontraktklausul der kræver Windows desktop.

---

## 9. Omstillingsomkostning og TCO

### 9.1 Skjulte omkostninger (ærligt)

| Post | Windows-stack | EIRA-stack | Noter |
|------|---------------|------------|-------|
| Platform-licens | Per-seat OS + suite | Ubuntu (inkl.) + EIRA licens | EIRA kan være lavere |
| Endpoint-styring | Intune/SCCM | Fleet Control + governance-agent | Fleet er **ny** kompetence for IT |
| OSS-bundle vedligehold | Microsoft centraliserer | EIRA QA per bundle | **Skjult post** — skal med i TCO |
| L1-support | Kendt model | L0/L1/L2 matrix | Se Support Matrix |
| Omstilling | Lav (status quo) | Træning, champion, parallel drift | 90 dage minimum fase 1 |
| Legacy hybrid | — | Nogle PC'er forbliver | Ikke fejl — planlagt |

### 9.2 TCO-pitch (kort)

> Lavere platform-TCO over 3 år **hvis** pilot-profilen passer og hybrid-andelen falder over tid. **Ikke** billigere hvis organisationen kører 100% parallel drift i 3 år.

Detaljer: [Business Plan Sprint](../../../company/EIRA_Business_Plan_Sprint_v0.1.md) Spor 3.

---

## 10. Compliance — NIS2, eIDAS, Schrems II

| Krav | EIRA-svar | Status |
|------|-----------|--------|
| **NIS2 §6** | Policy YAML + endpoint state + Intent Audit | Compliance Engine P1 |
| **KL minimumskrav** | Patches ≤ 30 dage via bundles | Release Train |
| **GDPR** | Local-first, retention 365d, sletning procedure | Identity Spec |
| **eIDAS 2.0 / EUDI** | Identity Strategy — arkitektur klar, pilot Entra-first | Deferred post-pilot |
| **Schrems II** | Data i EU; ingen US cloud i hot path for audit/identity | Mangler: 1-side dataflow-vedlæg til DPA |

**Differentiator vs. Windows:** Intent Audit (intention + rationale) — ikke kun filsti og process events.

---

## 11. OSS drift og vedligeholdelse

EIRA **signerer og tester hele stacken som én bundle** — ikke løs `apt upgrade`.

| Lag | Ejerskab | Opdatering |
|-----|----------|------------|
| Ubuntu LTS + security | Canonical (USN) → EIRA QA → bundle | Ugentlig security bundle |
| OSS-agenter (Wazuh, Falco, sssd, …) | Upstream + EIRA pin i `package-list.lock` | Samme bundle |
| EIRA-native (`eira-*`) | EIRA engineering | Semver i bundle |
| Kommerciel EDR (valgfri) | Partner + EIRA certificering | Partner SLA + EIRA matrix |

**Mål-SLA (pilot):** Kritisk CVE → certificeret bundle inden 7 dage (accelereret kanal 4t for emergency — se [Release Train](../../eira-fleet-control/docs/specs/EIRA_Update_Release_Train_v0.1.md)).

**Detaljer:** [OSS Operations Model](EIRA_OSS_Operations_Model_v0.1.md) — RACI, upstream-overvågning, bundle QA.

**Mangler (P1):** "Hvad vi ikke lover" 1-pager i Business Plan (copy fra Change Management §5.2).

---

## 12. Fallback og business continuity

Se **[BCP Endpoint Fallback v0.1](EIRA_BCP_Endpoint_Fallback_v0.1.md)** — tier-model (0–4), trigger-matrix, OU-flytning, RTO/RPO.

| Scenario | Handling | Dokument |
|----------|----------|----------|
| Bundle-fejl efter rollout | Atomic rollback (btrfs snapshot) | Release Train §3 |
| Policy-fejl | Push forrige policy snapshot | Transition §9 |
| Pilot fejler brugeraccept | Tier 3–4 efter Validation Plan | BCP §4–5 |
| VPN/EDR blocker | Tier 3 hybrid eller scope-reduktion | BCP §4.2 |
| Midlertidig retur til legacy endpoint | Tier 3 runbook — planlagt i kontrakt | BCP §5, §10 |

---

## 13. Fremtidssikring

| Mekanisme | Beskrivelse |
|-----------|-------------|
| **Paritet-dashboard** | Grøn/gul/rød per punkt 1–8 i Fleet (designet i OSS Manifest) |
| **LTS-cycle** | EIRA major = ny Ubuntu LTS + migrationsværktøj |
| **GPO-translator** | P3 — læs udvalgte AD GPO → EIRA policy |
| **Windows feature watch** | **Ikke etableret** — anbefalet: kvartalsvis review (1 time) |

---

## 14. P0-dokumenter — status (juli 2026)

| Dokument | Status | Dækker |
|----------|--------|--------|
| **EIRA_Strategic_Reality_Check_v0.1** | ✅ Dette dokument | Meta, R1, hybrid, blindvinkler |
| **EIRA_Support_Matrix_v0.1** | ✅ Skrevet | Reference-PC, L1/L2 |
| **EIRA_Desktop_Architecture_v1.0** | ✅ Skrevet | Shell, IPC, Explorer |
| **EIRA_VPN_Compatibility_Matrix_v0.1** | ◐ Skabelon — udfyld ved test | Punkt 6, vendor |
| **EIRA_EDR_Partner_Requirements_v0.1** | ✅ Skrevet | Punkt 4 — partner-beslutning uge 4 |
| **EIRA_Fleet_Control_MVP_Scope_v0.1** | ✅ I fleet-control | Punkt 7 |
| **EIRA_Pilot_Hardware_Selection_v0.1** | ⬜ Kan merges med Support Matrix v1.0 | Punkt 1, 5 |
| **EIRA_OSS_Operations_Model_v0.1** | ✅ Skrevet | Punkt 1 (vedligehold, CVE) |
| **EIRA_Pilot_Validation_Plan_v0.1** | ✅ Skrevet | Punkt 9 (test, gates) |
| **EIRA_BCP_Endpoint_Fallback_v0.1** | ✅ Skrevet | Punkt 1, 6 (fallback, BCP) |
| **EIRA_Change_Management_Pilot_v0.1** | ✅ Skrevet | Punkt 5 (adoption) |`n| **EIRA_Performance_Acceptance_v0.1** | ✅ Skrevet | Punkt 3 (FUSE/I/O) |

---

## 15. Beslutninger — deadline

| # | Beslutning | Deadline | Ejer |
|---|------------|----------|------|
| 1 | EDR: Wazuh-only OK til pilot? | Uge 4 | CISO + tech |
| 2 | Reference-PC model låst | Uge 2 | Tech |
| 3 | VPN test på target-miljø | Før pilot-commit | IT + tech |
| 4 | Indtægtsplan måned 3–6 | Uge 4 | Founder |
| 5 | Doc freeze efter vertical slice godkendt | Uge 4 | Alle |
| 6 | Positionering: hybrid-først i alle salgsmøder | Nu | Salg |

---

## 16. Relation til andre dokumenter

| Dokument | Fokus |
|----------|-------|
| **Dette dokument** | Kommerciel + strategisk realitet; R1; hybrid vs. paritet |
| [Technical Parity](EIRA_Windows_Technical_Parity_v0.1.md) | Tekniske gaps vs. Windows (ærlig) |
| [Parity Architecture](EIRA_Windows_Parity_Architecture_v0.1.md) | Hvordan vi matcher (integration) |
| [Success/Failure Matrix](EIRA_Success_Failure_Matrix_v0.1.md) | 25+25 medvind/modvind |
| [Enterprise Transition](../../../company/EIRA_Enterprise_Endpoint_Transition_v1.0.md) | Kundevendt overgang |
| [Ubuntu Integration](EIRA_Ubuntu_Integration_v0.1.md) | Blind spots under motorhjelmen |

---

## 17. Én sætning til teamet

> **Sælg hybrid og audit. Byg paritet. Dokumentér gaps. Tag penge ind via wedges mens politik modner.**

---

*EIRA Strategic Reality Check v0.1 — opdater ved pilot-go/no-go og kvartalsvis.*
