# EiraOS Master Plan 1.0

**Status:** Draft — governing implementation plan; requires repository audit and validation  
**Date:** 2026-10-21  
**Target platform:** Ubuntu Desktop 26.04 LTS, with exact 26.04.x image pinned for integration testing  
**Branch:** `feature/system-api-terminal-foundation`

> **Fundamental rule: AI'en foreslår. Gaten afgør. Systemet udfører.**

This plan connects the product vision, architecture, existing repository, implementation sequence, tests, and release evidence. It is a planning authority, not proof that listed components are implemented. Detailed contracts remain in the linked specifications and architecture documents.

## 1. What this plan governs

The master plan is the index and sequencing authority for:
- Product scope and user experience
- Architecture and presentation/logic separation
- AI and language/model adapters
- Gate Kernel, consent, authorization, and audit
- EDP contracts and IPC
- EiraSystemAPI and Ubuntu capability adapters
- Desktop GUI, settings, accessibility, and localization
- Real Linux terminal
- Identity, object graph, context, presence, evidence, and persistence
- Unified communication and provider adapters
- Local-first inference and optional cloud use
- Cross-device trust, sync, and revocation
- Packaging, installation, upgrades, recovery, CI, and release criteria

This plan does not replace detailed specifications. If documents conflict, record the discrepancy, identify the owner of the contract, resolve it explicitly, and add a regression test where applicable. Do not silently choose whichever document is newest.

## 2. Product goal

EiraOS is an intent-driven operating-system experience on Ubuntu. It combines a modern, coherent GUI with normal desktop capabilities, a real terminal, safe AI-assisted workflows, stable EiraOS-owned APIs, and a conversation-first communication experience.

Ubuntu provides the supported operating-system substrate. EiraOS owns its UX, stable contracts, policy, orchestration, and user-facing behavior.

### Non-negotiable principles

1. Presentation and business/system logic remain separate.
2. Models can propose intent and parameters but cannot authorize or execute actions.
3. Every protected action passes the authoritative Gate immediately before execution.
4. No generic privileged `run(command)` system API.
5. Typed, versioned EiraSystemAPI contracts sit above replaceable platform adapters.
6. Native Ubuntu APIs and D-Bus are preferred where suitable; command-line adapters are narrow, explicit exceptions.
7. Native authorization, including Polkit where applicable, is respected; no hidden privilege escalation.
8. The terminal is a real PTY for the logged-in user, not a simulated command box; no root/sudo by default.
9. Local-first inference; no silent cloud escalation.
10. External communication transports remain distinct. No silent rerouting that changes recipient, cost, privacy, or delivery semantics.
11. A proposal is not acceptance; a UI success message is not proof of persistence or delivery.
12. Specs, mocks, UI controls, and daemon names are not implementation evidence.
13. No user dead ends: misunderstanding, denial, delay, or unsupported integration must have a truthful explanation and a safe next step wherever one exists.
14. Intent is not the only route: important capabilities must remain discoverable and manually accessible.
15. Spatial 3D is the primary visual identity, not a mandate; dense and conventional workflows must retain efficient 2D and accessibility paths.

## 3. Status vocabulary and evidence

Use the same vocabulary across plans, code review, and capability matrix:

- **Missing** — required implementation or evidence does not exist.
- **Unclear** — repository evidence is insufficient or contracts conflict.
- **Partially implemented** — some path exists, but acceptance criteria are incomplete.
- **Implemented** — code and relevant automated tests exist and pass in the recorded environment.
- **Verified on target Ubuntu** — implemented and additionally passes reproducible integration tests on the pinned Ubuntu 26.04.x target.
- **Blocked** — a documented dependency, safety issue, platform limitation, or unresolved product decision prevents progress.
- **Deferred** — intentionally outside the current release scope, with rationale.

Every nontrivial work item must record: ID, owner/component, dependencies, implementation files, acceptance criteria, tests, evidence link, status, and blockers. Never infer a status from documentation alone.

## 4. Workstreams

