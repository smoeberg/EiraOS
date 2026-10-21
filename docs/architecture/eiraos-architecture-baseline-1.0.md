# EiraOS Architecture Baseline 1.0

**Status:** Integrated architecture baseline for review; implementation is evidence-gated  
**Date:** 2026-10-21  
**Primary platform:** Ubuntu Desktop 26.04 LTS; integration tests use the latest available 26.04.x point release  
**Applies to:** Desktop shell, AI/language layer, Gate Kernel, EDP, system API, communications, terminal, local services, and future companion clients

> **Fundamental rule: AI'en foreslår. Gaten afgør. Systemet udfører.**

This document is the architectural map for EiraOS. The linked specifications define the detailed contracts; this baseline explains how they fit together, which boundaries are mandatory, how work should be sequenced, and what evidence is required before a feature may be called implemented.

**Status discipline:** architecture text and schemas are not implementation. A component is not considered implemented merely because a daemon name, UI control, spec, mock, or plan exists. Claims of implementation require code and automated tests; claims of target-platform verification additionally require reproducible integration evidence from Ubuntu 26.04.x.

## 1. Product intent

EiraOS is an intent-driven operating-system experience built on Ubuntu. People should be able to work through language, conversations, people, objects, tasks, applications, and settings without needing to understand every underlying application or protocol.

The experience combines:

- A modern, coherent interface inspired by the usability and touch interaction patterns of iPadOS and Android, without copying their proprietary implementation.
- The power of a real desktop: windows, multitasking, files, applications, keyboard/mouse/touch, and accessibility.
- A real interactive Linux terminal for advanced users.
- AI-assisted language understanding and task planning, with no AI authority to grant permissions or bypass execution policy.
- One stable EiraOS contract layer above replaceable Ubuntu services and provider integrations.
- A conversation-first communication experience that does not pretend external networks have become one protocol.
- Local-first processing and user control over connected accounts, synchronization, and any cloud processing.

The design target is not a reskinned traditional Ubuntu desktop. Ubuntu supplies the supported operating-system substrate; EiraOS owns its interaction model, contracts, policy, and product experience.

## 2. Non-negotiable architectural invariants

1. **Gate authority:** no AI-proposed protected action may reach an executor without the authoritative Gate path.
2. **Presentation/logic separation:** React and other UI layers render state and express user intent. They do not own domain policy, credentials, privileged shell calls, or provider protocols.
3. **EiraOS-owned contracts:** UI and domain logic depend on stable, versioned EiraOS contracts—not directly on one Ubuntu service, Cockpit internals, model provider, or messaging provider.
4. **Replaceable adapters:** Ubuntu services, model runtimes, communication providers, and optional Cockpit integrations are replaceable behind published interfaces.
5. **Fail closed:** missing, stale, malformed, ambiguous, unauthorized, or unverified decisions do not execute.
6. **Consent is distinct from authorization:** a user's confirmation cannot grant Linux permissions, and Linux permission cannot substitute for user consent.
7. **Fresh-state check:** permissions, session, resource identity, and relevant state are rechecked immediately before protected execution.
8. **No generic privileged command API:** EiraSystemAPI must not expose `run(command)` or arbitrary privileged shell execution.
9. **Honest outcomes:** distinguish proposed, pending, accepted, queued, delivered, succeeded, failed, unknown, and partially completed states. Never report a requested or queued action as completed.
10. **Local-first, no silent cloud escalation:** local inference is the default. Cloud processing requires explicit, policy-checked user choice and data-scope disclosure.
11. **Evidence over claims:** unsupported hardware, unavailable services, permission denial, and unverified behavior are represented explicitly.
12. **No silent material rerouting:** communication fallback that changes recipient, privacy, cost, delivery semantics, or user expectations requires consent or a clear policy-approved choice.
13. **Security is deterministic:** model confidence, JSON-schema constrained output, trust scores, and UI colors do not establish authorization or truth.
14. **Server functions are not default desktop scope:** Server/Enterprise capabilities require explicit product approval and are not enabled by default.
15. **Testability:** domain rules must be testable without React, display server, real hardware, external network, or a production account.

