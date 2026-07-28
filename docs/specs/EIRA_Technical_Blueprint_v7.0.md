# EIRA OS v2.0 — Technical Blueprint v7.0

**Status:** Cognitive Runtime Evolution  
**Dato:** 3. juli 2026  
**Core Team:** Soeren Moeberg (Owner), Ukrainian Dev Team (2 Devs), AI Architect  
**Full spec:** [EIRA_Cognitive_Runtime_v1.0.md](EIRA_Cognitive_Runtime_v1.0.md)

---

## 0. Strategic Position

EIRA is an **enterprise platform built on Ubuntu LTS**.

Version 7 evolves the **runtime** into a **Cognitive Runtime Stack** — adding trust-aware interfaces, reasoning, journeys, and enterprise intelligence — while preserving the Ubuntu foundation and Governance plane.

> **Ubuntu remains the operating system. EIRA evolves the enterprise runtime.**

EIRA does not replace Linux. EIRA makes Linux usable for knowledge workers and administrable for IT.

EIRA must not behave like a new operating system. v7 strengthens the layer on top of Ubuntu — it does not redefine the whole product.

---

## 1. Full Architecture

```text
Ubuntu LTS
        │
────────┼──────────────────────────
        │
Open Source Services
(CUPS, systemd, NM, Flatpak, SSSD …)
        │
────────┼──────────────────────────
        │
EIRA Cognitive Runtime
• Cognitive Interface (trust-aware dashboard)
• Reasoning · Intent · Journey
• Trust & Evidence · Agency
• Knowledge · Temporal · Object Graph
• Capability (first-class)
• Transport (Adapters) · Identity Bridge
• Crypto · Local-First Storage
        │
────────┼──────────────────────────
        │
Governance (unchanged)
Fleet · Compliance · Intent Audit · Portal
```

---

## 2. The Differentiator

Most AI systems:

```text
Prompt → LLM → Answer
```

EIRA:

```text
Intent → Capability → Adapter → System
```

**Capability Layer** is the contract between intention and technology. Systems can be swapped without rewriting the agent.

---

## 3. Cognitive Runtime Stack (14 layers, bottom-up)

| # | Layer | Responsibility |
|---|-------|----------------|
| 1 | Local-First Storage | Secure persistent cache |
| 2 | Cryptographic Layer | Signing, local-first security |
| 3 | Transport Abstractor | Multi-protocol adapters |
| 4 | Identity Bridge | Entra + eID (eIDAS 2.0) |
| 5 | Object Graph | Person, Document, Interaction, … |
| 6 | Knowledge Graph | Org memory, skills |
| 7 | Temporal Graph | Validity windows, time-travel queries |
| 8 | Agency Layer | Traceability (Who?) |
| 9 | Trust & Evidence | Probability 0–100%, sources |
| **10** | **Capability Layer** | **What can each system do?** |
| 11 | Journey Orchestrator | Super/Sub-Journeys |
| 12 | Intent Engine | Purpose detection (Why?) |
| 13 | Reasoning Engine | Inference, rationale for UI |
| 14 | Cognitive Interface | Decision dashboard (not file browser) |

---

## 4. Core Primitives

### A. Trust Levels

| Level | Score | Meaning |
|-------|-------|---------|
| Unconfirmed | 0–20% | AI guess, unknown source |
| Indicative | 21–50% | Single weak source |
| Probable | 51–79% | Multiple sources, unverified |
| Confirmed | 80–95% | Manually verified or signed |
| Indisputable | 96–100% | Cryptographically proven |

Trust replaces the file browser as the primary navigation metaphor.

### B. Intent Taxonomy (extends Intent Protocol v0.1)

Categories (purpose) alongside existing actions (verbs):

- `DECISION` — Approve, Reject, Postpone
- `DISCUSSION` — Explore, Brainstorm, Clarify
- `INFORMATION` — Briefing, Status, Report
- `ACTION` — Agreement, Promise, Task
- `RELATION` — Build, Maintain, Close

### C. Temporal Graph

Validity windows on relations. Query: *"Who was Lars relative to Mette in March 2024?"*

### D. Journey UX

```text
Budget 2027
████░░░░
2 of 5 steps

✓ Controller
✓ Manager
→ You (CFO)
```

---

## 5. Prototype Roadmap

Runs on **Ubuntu reference PC** — not an isolated mockup.

| Phase | Weeks | Deliverable |
|-------|-------|-------------|
| **1** | 1–3 | Trust + Journey prototype (Python/FastAPI) |
| **2** | 4–6 | Intent + Agency (local Mistral); Capability manifest |
| **3** | 7–9 | Cognitive Dashboard (Tauri/React); `eira-shell` slice |

Governance track (`eira-governance-agent`, Fleet) runs in parallel.

---

## 6. Mapping to Existing Specs

| Existing | v7 |
|----------|-----|
| Platform Principles | Unchanged — foundational |
| Lag 0 Governance | Unchanged |
| Lag 1–8 Runtime | Evolved into Cognitive Runtime (see full spec) |
| Intent Protocol v0.1 | Actions preserved; category added (see v1.1) |
| Object Graph v0.1 | + validity windows (see v0.2) |
| Intent Audit | Unchanged — strengthened by Trust layer |

---

## Relaterede dokumenter (operationalisering)

| Spørgsmål | Dokument |
|-----------|----------|
| Fuld runtime-stack | [Cognitive Runtime v1.0](EIRA_Cognitive_Runtime_v1.0.md) |
| Fase 0/1 test | [Pilot Validation Plan](EIRA_Pilot_Validation_Plan_v0.1.md) |
| Performance | [Performance Acceptance](EIRA_Performance_Acceptance_v0.1.md) |
| Sprint og kode | [Sprint Plan](../Sprint_Plan_v0.1.md), [phase1 prototype](../../prototype/phase1/README.md) |
| Navigation | [Document Map](../EIRA_Document_Map_v0.1.md) |

---

*EIRA Technical Blueprint v7.0 — Confidential*
