# EiraOS Architecture Rule: Separation of Presentation and Logic

Status: **normative architecture rule**  
Applies to: React GUI, control center, terminal UI, EiraSystemAPI, adapters, daemons, and tests.

## Rule

EiraOS MUST keep presentation separate from application/domain logic and from operating-system integrations. A redesign of the GUI MUST NOT require rewriting system-management rules. Replacing Cockpit or an Ubuntu service integration MUST NOT require rewriting the GUI or domain rules when the published EiraOS contracts remain compatible.

## Layer responsibilities

1. **Presentation layer** — React components, layout, styling, animation, accessibility and local view state. It renders typed state and sends user intentions through defined interfaces. It MUST NOT implement system policy, invoke privileged commands, or speak directly to arbitrary OS services.
2. **Application/domain layer** — use cases, validation, state transitions, authorization decisions that belong to EiraOS, orchestration and stable error semantics. It MUST NOT depend on React, CSS, view components or Cockpit UI internals.
3. **Contract and adapter layer** — versioned typed contracts, IPC/API boundaries and adapters. EiraSystemAPI owns the stable EiraOS-facing contract; Cockpit and Ubuntu integrations are replaceable implementations behind it.
4. **Operating-system layer** — Ubuntu services, documented D-Bus APIs, system tools and kernel interfaces remain the source of truth for actual host state and native authorization.

Dependencies point inward toward EiraOS-owned contracts. Infrastructure-specific details MUST NOT leak into presentation components or domain types.

## Mandatory implementation rules

- No business/domain policy in React components or presentation hooks. UI-only state (e.g. an open menu or selected tab) may remain in the presentation layer.
- No React, DOM, CSS, or GUI imports in domain/application logic.
- No direct privileged shell commands from the GUI.
- No generic privileged `run(command)` operation in EiraSystemAPI.
- Ubuntu integrations MUST prefer supported service APIs (often D-Bus). A narrow command-line adapter is allowed only when a suitable supported API is unavailable, and must validate inputs and test exit codes/output.
- Cockpit is an optional feature-by-feature reuse candidate. Use documented, supported integration surfaces only; do not depend on private UI internals. Every Cockpit-backed feature must have a native-adapter replacement plan behind the same EiraSystemAPI contract.
- GUI and terminal run as the logged-in user by default, not root. Privileged operations use native service authorization / Polkit and fail closed.
- API results use typed payloads and stable structured errors; no UI parsing of human-readable command output.
- Long-running operations expose progress/cancellation when supported, and the UI must show pending, success, failure and permission-denied states.
- Capability discovery distinguishes unsupported hardware/features from a broken or unavailable service.
- Logs/audit events must never include credentials or secrets.

## Testable acceptance criteria

A change that crosses these layers is not complete until relevant criteria are met:

1. **Domain isolation:** unit tests for application/domain logic run without React, a display server, Cockpit, or real hardware.
2. **Contract tests:** API input/output schemas, version behavior, error codes, and capability discovery are tested.
3. **Adapter tests:** adapters have mocked unit tests and integration tests against the supported Ubuntu services where feasible.
4. **Presentation tests:** GUI components consume typed contracts and cover loading, empty, unsupported, permission-denied and failure states.
5. **Substitution test:** at least one adapter can be replaced by a fake/test implementation without changing presentation or domain logic.
6. **Security tests:** invalid arguments, authorization denial, missing services, timeout, cancellation and partial failure are covered.
7. **Evidence:** a feature is marked implemented only when adapter, GUI, tests and target-Ubuntu integration evidence exist. Documentation or mock UI alone does not count.

## Architecture review checklist

For every pull request that adds a system capability, reviewers should ask:

- Is presentation code limited to rendering and view-local interaction?
- Does the use case depend on an EiraOS-owned interface rather than Cockpit or a concrete Ubuntu service?
- Are OS-specific details confined to an adapter?
- Are permissions enforced at the backend/native-service boundary?
- Are errors typed and user-presentable without parsing terminal output?
- Can the feature be tested without a GUI and can the adapter be replaced?
- Are package dependencies, supported Ubuntu version and limitations documented?

## Relationship to the API catalog

The capability and Cockpit reuse matrix lives in [ubuntu-pc-api-catalog.md](./ubuntu-pc-api-catalog.md). The detailed system API contract and coverage checklist lives in [ubuntu-system-api.md](./ubuntu-system-api.md). The terminal runtime requirements live in [eira-terminal.md](./eira-terminal.md).

This rule defines the required architecture; it does not claim that existing EiraOS code already satisfies every criterion. Existing code must be audited and migrated incrementally.