## 3. System context and dependency direction

Logical view (the diagram describes intended boundaries, not a claim that every component exists today):

```text
┌─────────────────────────────────────────────────────────────────┐
│ Experience layer                                                 │
│ EiraOS shell · home/workspace · settings · communication · PTY   │
│ Presentation only: view state, accessibility, interaction        │
└───────────────────────────────┬─────────────────────────────────┘
                                │ typed UI commands / view models
┌───────────────────────────────▼─────────────────────────────────┐
│ Application and domain layer                                     │
│ Use cases · intent orchestration · object/context workflows      │
│ Conversation state · capability policy · explicit state machines│
└───────────────────────────────┬─────────────────────────────────┘
                                │ EiraOS-owned versioned contracts
┌───────────────────────────────▼─────────────────────────────────┐
│ Contract and security boundary                                   │
│ AI Interface · EDP · Gate Kernel · EiraSystemAPI · Comm API      │
│ Schema/semantic validation · auth · consent · idempotency · audit│
└───────────────┬────────────────────┬──────────────────┬──────────┘
                │                    │                  │
        ┌───────▼────────┐   ┌───────▼────────┐  ┌──────▼──────────┐
        │ Model adapters │   │ OS adapters    │  │ Provider/route  │
        │ local runtime  │   │ Ubuntu/D-Bus   │  │ adapters        │
        └───────┬────────┘   └───────┬────────┘  └──────┬──────────┘
                │                    │                  │
        ┌───────▼────────┐   ┌───────▼────────┐  ┌──────▼──────────┐
        │ EiraLang /     │   │ Ubuntu 26.04   │  │ SMTP/IMAP,      │
        │ EiraAI models  │   │ Linux services │  │ Matrix, SIP,    │
        │                │   │ kernel/drivers │  │ provider APIs…  │
        └────────────────┘   └────────────────┘  └─────────────────┘

Cross-cutting: identity/session · audit/event history · localization
privacy/secret handling · capability discovery · tests/observability
```

Dependencies point inward toward EiraOS-owned contracts. A replaceable adapter must not force a rewrite of the GUI or domain logic. The UI must never call arbitrary D-Bus methods, privileged system commands, or provider APIs directly.

## 4. Main architectural subsystems

### 4.1 Experience and presentation

Owns the visual design system, navigation, workspace, settings surfaces, conversation UI, notifications, file browsing, app switching, terminal presentation, accessibility, responsive behavior, and local view state.

Requirements:

- Simple by default; advanced Linux controls remain accessible.
- Consistent design language, keyboard/mouse/touch navigation, focus handling, screen-reader support, scalable text, reduced motion, localization and RTL readiness.
- Each visible control is backed by a real capability or visibly marked unavailable/in development.
- UI states distinguish loading, confirmation required, denied, unavailable, failed, partial, and verified success.
- UI code sends typed intent to application services and renders returned state; it does not parse human-readable shell output or implement authorization.
- The terminal UI is presentation for a real PTY session; it is not a privileged system-management API.

Normative detail: [Separation of Presentation and Logic](separation-of-presentation-and-logic.md) and [EiraOS Design Principles](eiraos-design-principles.md).

### 4.2 Eira Language Layer and AI interface

Language is a system-wide capability, not a collection of screen-specific model calls.

**EiraLang** interprets user language, detects/uses language hints, extracts intent and entities, and may translate or normalize text into a typed intermediate representation. It does not know EDP action types and cannot execute actions.

**EiraAI** turns the validated intent representation into a structured action or task-plan proposal. It may suggest a sequence, but it does not own transport, permissions, OS APIs, consent, or execution.

**ModelAdapter** provides a model-independent contract to local inference runtimes and future model providers. It reports capabilities, errors, cancellation/timeouts, and resource/runtime details. Model choice is an implementation decision, not a system architecture dependency.

Required behavior:

