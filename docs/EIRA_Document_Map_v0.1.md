# EIRA — Document Map v0.1

**Status:** Navigationsindeks — læs dette før du dykker ned i specs  
**Dato:** 4. juli 2026  
**Formål:** Én side der svarer på *"hvilket dokument skal jeg læse?"*

> Fuld syntese på engelsk: [EIRA_Master_Reference_v1.0_EN.md](../../EIRA_Master_Reference_v1.0_EN.md)  
> Status audit: [specs/EIRA_360_Gap_Checklist_v0.1.md](specs/EIRA_360_Gap_Checklist_v0.1.md)  
> Handlingsplan: [Sprint_Plan_v0.1.md](Sprint_Plan_v0.1.md)

---

## Start her (3 dokumenter)

| Rolle | Læs først | Derefter |
|-------|-----------|----------|
| **Alle** | [Platform Principles](specs/EIRA_Platform_Principles_v1.0.md) | Document Map (denne) |
| **CIO / indkøb** | [Enterprise Endpoint Transition](../company/EIRA_Enterprise_Endpoint_Transition_v1.0.md) | [Strategic Reality Check](specs/EIRA_Strategic_Reality_Check_v0.1.md) |
| **Arkitekt / lead** | [OS Architecture Overview](specs/EIRA_OS_Architecture_Overview_v1.0.md) | [Cognitive Runtime v1.0](specs/EIRA_Cognitive_Runtime_v1.0.md) |
| **Udvikler** | [Desktop Architecture v1.0](specs/EIRA_Desktop_Architecture_v1.0.md) | [prototype/phase1/README.md](../prototype/phase1/README.md) |
| **Design / UX** | [UX Logic](specs/EIRA_User_Experience_Logic_v0.1.md) | [Situation UI Vision](specs/EIRA_Situation_UI_Vision_v0.1.md) |
| **IT drift** | [Support Matrix v0.1](specs/EIRA_Support_Matrix_v0.1.md) | [OSS Operations Model](specs/EIRA_OSS_Operations_Model_v0.1.md) |

---

## Spørgsmål → dokument

| Du spørger… | Læs |
|-------------|-----|
| Hvad er EIRA — og hvad er det ikke? | [Platform Principles](specs/EIRA_Platform_Principles_v1.0.md), [Technical Blueprint v7.0](specs/EIRA_Technical_Blueprint_v7.0.md) |
| Hvordan sælger vi det uden big bang? | [Enterprise Endpoint Transition](../company/EIRA_Enterprise_Endpoint_Transition_v1.0.md), [Reality Check](specs/EIRA_Strategic_Reality_Check_v0.1.md) |
| Hvad kan vi love om Windows? | [Windows Technical Parity](specs/EIRA_Windows_Technical_Parity_v0.1.md) (ærlige gaps) |
| Hvordan når vi Windows-paritet på sigt? | [Windows Parity Architecture](specs/EIRA_Windows_Parity_Architecture_v0.1.md) |
| Hvordan håndterer vi Ubuntu i enterprise? | [Ubuntu Integration](specs/EIRA_Ubuntu_Integration_v0.1.md) |
| Hvem ringer brugeren ved problemer? | [Support Matrix](specs/EIRA_Support_Matrix_v0.1.md), [Change Management Pilot](specs/EIRA_Change_Management_Pilot_v0.1.md) |
| Hvordan opdaterer og patcher vi? | [OSS Operations Model](specs/EIRA_OSS_Operations_Model_v0.1.md), [Update Release Train](../eira-fleet-control/docs/specs/EIRA_Update_Release_Train_v0.1.md) |
| Hvordan tester vi før pilot? | [Pilot Validation Plan](specs/EIRA_Pilot_Validation_Plan_v0.1.md), [Performance Acceptance](specs/EIRA_Performance_Acceptance_v0.1.md) |
| Hvad hvis EIRA fejler? | [BCP Endpoint Fallback](specs/EIRA_BCP_Endpoint_Fallback_v0.1.md) |
| Hvilken EDR skal vi vælge? | [EDR Partner Requirements](specs/EIRA_EDR_Partner_Requirements_v0.1.md) |
| Hvordan kompileres policy? | [Policy Compiler](specs/EIRA_Policy_Compiler_Architecture_v0.1.md) + [Release Train](../eira-fleet-control/docs/specs/EIRA_Update_Release_Train_v0.1.md) |
| Hvad er de største risici nu? | [Risk Sprint 0–1](specs/EIRA_Risk_Sprint_0-1_v0.1.md) |
| Hvad vinder/taberr vi på? | [Success/Failure Matrix](specs/EIRA_Success_Failure_Matrix_v0.1.md) |
| Hvordan prioriterer UI handlinger? | [Prioritization Heuristics](specs/EIRA_Prioritization_Heuristics_v0.1.md) |
| Relation confidence i grafen? | [Object Graph v0.3](specs/EIRA_Object_Graph_Specification_v0.3.md) |
| Hvordan skal Explorer se ud (nu)? | [UX Visual Language](specs/EIRA_UX_Visual_Language_v0.1.md) |
| Hvor går UI på sigt (Situation OS)? | [Situation UI Vision](specs/EIRA_Situation_UI_Vision_v0.1.md) |
| Scope closure / engineering gaps | [Scope Closure Engineering](specs/EIRA_Scope_Closure_Engineering_v0.1.md) |
| IPC kontrakter (AI prompts) | [Contract Prompt Framework](../contracts/EIRA_Contract_Prompt_Framework_v0.1.md), [prompts/](../contracts/prompts/) |
| Hvordan virker intent og tillid? | [Intent Protocol v1.1](specs/EIRA_Intent_Protocol_v1.1.md), [UX Logic](specs/EIRA_User_Experience_Logic_v0.1.md) |
| Hvad mangler stadig? | [360° Gap Checklist](specs/EIRA_360_Gap_Checklist_v0.1.md) |