### WS-0 — Repository truth and contract reconciliation
- Inventory the actual repository, entry points, daemons, IPC paths, UI routes, persistence, tests, packaging, and CI.
- Compare code with EDP 1.0, EDP schema, Gate Kernel 1.0, AI Interface 1.0, architecture baseline, and capability matrix.
- Record exact file/function/test evidence for every claim.
- Resolve duplicate, stale, and conflicting documentation.
- Reconcile the README's Ubuntu 24.04 claims with the 26.04 LTS target; do not claim 26.04 support before testing.
- Deliverable: evidence-based implementation audit and prioritized gap list.

### WS-1 — Security and Gate Kernel
- Make the Gate the only authoritative protected-action boundary.
- Validate the complete enriched EDP envelope at the Gate.
- Bind confirmation to an immutable action, target, and parameter set; reject changed or stale plans.
- Recheck session, assurance, consent, authorization, current state, and policy at execution time.
- Default unknown actions and operations to deny; unknown reversibility is treated as irreversible.
- Keep policy-derived reversibility and permissions outside model-controlled payloads.
- Record audit events and distinguish rejected, pending-consent, pending-authentication, failed, partially completed, and completed outcomes.
- Add regression tests for bypasses, concurrency, duplicates, stale confirmations, missing consent, insufficient assurance, changed targets, and partial failure.

### WS-2 — Contracts, IPC, and service reliability
- Establish canonical error, status, timeout, cancellation, correlation, and version-mismatch semantics.
- Validate IPC message schemas at both producer and consumer boundaries.
- Define identity/object references, idempotency keys, and audit correlation.
- Test malformed messages, stale state, duplicate requests, process restarts, and unavailable daemons.
- Keep UI transport details out of domain logic.

### WS-3 — EiraSystemAPI and Ubuntu PC Core
- Define stable, typed, versioned EiraSystemAPI operations and capability discovery.
- Build and maintain the Ubuntu capability coverage matrix.
- Verify candidate APIs, package dependencies, D-Bus interfaces, Polkit behavior, and permissions on the exact target image.
- Start with read-only NetworkManager status; then a bounded, approved-scope file listing/read operation.
- Expand carefully to network settings, Bluetooth, audio, displays, power, storage, updates, services/logs, printers, users, input, locale, accessibility, camera/media, firewall, drivers, and firmware.
- Destructive or disruptive operations require explicit policy, clear UI, authorization, confirmation where appropriate, and failure/recovery tests.
- Evaluate Cockpit only feature by feature as optional replaceable reuse; never make it the universal API layer.
- Mark server/enterprise features optional unless product scope explicitly includes them.

### WS-4 — Modern desktop UX and settings
- Audit the existing React/Tauri UI and IPC bridge before redesigning.
- Keep presentation separate from domain decisions and OS adapters.
- Define navigation, windowing/multitasking, settings taxonomy, notifications, empty/loading/error/permission states, keyboard and touch behavior, and accessibility.
- Build settings against EiraSystemAPI capabilities rather than direct shell commands from UI components.
- Provide graceful behavior when hardware, a daemon, a permission, or an optional capability is unavailable.
- Validate localization, including language fallback and user-visible terminology.
- Do not declare a settings area complete until its underlying operation and failure states are tested.

### WS-5 — AI and language layer
- Keep model/provider adapters replaceable behind the AI Interface.
- Separate language detection, intent parsing, ambiguity resolution, planning, execution policy, and presentation.
- Treat model output and `allowed_actions` as proposals, never authorization.
- Route proposed actions through schema validation and Gate.
- Define model capability requirements, offline behavior, resource limits, latency targets, licensing, and model artifact provenance.
- Evaluate candidate models using a repeatable multilingual benchmark; do not select based only on marketing claims or a single demo.
- No cloud fallback without explicit user-visible policy and consent.

### WS-6 — Identity, object graph, context, presence, evidence
- Audit existing daemons and persistence before adding new ones.
- Use real identity and object resolution; never hardcode demo identities or project IDs as production behavior.
- Define confidence, ambiguity, no-match, and multiple-match behavior.
- Persist state before reporting success.
- Track evidence and provenance for important assertions and system outcomes.
- Add idempotency and recovery for retries and partial failures.