- Danish, German, and English are initial input languages in the AI Interface spec; actual feature quality must be benchmarked and disclosed per language.
- Ambiguous or incomplete intent returns abstention/clarification, not a guessed action.
- Confidence may help decide when to ask, but never grants authorization.
- The final enriched action object must be revalidated by the Gate. Orchestration may add trusted metadata but must not silently change model-proposed action semantics.
- Model output, retrieved text, documents, web pages, tool results, and prompts are untrusted data.
- No model or adapter can invoke an executor directly.
- Local inference is the default. Network access and cloud escalation must be explicit and policy-checked; no silent fallback from local to cloud.
- Pin exact artifact, revision, tokenizer/chat template, runtime version, license, hashes, and local-only behavior before accepting a model.
- Soofi S, Teuken, Devstral and other candidates remain evaluation candidates until their exact artifacts pass access, license, resource, language, tool-call, security, and reproducibility checks.

Normative detail: [AI Interface 1.0](../../specs/AI-INTERFACE-1.0.md) and [Soofi S evaluation plan](soofi-s-model-evaluation.md).

### 4.3 Gate Kernel and protected execution

Gate Kernel is the only authority for AI-assisted protected execution. The executor is a downstream mechanism, not a second policy engine.

Required logical sequence:

1. Parse proposal and validate protocol version.
2. Validate schema and action-specific fields.
3. Validate semantic completeness and resolve references.
4. Validate action, resource, destination, parameter limits, and scope.
5. Classify impact: idempotent, compensatable, or irreversible.
6. Evaluate current policy and system authorization.
7. Obtain explicit consent/confirmation where required, bound to the exact action and parameters.
8. Recheck session, authorization, resource identity/state, and approval freshness immediately before execution.
9. Atomically claim the action/idempotency key and prevent duplicate concurrent execution.
10. Execute through a narrow typed adapter.
11. Verify actual postcondition and record result, audit event, and durable state.
12. Report success only when supported by evidence; otherwise report failure, unknown, or partial completion.

Additional rules:

- An explicit plan block is absolute. Capability matches or higher assurance must never override `can_execute != true`.
- Consent and OS authorization are separate gates.
- A confirmation for one target or parameter set cannot authorize a modified action.
- Irreversible actions require explicit confirmation and clear target/impact presentation.
- Compensability does not imply consent and does not guarantee rollback.
- Partial failure must preserve completed effects and a recovery/resume path; never claim all-or-nothing rollback when the underlying service cannot provide it.
- Audit states should distinguish proposed, clarified, blocked, confirmation-pending, authorized, started, succeeded, failed, partially completed, and unknown.
- No alternate IPC route, debug endpoint, script, or direct executor call may bypass Gate policy.

Normative detail: [Gate Kernel 1.0](../../specs/GATE-KERNEL-1.0.md). Its implementation and regression tests must be audited against this contract before protected actions are enabled.

### 4.4 EDP — internal semantic dialog protocol

EDP expresses the meaning of an interaction independently of its transport. It is not a replacement for SMTP, SMS, SIP, XMPP, Matrix, WhatsApp, or other external protocols.

Initial action taxonomy:

- `utterance`
- `live_session`
- `artifact_shared`
- `commitment_proposed`, `commitment_accepted`, `commitment_declined`
- `value_transfer_requested`, `value_transfer_confirmed`
- `consent_requested`, `consent_granted`
- `presence_changed`

EDP must retain stable event/conversation/object references, participants, typed action content, timestamps, supersession history, route metadata, degradation/errors, evidence references, and idempotency/correlation where needed.

Rules:

- A proposed commitment is not an accepted agreement. UI language must say “foreslået” until the intended recipient explicitly accepts it.
- A transfer request is not payment authorization or proof of transfer.
- A consent message is not by itself a valid authorization record.
- A queued/accepted send is not a delivered message.
- Unknown or unassessed evidence is not trustworthy by default.
- Route changes that materially affect privacy, cost, recipient, or delivery expectation require user choice or explicit policy.
- Adapters declare supported actions and lossy mappings; unsupported mappings fail explicitly.