---

## Operational companions (kerne-specs)

Hvert strategidokument har **drift-, test- og roadmap-følgesvend**. Læs dem sammen — ikke isoleret.

| Kerne-spec | Operational companions |
|------------|------------------------|
| Object Graph v0.3 | Identity Strategy §10, Cognitive Runtime §2.1, Trust layer |
| Technical Blueprint v7.0 | Cognitive Runtime, Sprint Plan, Pilot Validation, Performance Acceptance |
| Policy Compiler | OSS Operations Model, Update Release Train, Fleet Control |
| Ubuntu Integration | Support Matrix, OSS Operations, VPN Matrix, BCP Fallback |
| Windows Parity Architecture | Windows Technical Parity, Reality Check, Enterprise Transition |
| UX Logic | UX Visual Language, Prioritization Heuristics, Desktop Architecture |
| Risk Sprint 0–1 | Reality Check, Pilot Validation, BCP, Success/Failure Matrix |
| Success/Failure Matrix | Business Plan Sprint, Performance Acceptance, Change Management |
| EDR Partner Requirements | Pilot Validation §security, OSS Operations, Intent Audit (Fleet) |

---

## Projekt-grænser

| Projekt | Ejer | Index |
|---------|------|-------|
| **eira-os** | Endpoint, runtime, Explorer | [Sprint Plan](Sprint_Plan_v0.1.md) |
| **eira-fleet-control** | IT console, bundles, rollout | [fleet Sprint Plan](../eira-fleet-control/docs/Sprint_Plan_v0.1.md) |
| **company/** | Indtægt, TCO, CIO-pitch | [company/README.md](../company/README.md) |
| **eck/** | Compatibility kernel (separat produkt) | [eck/docs/README.md](../eck/docs/README.md) |
| **prototype/phase1** | Reference-kode | [phase1/README.md](../prototype/phase1/README.md) |

---

## Vedligeholdelse

- Opdater denne fil når et **nyt normativt** dokument tilføjes — ikke for hver draft.
- Companion-footers i kerne-specs peger tilbage hertil og til relevante operational docs.
- **Doc freeze:** Kun navigation + P0-specs + kode — undgå nye masterdokumenter.

---

*EIRA Document Map v0.1*