### WS-7 — Vertical end-to-end demo
- Select one narrow, representative user workflow and define its exact scope.
- Resolve people and objects through real lookup.
- Exercise the full chain: UI → AI proposal → EDP validation → Gate → typed service/executor → persistence → audit → notification/UI state.
- Distinguish proposed commitments from recipient-accepted commitments.
- Freeze time and timezone in tests; specify date-resolution rules.
- Test zero, one, and multiple matches; ambiguous input; denied authorization; duplicate requests; and partial failure.
- Use three test layers: contract/model tests without side effects; Gate/executor tests with a fake executor; end-to-end tests with persisted-state and audit verification.
- A demo is accepted only when evidence confirms the complete chain, not just a successful UI animation.

### WS-8 — Real terminal
- Implement a PTY-backed terminal through the Tauri/Rust boundary.
- Run as the logged-in user with normal OS permissions; no implicit root or sudo.
- Support terminal resize, Unicode, interactive TUI applications, stdin/stdout/stderr, signals, exit status, session lifecycle, cleanup, and concurrent sessions.
- Keep terminal commands separate from typed EiraSystemAPI actions; the terminal is not a privileged API bypass.
- Test process termination, app shutdown, permission boundaries, long-running processes, and resource cleanup.

### WS-9 — Communications and EDP
- Preserve EDP as an internal semantic protocol, not a replacement for SMTP, SMS, SIP, XMPP, or proprietary messaging protocols.
- Define provider adapters and capability/transport metadata.
- Keep recipient, account, privacy, cost, delivery, and transport semantics visible when material.
- Do not silently reroute messages or represent a proposal as accepted.
- Test delivery receipts, retries, duplicates, offline states, provider errors, and partial multi-provider failure.
- Add providers only when contracts, security, and user experience are defined.

### WS-10 — Cross-device, sync, and trust
- Define device identity, enrollment, trust levels, revocation, conflict resolution, and offline behavior.
- Make sync scope and cloud processing explicit and user-controllable.
- Test lost/revoked devices, replay, duplicate delivery, conflicting edits, and interrupted synchronization.
- Keep this work behind foundational Gate, identity, and persistence requirements.

### WS-11 — Release engineering and lifecycle
- Pin supported Ubuntu image/package versions for CI and target integration testing.
- Define installation, update, rollback, migration, backup/recovery, uninstall, logs, diagnostics, and support policy.
- Audit dependency and model licenses, supply-chain provenance, permissions, secrets, and data retention.
- Add accessibility, localization, performance, resource-use, crash recovery, and security regression gates.
- Publish a capability/support matrix that distinguishes implemented from target-verified behavior.

## 5. Delivery phases and exit gates

Phases are ordered by dependency and risk, not calendar promises. Parallel work is allowed only where dependencies are satisfied.

| Phase | Focus | Exit gate |
|---|---|---|
| 0 | Repository audit and contract reconciliation | Every critical component has evidence-based status; conflicts and blockers are logged |
| 1 | Gate Kernel hardening | Security regression suite passes; protected action cannot bypass Gate |
| 2 | IPC contracts and typed capability discovery | Versioning/errors/idempotency defined; read-only NetworkManager smoke test works on target image |
| 3 | First bounded system operation | Approved-scope read/list operation has authorization, tests, audit, and clear failure behavior |
| 4 | Complete vertical workflow | Real lookup, Gate, execution, persistence, audit, and truthful UI status verified end to end |
| 5 | Desktop UX and PC Core expansion | Settings/UI use stable contracts; each capability has passing tests and matrix evidence |
| 6 | AI/model maturity | Model adapters and multilingual evaluation are repeatable; offline/cloud rules enforced |
| 7 | PTY terminal | Interactive terminal lifecycle and permission tests pass on target |
| 8 | Communications and provider adapters | Transport semantics, delivery status, consent, retries, and partial failures tested |
| 9 | Cross-device trust/sync | Enrollment, revocation, conflict, offline, and replay tests pass |
| 10 | Release candidate | CI, target-image tests, packaging, upgrade/recovery, licensing, security, accessibility, and support docs pass |

Phases may be re-sequenced only by recording the dependency or product rationale and preserving all safety gates.

## 6. Definition of done for every feature