Normative detail: [EDP 1.0](../../specs/EDP-1.0.md) and [EDP JSON Schema](../../specs/edp-1.0.schema.json). The spec/schema are drafts until reconciled with existing IPC and event contracts.

### 4.5 EiraSystemAPI and Ubuntu adapters

EiraSystemAPI is EiraOS's versioned contract for local system capabilities. Ubuntu and freedesktop services remain the source of truth for actual host state and native authorization. EiraSystemAPI is not a single Ubuntu API.

Adapter preference:

1. Documented and supported native service interfaces, often D-Bus.
2. Desktop portals/session APIs when appropriate.
3. Narrow, validated command-line adapter only when a suitable stable API is unavailable.
4. No generic privileged shell or arbitrary command execution through the typed system API.

Candidate integrations to verify on the exact Ubuntu 26.04.x image include:

- NetworkManager: Ethernet, Wi-Fi, VPN.
- BlueZ: Bluetooth.
- PipeWire/WirePlumber: audio and media routing.
- Wayland compositor/session APIs: display and per-user settings.
- UPower and systemd-logind: power and sessions.
- UDisks2/udev: disks, removable media, mount/eject.
- APT/dpkg and release-supported update mechanisms: packages and OS updates.
- systemd D-Bus: narrowly scoped service status/actions.
- systemd journal: bounded diagnostics.
- CUPS/SANE: printing/scanning when installed.
- AccountsService/PAM/logind: account/session capabilities subject to a separate security design.
- fwupd and Ubuntu package metadata: firmware/driver status where supported.
- AT-SPI/Orca and desktop settings: accessibility.
- PipeWire/V4L2 and supported session permissions: cameras/media.
- UFW/nftables: firewall only through one explicitly selected manager, not competing managers.

Ubuntu version-specific assumptions must be verified against the target release, package versions, D-Bus introspection, Polkit rules, and session architecture. For example, release notes report removal of `pkcon` in Ubuntu 26.04; any package-management integration must use a verified supported path rather than assume older commands remain available.

**Cockpit policy:** optional, feature-by-feature reuse candidate. It is not a universal API or required foundation. For each proposed Cockpit-backed capability, document exact module/version, supported integration surface, license, dependencies, privileges, desktop UX fit, maintenance, and a native-adapter replacement path. Never depend on private Cockpit UI internals.

**Capability status:** unsupported hardware, missing service, permission denial, unavailable adapter, and runtime failure are distinct states. Capability discovery advertises only functionality that is implemented and actually available in the current environment.

Normative detail: [Ubuntu PC API catalog](ubuntu-pc-api-catalog.md), [coverage matrix](ubuntu-pc-api-coverage-matrix.md), [Ubuntu System API](ubuntu-system-api.md), and [EiraSystemAPI contract](eira-system-api.md).

### 4.6 Real Linux terminal

The terminal is a real interactive shell backed by a PTY managed by the Tauri/Rust backend. It is not a fake command prompt and not an alternate route for EiraOS privileged actions.

Requirements:

- Runs as the logged-in user by default; no automatic root or sudo.
- Correct PTY lifecycle, resize, Unicode, keyboard handling, terminal escape sequences/TUI behavior, Ctrl+C/Ctrl+D, exit status, session ownership, child-process cleanup, and multiple-session policy.
- Bounded output and IPC channels; backpressure and cancellation where possible.
- No secret terminal input/output in normal logs by default.
- Shell execution uses normal Linux permissions. Privileged settings remain in EiraSystemAPI's narrow, typed operations and native authorization flow.
- The GUI must clearly distinguish terminal output from trusted EiraOS status.
- Tests cover Unicode, TUI programs, resize, interrupted commands, shell exit, orphan cleanup, multiple tabs/sessions, and failure to start.

Normative detail: [Eira Terminal](eira-terminal.md).

### 4.7 Unified communication and provider adapters

The user interacts with a conversation/object, not a transport protocol. The communication layer should unify interaction patterns without claiming that external networks have become interoperable.

