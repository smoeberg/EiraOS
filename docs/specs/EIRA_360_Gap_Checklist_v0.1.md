# EIRA OS � 360� Gap Checklist v0.1

**Status:** Audit-ark � kun **endpoint / oplevelse** (EIRA OS)  
**Dato:** 26. juni 2026  
**Form�l:** Kryds af f�r pilot-m�de � OS-scope  
**Andre planer:**
- [eira-fleet-control/docs/Sprint_Plan_v0.1.md](../../eira-fleet-control/docs/Sprint_Plan_v0.1.md) � administration, bundles, rollout  
- [company/EIRA_Business_Plan_Sprint_v0.1.md](../../company/EIRA_Business_Plan_Sprint_v0.1.md) � indt�gt, TCO, pilot-selektion  
- [Sprint_Plan_v0.1.md](../Sprint_Plan_v0.1.md) � OS handlingsplan (4 spor)

---

## S�dan bruges listen

| Symbol | Betydning |
|--------|-----------|
| ? | Ikke startet |
| ? | Delvist |
| ? | Klar |
| ? | Se andet projekt |

**Regel:** Fleet, bundles og IT-console ejes af **eira-fleet-control**. Business-punkter ejes af **company/**.

---

## A. Strategi og retning (verifikation)

| ? | Emne | Reference |
|---|------|-----------|
| ? | Vision: oplevelseslag p� Ubuntu | [Platform Principles](EIRA_Platform_Principles_v1.0.md) |
| ? | Samle, ikke erstatte | [UX Logic](EIRA_User_Experience_Logic_v0.1.md) |
| ? | Opm�rksomhedsk�de + 6 UX-regler | [UX Logic](EIRA_User_Experience_Logic_v0.1.md) |
| ✓ | R1a vs R1b adskilt | [Reality Check](EIRA_Strategic_Reality_Check_v0.1.md) |
| ? | Wedges (OS-vinkel: M365-first) | [Success/Failure Matrix](EIRA_Success_Failure_Matrix_v0.1.md) |
| ? | 2025 ? 2026 sporbarhed | [Lineage](../EIRA_v2_0_Lineage.md) |

---

## B. OS � fire spor (erstatter gammel �11 P0-dokumenter�-liste)

Detaljer og frister: **[Sprint_Plan_v0.1.md](../Sprint_Plan_v0.1.md)**

### Spor 1 � Uge 1�4

| ? | Leverance |
|---|-----------|
| ? | Sprint 0 vertical slice (max 6 komponenter) |
| ◐ | EDR-beslutning (Wazuh-only?) | Se EDR Partner Requirements §10 |
| ? | VPN-test + mini-matrix |
| ? | F�rste git commit (governance-agent / enroll) |
| ? | 50 intentioner til R2 |
| ? | Doc freeze |

### Spor 2 � F�r pilot-commit

| ? | Leverance |
|---|-----------|
| ✓ | Support Matrix v0.1 — [EIRA_Support_Matrix_v0.1.md](EIRA_Support_Matrix_v0.1.md) |
| ✓ | Desktop Architecture — [EIRA_Desktop_Architecture_v1.0.md](EIRA_Desktop_Architecture_v1.0.md) |
| ✓ | Strategic Reality Check — [EIRA_Strategic_Reality_Check_v0.1.md](EIRA_Strategic_Reality_Check_v0.1.md) |
| ◐ | VPN Compatibility Matrix (skabelon) — [EIRA_VPN_Compatibility_Matrix_v0.1.md](EIRA_VPN_Compatibility_Matrix_v0.1.md) |
| ✓ | EDR Partner Requirements — [EIRA_EDR_Partner_Requirements_v0.1.md](EIRA_EDR_Partner_Requirements_v0.1.md) |
| ✓ | OSS Operations Model — [EIRA_OSS_Operations_Model_v0.1.md](EIRA_OSS_Operations_Model_v0.1.md) |
| ✓ | Pilot Validation Plan — [EIRA_Pilot_Validation_Plan_v0.1.md](EIRA_Pilot_Validation_Plan_v0.1.md) |
| ✓ | BCP Endpoint Fallback — [EIRA_BCP_Endpoint_Fallback_v0.1.md](EIRA_BCP_Endpoint_Fallback_v0.1.md) |
| ✓ | Change Management Pilot — [EIRA_Change_Management_Pilot_v0.1.md](EIRA_Change_Management_Pilot_v0.1.md) |
| ✓ | Performance Acceptance — [EIRA_Performance_Acceptance_v0.1.md](EIRA_Performance_Acceptance_v0.1.md) |
| ? | Intent Audit demo (Wazuh live) |
| ? | NIS2 ? Intent Audit 1-pager |
| ? | Notifikation ? handlingskort-pipeline |
| ✓ | Prioriteringsheuristik — [EIRA_Prioritization_Heuristics_v0.1.md](EIRA_Prioritization_Heuristics_v0.1.md) |
| ✓ | UX Visual Language — [EIRA_UX_Visual_Language_v0.1.md](EIRA_UX_Visual_Language_v0.1.md) |
| ? | Tom Object Graph / first boot UX |
| ? | Legacy Bridge spike go/no-go |

### Spor 3 � Med kode

| ? | Leverance |
|---|-----------|
| ? | `eira-governance-agent` |
| ? | Factory Enroll firstboot |
| ? | Policy apply backends (stub) |
| ? | OSS CORE p� image |

### Spor 4 � Kan vente

| ? | Leverance |
|---|-----------|
| ? | Support Matrix v1.0 (bred hardware) |
| ? | WCAG testplan |
| ? | Pen-test program |
| ? | Object Graph recovery |

---

## C. Flyttet til andre projekter

| Emne | Projekt | Dokument |
|------|---------|----------|
| Fleet MVP scope | eira-fleet-control | [MVP_SCOPE_v0.1.md](../../eira-fleet-control/docs/MVP_SCOPE_v0.1.md) ? |
| Bundle-builder, `package-list.lock` | eira-fleet-control | [Sprint_Plan spor 3](../../eira-fleet-control/docs/Sprint_Plan_v0.1.md) |
| Fleet HA / DR, IT runbooks (Fleet) | eira-fleet-control | [Sprint_Plan spor 2�4](../../eira-fleet-control/docs/Sprint_Plan_v0.1.md) |
| Indt�gtsplan m�ned 3�6 | company | [Business Plan](../../company/EIRA_Business_Plan_Sprint_v0.1.md) |
| TCO-model | company | [Business Plan spor 3](../../company/EIRA_Business_Plan_Sprint_v0.1.md) |
| Pilot-selektion | company | [Business Plan spor 2](../../company/EIRA_Business_Plan_Sprint_v0.1.md) |
| "Hvad vi ikke lover" | company | [Business Plan spor 2](../../company/EIRA_Business_Plan_Sprint_v0.1.md) |
| DPA-skabelon | company | [Business Plan spor 2](../../company/EIRA_Business_Plan_Sprint_v0.1.md) |

---

## D. Produkt / UX (OS)

| ? | Emne | Handling |
|---|------|----------|
| ? | Rationale ved blokering (R2) | PoC f�r Explorer-polish |
| ✓ | Bruger-tr�ning | 2t onboarding — [Change Management](EIRA_Change_Management_Pilot_v0.1.md) §5 |
| ? | Multi-monitor / docking | Smoke-test reference-PC |
| ? | Print-workflow | CUPS smoke-test |

---

## E. Juridisk (OS-relevant)

| ? | Emne | Handling |
|---|------|----------|
| ? | GDPR retention audit (365 d) | ? Identity Spec |
| ? | GDPR sletning / anonymisering | Procedure for audit-events |
| ? | Forsikring FAQ | ? [company Business Plan](../../company/EIRA_Business_Plan_Sprint_v0.1.md) |
| ? | Udbudstekst-kladde | ? company spor 2 |

---

## F. Drift (endpoint)

| ? | Emne | Handling |
|---|------|----------|
| ✓ | Helpdesk L1–L2 | [Support Matrix v0.1](EIRA_Support_Matrix_v0.1.md) §4 |
| ? | Policy snapshot rollback | ? Policy Compiler |
| ? | OS runbooks (bruger) | Efter pilot |

---

## G. �kosystem

| ? | Emne | Handling |
|---|------|----------|
| ? | Adapter certificeringsproces | 1-side |
| ? | ECK ? EIRA OS bridge | [ECK_EIRA_OS_Bridge_v0.1.md](../../eck/docs/ECK_EIRA_OS_Bridge_v0.1.md) |
| ? | Adapter versionskompatibilitet | Efter f�rste bundle |
| ? | SIEM feltmapping (endpoint) | Intent Protocol |
| ✓ | Hybrid-first i salg | [Reality Check](EIRA_Strategic_Reality_Check_v0.1.md) §2 + [company Transition](../../../company/EIRA_Enterprise_Endpoint_Transition_v1.0.md) |

---

## H. Pilot-gates (OS-del)

F�lles gates (business + fleet): se [company Business Plan](../../company/EIRA_Business_Plan_Sprint_v0.1.md) og [Fleet MVP go/no-go](../../eira-fleet-control/docs/MVP_SCOPE_v0.1.md).

| ? | Gate (EIRA OS) |
|---|----------------|
| ? | Reference-hardware testet |
| ? | Entra OIDC + session demonstreret |
| ? | Intent Audit i Wazuh/SIEM |
| ? | VPN + EDR godkendt teknisk |
| ? | `eira-governance-agent` heartbeat til Fleet |

---

## I. Bevidst ikke her

- Fleet Console, bundle repo, staged rollout ? **eira-fleet-control**
- Indt�gt, TCO, pilot-kriterier ? **company**
- App Store, blockchain, non-profit nu ? ignorer

---

## Opsummering

| Spor | Ejerskab |
|------|----------|
| Brugeroplevelse + agent p� PC | **eira-os** (denne checklist) |
| Administration + update-flow | **eira-fleet-control** |
| Cashflow + pilot-udv�lgelse | **company** |

> **360° OS-konklusion:** Validation Plan + BCP Fallback er skrevet. Doc freeze — næste er **kode, VPN-test og Fase 0 gates** på reference-PC.

---

*EIRA OS 360� Gap Checklist v0.1 � opdater ved sprint review.*