A feature is not done until all applicable criteria are met:

1. User story and scope are explicit.
2. Domain contract and versioning are defined.
3. Presentation and logic are separated.
4. Authorization, consent, threat model, and failure behavior are reviewed.
5. Implementation is present in the repository.
6. Automated unit/contract/regression tests pass.
7. Integration tests pass for affected components.
8. UI reports real state, including pending, denied, failed, partial, and completed states.
9. Persistence/audit evidence supports any claimed success.
10. Documentation and coverage matrix are updated.
11. Target Ubuntu verification is recorded when claimed.
12. Known limitations and unsupported configurations are documented.

## 7. Required project artifacts

- This master plan: scope, dependencies, phases, and exit gates.
- Architecture baseline: component boundaries and invariants.\n- [GUI Product and Implementation Plan 1.0](architecture/eiraos-gui-product-and-implementation-plan-1.0.md): shell, screens, settings, interaction states, design system, frontend boundaries, accessibility, and GUI acceptance criteria.
- [Intuitive 3D Desktop prototype](architecture/prototypes/eiraos-intuitive-3d-desktop.html): agreed visual baseline for the spatial workspace and application-object experience; a concept prototype, not production functionality.
- GUI plan section 5.1 defines UX resilience, intent repair, discoverability, Gate denial explanations, hybrid desktop integration, latency targets, undo/recovery, identity context, and priority failure-path tests.
- Gate Kernel, AI Interface, EDP specification and schema: normative contracts.
- Ubuntu PC API catalog and coverage matrix: capability-level research and verification.
- Code-review checklist: each requirement mapped to files, functions, tests, and evidence.
- Test plan: unit, contract, integration, security regression, target-image, and E2E suites.
- Decision log: material architecture/product decisions, rationale, alternatives, and consequences.
- Risk/blocker register: severity, likelihood, mitigation, owner, and exit criteria.
- Release checklist: packaging, upgrade/recovery, security, accessibility, localization, licenses, and support matrix.

## 8. Immediate next actions

1. Audit actual code against Gate Kernel, AI Interface, EDP/schema, and the current IPC contracts.
2. Produce a code-review checklist with statuses **Implemented and verified / Partially implemented / Missing / Unclear**, each with exact file/function/test evidence.
3. Reconcile contradictory documentation, beginning with Ubuntu version and daemon/IPC architecture claims.
4. Run existing focused tests and record actual results; add missing security regression tests.
5. Verify the pinned Ubuntu 26.04.x environment and perform a read-only NetworkManager integration smoke test.
6. Choose and implement the first bounded end-to-end vertical only after the Gate and contract prerequisites pass.
7. Before broad GUI expansion, prototype and test the priority UX failure paths: ambiguous intent repair, understandable Gate denial with no bypass, and a normal file/browser/app workflow crossing the spatial workspace.
8. Measure interaction and intent latency by stage; treat initial UX budgets as targets to validate, not assumed performance.
7. Keep the PR open and unmerged until review and required checks are complete.

## 9. Open decisions — must be resolved with evidence

- Exact Ubuntu 26.04.x image, desktop session, and supported hardware baseline.
- Which existing daemons/contracts are retained, consolidated, or replaced after code audit.
- The first end-to-end demo workflow and its acceptance criteria.
- Supported languages and benchmark thresholds for model evaluation.
- Initial PC Core versus PC Optional scope.
- Communication providers and the exact first supported transport.
- Persistence, backup, and recovery contract for the first release.
- Resource and performance budgets for local inference.
- Release packaging and update mechanism.

Until resolved, mark dependent work as **Unclear** or **Blocked** rather than guessing.

## 10. Related documents

- [Architecture Baseline 1.0](architecture/eiraos-architecture-baseline-1.0.md)
- [Ubuntu PC API Coverage Matrix](architecture/ubuntu-pc-api-coverage-matrix.md)
- [Gate Kernel 1.0](../specs/GATE-KERNEL-1.0.md)
- [AI Interface 1.0](../specs/AI-INTERFACE-1.0.md)
- [EDP 1.0](../specs/EDP-1.0.md)
- [Specifications index](../specs/README.md)