Eira Communication API (to be specified and versioned before production implementation) should define typed contracts for accounts, linked identities, conversations, messages, attachments, drafts, send requests, delivery state, notifications, calendar/contact operations, live-session launch, capability discovery, authorization, and sync status.

Adapters may include email standards/providers, Matrix or other supported chat APIs, authorized SMS paths, SIP/PBX, WebRTC/video providers, calendar/contact providers, and social APIs where official access permits. These are candidates, not promises of support.

Rules:

- Preserve original account, channel, sender, timestamp, attachment, delivery and security metadata.
- Identity linking must be explicit or supported by a reliable, explainable rule; never merge people based on an AI guess alone.
- Show which account/channel will be used for outbound communication when relevant.
- Sending, forwarding, inviting, deleting, paying, sharing sensitive attachments, or recording calls requires clear intent and applicable consent/confirmation.
- Never scrape private interfaces or bypass provider permissions.
- Delivery unknown/failure is not success; retries must be bounded and idempotent.
- End-to-end encryption claims must reflect actual protocol properties and implementation evidence.

Normative detail: [Communication principles](eiraos-communication-principles.md) and [Unified communication experience](unified-communication-experience.md).

### 4.8 Identity, context, graph, presence and evidence

These are responsibility boundaries, not proof that every daemon is fully implemented.

- **Identity/session:** authenticated principal, linked identities, session lifetime, assurance, credential/authorization references.
- **Context:** current user, active conversation/object, relevant recent events, and explicit scope; no unbounded implicit access to private data.
- **Graph/object store:** durable object references and temporal relationships, with versioning and concurrency semantics.
- **Presence:** time-sensitive availability, never a guarantee of reachability.
- **Evidence/provenance:** sources, signatures, validation result, freshness, and uncertainty. Keep evidence distinct from model confidence.
- **Audit/event history:** append or preserve relevant state transitions and outcomes; corrections/supersession do not silently erase history.

A `did:eira:anne` or `obj:project:42` string in a demo is only an illustrative identifier unless a real identity/object resolver proves that it maps to the intended person/object. Production flows must resolve identity and object references, handle zero/one/multiple matches, and ask when ambiguous.

### 4.9 Cross-device model

PC remains the full desktop environment. Early mobile support may be a companion app on existing mobile platforms; do not assume EiraOS replaces Android or iOS.

Shared contracts should cover account/device registration, authentication, device trust/revocation, per-data-type sync preferences, conflict handling, notification routing, file/link sharing, language preferences, and audit status. Pairing is opt-in. Device identity alone is not authorization. Sync is minimized and revocable, and no entire mailbox/contact/document history is synchronized by default.

Normative detail: [Cross-device principles](eira-cross-device-principles.md).

## 5. Data, IPC, and state contracts

Every IPC/API boundary must define:

- Protocol and schema version.
- Request ID/correlation ID and idempotency semantics where side effects occur.
- Typed request/response and stable structured error codes.
- Message framing, maximum size, timeouts, cancellation, and retry behavior.
- Authentication/authorization and scope.
- Event ordering, duplicate handling, stale state, and version mismatch behavior.
- Audit and secret-redaction policy.
- Capability discovery and feature unavailability behavior.

Existing Unix-domain socket/JSON-RPC IPC and the Tauri bridge are transport mechanisms; they are not automatically the Ubuntu system API or a security boundary by themselves. Existing interfaces must be inspected and tested before replacing or duplicating them.

For durable mutations, use explicit state machines and transactional/atomic transitions where available. Use idempotency keys for retries. For external effects that cannot be atomic with local storage, record intent and result separately and support uncertain/partial states rather than claiming a distributed transaction.

## 6. Security and threat model

Assume all model output, user-provided content, files, web pages, remote provider payloads, tool results, and IPC messages may be malformed or adversarial.

Protect against at least:

