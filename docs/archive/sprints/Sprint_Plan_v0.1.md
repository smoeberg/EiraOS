# EIRA OS � Sprint Plan v0.1

**Status:** Handlingsplan (endpoint)  
**Dato:** 26. juni 2026  
**Horisont:** Sprint 0 (uge 0�4) ? pilot-commit  
**Relateret:** [specs/EIRA_360_Gap_Checklist_v0.1.md](specs/EIRA_360_Gap_Checklist_v0.1.md), [eira-fleet-control Sprint Plan](../../eira-fleet-control/docs/Sprint_Plan_v0.1.md)

Administration, bundles og rollout � se **[eira-fleet-control](../../eira-fleet-control/)**.  
Indt�gt, TCO, pilot-selektion � se **[company](../../company/EIRA_Business_Plan_Sprint_v0.1.md)**.

---

## Spor 1 � Uge 1�4 (beslut + skriv kort)

| ? | Leverance | Type | Output |
|---|-----------|------|--------|
| ? | **Sprint 0 vertical slice** | Beslutning | Max 6 komponenter � skriftlig liste |
| ◐ | **EDR-beslutning** | Beslutning | [EDR Partner Requirements](specs/EIRA_EDR_Partner_Requirements_v0.1.md) — Wazuh-only vs. MDE/CrowdStrike (uge 4) |
| ? | **VPN-test** | Test | Mini-matrix: klient � gateway |
| ? | **F�rste git commit** | Kode | `eira-governance-agent` eller enroll stub |
| ? | **50 intentioner** til R2 | Data | Input til Rationale PoC |
| ? | **Doc freeze** | Process | Kun kode + plan-opdateringer |

---

## Spor 2 � F�r pilot-commit

| ? | Leverance | Type | Output |
|---|-----------|------|--------|
| ✓ | **Support Matrix v0.1** | 1-pager | [EIRA_Support_Matrix_v0.1.md](specs/EIRA_Support_Matrix_v0.1.md) |
| ✓ | **Desktop Architecture** | Spec | [EIRA_Desktop_Architecture_v1.0.md](specs/EIRA_Desktop_Architecture_v1.0.md) |
| ✓ | **Strategic Reality Check** | Spec | [EIRA_Strategic_Reality_Check_v0.1.md](specs/EIRA_Strategic_Reality_Check_v0.1.md) |
| ◐ | **VPN Compatibility Matrix** | Skabelon | [EIRA_VPN_Compatibility_Matrix_v0.1.md](specs/EIRA_VPN_Compatibility_Matrix_v0.1.md) |
| ✓ | **Pilot Validation Plan** | Spec | [EIRA_Pilot_Validation_Plan_v0.1.md](specs/EIRA_Pilot_Validation_Plan_v0.1.md) |
| ✓ | **BCP Endpoint Fallback** | Spec | [EIRA_BCP_Endpoint_Fallback_v0.1.md](specs/EIRA_BCP_Endpoint_Fallback_v0.1.md) |
| ✓ | **Change Management Pilot** | Spec | [EIRA_Change_Management_Pilot_v0.1.md](specs/EIRA_Change_Management_Pilot_v0.1.md) |
| ✓ | **Performance Acceptance** | Spec | [EIRA_Performance_Acceptance_v0.1.md](specs/EIRA_Performance_Acceptance_v0.1.md) |
| ? | **Intent Audit demo** | Demo | CEF/Wazuh live p� reference-PC |
| ? | **NIS2 ? Intent Audit** 1-pager | Salg | Til CISO |
| ? | **Notifikation ? handlingskort** | Spec | Event-flow: adapter ? agent ? kort |
| ✓ | **Prioriteringsheuristik** | Spec | [EIRA_Prioritization_Heuristics_v0.1.md](specs/EIRA_Prioritization_Heuristics_v0.1.md) |
| ✓ | **UX Visual Language** | Spec | [EIRA_UX_Visual_Language_v0.1.md](specs/EIRA_UX_Visual_Language_v0.1.md) | ��n ting skriger� |
| ? | **Tom Object Graph / first boot** | UX | Script eller wireframe dag 1 |
| ? | Legacy Bridge spike | Spike | Go/no-go |

---

## Spor 3 � Med kode

| ? | Leverance | Type | Output |
|---|-----------|------|--------|
| ? | **Phase 1–2 prototype** | Kode | `prototype/phase1` — API + React dashboard |
| ? | `eira-governance-agent` | Kode | Fleet Agent Protocol client |
| ? | `eira-firstboot.service` | Kode | Factory Enroll ? `/v1/enroll` |
| ? | Policy apply backends (stub) | Kode | Align Policy Compiler |
| ? | OSS CORE p� image | Kode | Per [OSS Manifest](specs/EIRA_OSS_Integration_Manifest_v0.1.md) |

---

## Spor 4 � Kan vente

| ? | Leverance | Note |
|---|-----------|------|
| ? | Support Matrix v1.0 (bred hardware) | Efter reference-PC pilot |
| ? | Lifecycle Policy (fuld) | Delvist i Release Train (fleet) |
| ? | WCAG testplan | F�r bruger-pilot |
| ? | Pen-test program | Efter vertical slice |
| ? | Object Graph SQLite recovery | Local-first backup |

---

## Vertical slice (forslag � godkend i uge 1)

Max 6 komponenter der krydser OS + Fleet:

1. `eira-governance-agent` � heartbeat  
2. Fleet API � enroll + desired-state  
3. Entra OIDC + session (`eira-identityd`)  
4. Intent Audit ? Wazuh  
5. Factory Enroll � 1 PC zero-touch  
6. Minimal Explorer eller status-sk�rm (valgfri 6.)

---

## Milestones

| Uge | Milestone |
|-----|-----------|
| 1 | Vertical slice skriftligt godkendt |
| 2 | F�rste commit + agent stub |
| 4 | Entra login + audit event |
| 6 | Enroll end-to-end med Fleet |
| 8 | Rationale PoC (R2) |

---

*EIRA OS endpoint � ikke Fleet Console eller bundle-builder.*