- Prompt injection and attempts to alter system policy.
- Schema-valid but semantically invalid actions.
- Path traversal, symlink escape, resource substitution, stale references, and time-of-check/time-of-use races.
- Confirmation replay or confirmation bound to different parameters.
- Session expiry, assurance downgrade, permission revocation, and concurrent requests.
- Duplicate side effects caused by retries/timeouts.
- Malicious or compromised adapters and malformed provider responses.
- Secret leakage through logs, error strings, telemetry, model prompts, or terminal output.
- Silent cloud escalation or unauthorized cross-device synchronization.
- Communication misrouting, identity collision, false delivery claims, and lossy protocol mappings.
- Missing services/hardware and hostile environment changes after capability discovery.

Security controls must be layered: schema validation, semantic validation, scope checks, consent, native OS authorization, current-state recheck, constrained adapters, postcondition verification, audit, and regression tests. No single layer replaces the others.

## 7. Canonical feature-state vocabulary

Use consistent status language across code, UI, docs and tests:

- **Proposed:** AI or application suggested an action; nothing has been executed.
- **Needs clarification:** required meaning, identity, target, or parameter is ambiguous.
- **Blocked:** policy, capability, permission, or safety rule forbids execution.
- **Needs confirmation:** user must approve the exact displayed action/target/impact.
- **Authorized:** required user consent and system permission checks passed; this does not yet mean execution succeeded.
- **Running:** execution began and has not reached a verified terminal state.
- **Succeeded:** the relevant postcondition was checked and supported by evidence.
- **Failed:** operation failed; include a safe structured reason.
- **Partially completed:** some effects happened; report them and the recovery/resume options.
- **Unknown:** outcome cannot currently be verified; do not retry blindly if the action may have occurred.
- **Unavailable/unsupported:** service, hardware, API, or provider does not offer the capability in this environment.

Do not conflate compensatable with consented, accepted with delivered, queued with sent, or model confidence with truth.

## 8. Testing and release gates

Testing is layered and must progress from safe isolation to real integration.

### Level A — contract and model tests

- Schema validity and invalid/unknown versions.
- EiraLang extraction, ambiguity, abstention and multilingual cases.
- EiraAI proposals, prohibited actions and malformed outputs.
- EDP action semantics, temporal rules and unknown action behavior.
- Model timeout, unavailable runtime, resource limit, and no-cloud policy.

No real side effects.

### Level B — Gate and adapter tests with fakes

- Explicit plan blocks and missing decisions always fail closed.
- Missing/expired session and insufficient/revoked assurance.
- Consent absent, stale, replayed, or bound to changed parameters.
- Duplicate and concurrent confirmation/idempotency.
- Resource scope, path traversal, symlink escape, stale object, and changed resource.
- Adapter missing, timeout, malformed output, permission denial, partial failure, and recovery state.
- Direct executor invocation cannot bypass Gate policy.
- Audit records correct transitions without secrets.

Use fake executors or disposable test resources; do not touch real user data.

### Level C — Ubuntu integration tests

Run against the exact supported Ubuntu 26.04.x image and package set:

- D-Bus introspection and permissions/Polkit behavior.
- Capability discovery with service present, absent, denied, and degraded.
- Read-only NetworkManager status as an initial low-risk system integration smoke test.
- Real PTY behavior and lifecycle.
- File operations only inside a disposable test directory and only after scope/confirmation rules pass.
- Device/service variations and reboot/session persistence where relevant.
- Evidence includes image version, package versions, test command, output, and known limitations.

### Level D — user-visible vertical end-to-end tests

The UI, orchestration, Gate, adapter, persistence, and result/audit must all be verified. A successful button click or mock response is insufficient.

For the initial commitment/demo workflow:

- Resolve the intended person and project through actual identity/object lookup; never rely on hardcoded demo IDs as proof of identity.
- Resolve dates against a frozen clock and explicit timezone in tests.
- Distinguish a proposed commitment from recipient acceptance.
- Test zero, one, and multiple identity/project matches.
- Test ambiguous time, recipient unavailable, permission denial, duplicate request, persistence failure, notification failure, and partial success.
- Verify the graph/object state and audit record independently of the UI response.
- Report “foreslået” until the recipient's acceptance is actually recorded.

No feature passes a release gate based only on a mockup, unit test, model score, or spec.

## 9. Implementation roadmap

This sequence is designed to reduce risk and produce real evidence early.

### Phase 0 — architecture and contract reconciliation

- Treat this baseline as the map; linked documents remain the detailed contracts.
- Reconcile Gate Kernel, AI Interface, EDP text and JSON Schema, existing JSON-RPC/IPC, capability manifests, and executor semantics.
- Record any mismatch as a tracked issue; do not silently choose different behavior in code and docs.
- Define stable error/state vocabulary, identity/object resolution contracts, idempotency, and audit semantics.
- Add a code-review checklist that labels each item **Implemented and verified / Partially implemented / Missing / Unclear**, with exact file/function/test evidence.

### Phase 1 — harden the Gate before expanding actions

- Verify that `can_execute` must be exactly true before execution.
- Recheck session and all required assurance levels at confirmation time.
- Bind confirmation to the immutable action/target/parameters and invalidate it if the plan changes.
- Make execution claims depend on postcondition verification.
- Add bypass, concurrency, duplicate, stale-session, consent, and partial-failure regression tests.
- Run CI and record results; do not call the fix verified until tests actually pass.

### Phase 2 — first EiraSystemAPI vertical

- Implement capability discovery and typed error behavior.
- Verify the target Ubuntu 26.04.x image and relevant package/interface versions.
- Implement read-only NetworkManager status as the first OS integration smoke test.
- Add mocked adapter tests and real Ubuntu integration tests, including service missing and permission denied.
- Then implement the first bounded file operation (directory listing within an approved scope), followed by metadata/read; keep copy/move/delete behind later explicit gates.
- Build the PC coverage matrix row-by-row and link every status to implementation/test evidence.

### Phase 3 — first complete AI/user workflow

- Wire AI Interface proposal through Gate to a fake executor first.
- Add identity/object lookup and durable graph/audit state before sending notifications or external messages.
- Implement the commitment demo as a true vertical slice, with “proposed” and “accepted” distinct.
- Verify state persistence, notification outcome, idempotency and partial failures end to end.

### Phase 4 — real terminal

- Implement the PTY lifecycle in Tauri/Rust under the logged-in user.
- Validate terminal UI, Unicode/TUI, resizing, signals, session ownership, output limits and cleanup.
- Ensure terminal commands are not silently routed through EiraSystemAPI and cannot bypass Gate-controlled actions.

### Phase 5 — PC settings coverage

- Continue through P0 PC Core rows in the Ubuntu PC API coverage matrix.
- Implement P1 and P2 only after dependencies, UX, authorization, and scope are agreed.
- Evaluate Cockpit feature by feature; keep it optional and replaceable.
- Do not install server/remote-management stack by default.

### Phase 6 — communications and cross-device expansion

- Define the versioned Eira Communication API and provider capability matrix.
- Implement one authorized real provider at a time; retain original channel/account/delivery metadata.
- Add explicit identity linking, consent, privacy, and route fallback rules.
- Define cross-device trust, revocation, per-data-type sync, and conflict handling before syncing private content.

### Phase 7 — release hardening

- Reproducible CI and target-image tests.
- Threat-model review and authorization/bypass regression suite.
- Dependency/license/model artifact review.
- Accessibility and localization testing.
- Upgrade/recovery testing, audit review, and documented support matrix.

## 10. Definition of done

A capability may be labelled **Implemented** only when all applicable items are true:

1. Typed versioned contract and error semantics are documented.
2. Application/domain logic is separate from UI and platform-specific adapters.
3. Authorization, scope, consent and confirmation behavior are explicit and fail closed.
4. Normal, invalid, denied, unavailable, timeout, duplicate and partial-failure cases are tested.
5. Automated tests pass in CI, with results recorded.
6. The UI accurately reflects pending, success, failure, unavailable, unknown and partial states.
7. Audit events exist where appropriate and contain no secrets.
8. The implementation is linked to the exact matrix row/capability.
9. **Verified on target Ubuntu** additionally requires reproducible integration evidence from the supported Ubuntu 26.04.x image.
10. External communication or cross-device features additionally require provider/device authorization, privacy, delivery/sync, revocation and failure tests.

## 11. Repository map and source of truth

Use the following hierarchy to avoid competing specifications:

| Area | Primary document / contract | Role |
|---|---|---|
| Overall architecture | `eiraos-architecture-baseline-1.0.md` (this document) | Cross-system map, invariants, roadmap and definition of done |
| System architecture overview | `eiraos-system-architecture.md` | High-level architecture and responsibilities |
| Presentation vs logic | `separation-of-presentation-and-logic.md` | Normative layer boundaries |
| UI/product language | `eiraos-design-principles.md` | Experience, accessibility, language layer |
| Ubuntu capability inventory | `ubuntu-pc-api-catalog.md` | Initial research inventory |
| Ubuntu coverage tracking | `ubuntu-pc-api-coverage-matrix.md` | Capability-level verification ledger |
| EiraSystemAPI | `eira-system-api.md`, `ubuntu-system-api.md` | Eira-owned contract and Ubuntu adapter strategy |
| Terminal | `eira-terminal.md` | PTY UX, lifecycle and security requirements |
| Gate | `../../specs/GATE-KERNEL-1.0.md` | Authoritative protected-action policy |
| Model boundary | `../../specs/AI-INTERFACE-1.0.md` | EiraLang/EiraAI/model adapter contract |
| Semantic communication protocol | `../../specs/EDP-1.0.md` and `../../specs/edp-1.0.schema.json` | Internal action envelope/schema |
| Communication UX and integration | `eiraos-communication-principles.md`, `unified-communication-experience.md` | Provider-neutral communication behavior |
| Cross-device | `eira-cross-device-principles.md` | Pairing, sync, revocation and mobile direction |
| Model evaluation | `soofi-s-model-evaluation.md` | Evidence-based candidate evaluation |
| Existing file flow | `../audit/ubuntu-file-operations-audit.md` | Static audit findings and limitations |

**Authority rule:** this baseline does not override the detailed schema or implementation contract. If documents disagree, record the conflict and reconcile the relevant source documents and tests before coding. JSON Schema defines structural constraints; semantic rules, authorization, identity, and execution evidence remain separate checks.

## 12. Known open decisions and explicit non-claims

These are not hidden assumptions; they require review and/or implementation evidence:

- Whether EDP 1.0 is ready to become binding after schema/spec/IPC reconciliation.
- Whether all Gate Kernel decisions and error codes are consistent, including where clarification is permitted versus where rejection is required.
- Whether `intentd` enrichment can add trusted metadata without altering action semantics.
- The precise object-reference registry and identity-resolution API.
- The exact Eira Communication API schema and the first production provider.
- Which Cockpit features, if any, have a supported integration surface suitable for EiraOS.
- The exact Ubuntu 26.04.x packages, D-Bus APIs, permissions and desktop-session behavior for every capability.
- The first supported hardware profile and CI image.
- Model selection: no candidate becomes a fixed dependency before access/license/local behavior/performance tests pass.
- Whether each daemon named in the architecture is present, production-ready, and covered by tests must be verified against current code.

This baseline does **not** claim that all system settings, drivers, communication providers, cross-device services, AI models, Gate behavior, or Ubuntu adapters are implemented. It defines the intended complete architecture and a controlled path to verify and implement it.

## 13. Summary

EiraOS owns the experience, contracts, policy, and orchestration. Ubuntu owns the underlying host state and native permissions. External providers own their networks and delivery guarantees. Models interpret and propose; they do not authorize or execute. The Gate validates every protected action. Adapters keep implementation replaceable. The UI shows only what the system can truthfully substantiate.

**Models come and go. Providers come and go. Ubuntu interfaces evolve. The EiraOS contracts and Gate remain the stable center.**
