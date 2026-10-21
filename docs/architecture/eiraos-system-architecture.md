# EiraOS — System Architecture

**Status:** Proposed architecture baseline; subject to repository review  
**Scope:** All EiraOS components  
**Primary platform target:** Ubuntu Desktop 26.04 LTS, latest 26.04.x point release  
**Implementation status:** This document describes architectural intent and boundaries. It does not claim every listed daemon, model, adapter, or feature is implemented or runtime-verified.

## 1. Purpose

EiraOS is an intent-driven operating-system experience built on Ubuntu. Its UX should center on people, conversations, objects, tasks, and user intent rather than requiring users to navigate application silos, files, menus, or transport protocols as the primary mental model.

The experience should take interaction cues from modern touch-first systems while retaining the power of a full desktop, native Linux tools, and an interactive terminal. Presentation, domain logic, contracts/adapters, and operating-system infrastructure remain separate layers.

## 2. Fundamental rule

> **The AI proposes. The Gate decides. The system executes.**

This is a security invariant, not a slogan:

- Models interpret language and propose structured actions.
- EiraOS-owned deterministic policy and validation code checks schema, semantics, authorization, scope, consent, and current state.
- Only the authorized execution path may perform protected actions.
- Model output, confidence scores, tool calls, and constrained JSON are untrusted input; none is authorization or evidence of truth.
- Changing a model must not require changing EDP, the Gate, or the UI contract.

## 3. Layered architecture

The following is a logical architecture, not a claim that all components already exist:

```text
┌─────────────────────────────────────────────────────────────┐
│ EiraOS UX / Intent Shell                                     │
│ Conversation-first UI · object workspace · settings · PTY    │
├─────────────────────────────────────────────────────────────┤
│ Model-independent AI interface                               │
│ EiraLang: language understanding / translation / intent      │
│ EiraAI: planning / tool and action proposals                 │
│ Model adapters and local runtime                              │
├─────────────────────────────────────────────────────────────┤
│ EiraOS Gate / application policy                             │
│ schema · semantic validation · scope · permissions · consent │
│ state transitions · idempotency · audit · result verification│
├─────────────────────────────────────────────────────────────┤
│ EiraOS contracts and core services                           │
│ EDP · EiraSystemAPI · identity · context · graph · presence  │
│ intent orchestration · trust/evidence services                │
├─────────────────────────────────────────────────────────────┤
│ Ubuntu Desktop 26.04 LTS substrate                           │
│ Linux · systemd · AppArmor · supported D-Bus/APIs · drivers   │
└─────────────────────────────────────────────────────────────┘
```

Dependencies point toward EiraOS-owned contracts. The UI must not implement system policy or call privileged OS interfaces directly. Domain logic must be testable without React, a display server, or a live desktop session. OS adapters must not depend on UI internals.

See [Separation of Presentation and Logic](separation-of-presentation-and-logic.md) and [EiraSystemAPI](eira-system-api.md) for the more specific contracts.

## 4. Core-service responsibilities

These are candidate responsibility boundaries. Names in this table do not prove that the corresponding service or full behavior is implemented.

| Service / area | Intended responsibility |
|---|---|
| `identityd` | User and organization identity, keys, identity assurance and session identity |
| `walletd` | Payment and wallet integrations, only where explicitly implemented and authorized |
| `veritasd` | Evidence/provenance assessment; keep evidence separate from model confidence |
| `graphd` | Objects and temporal relationships |
| `presenced` | Presence and conversation/object association |
| `contextd` | Context scoped to the active user, object, and conversation |
| `intentd` | Intent orchestration and creation of validated action proposals |
| Gate / executor | Authoritative authorization and controlled execution; must not be bypassable |

Where IPC uses AF_UNIX sockets and JSON-RPC, message framing, schema versioning, request correlation, error behavior, and authorization must be explicitly specified and tested. Do not assume a daemon's name alone establishes its contract.

## 5. EDP — EiraOS Dialog Protocol

EDP is the internal semantic protocol for representing dialog-related actions. It does not replace external transport protocols such as SMS, SMTP, SIP, XMPP, or provider-specific messaging APIs. Adapters translate between EDP and supported external services.

### 5.1 Transport independence

- The user expresses the intended outcome; a supported adapter handles transport-specific details.
- Transport remains structured metadata for reachability, delivery status, account identity, cost, privacy, and troubleshooting.
- Do not silently reroute when a route change materially affects privacy, cost, delivery expectations, or identity.
- Never imply that two networks interoperate if the destination service does not support it.
- Report delivery failures honestly; a failed or unknown delivery must not be represented as success.

### 5.2 Initial action taxonomy

The following is the proposed initial closed set. Changes require versioned schema updates and tests.

| Action type | Intended meaning |
|---|---|
| `utterance` | Message or conversational content |
| `live_session` | Call, video session, or live room |
| `artifact_shared` | File, document, or image shared |
| `commitment_proposed` / `commitment_accepted` / `commitment_declined` | Meeting or commitment workflow |
| `value_transfer_requested` / `value_transfer_confirmed` | Payment workflow |
| `consent_requested` / `consent_granted` | Explicit consent workflow |
| `presence_changed` | Presence state change |

Each action type needs a versioned schema, required fields, semantic rules, authorization requirements, idempotency behavior, and negative tests. Do not allow a model to invent missing required values; reject or ask the user.

### 5.3 Message envelope

The canonical EDP envelope and JSON Schema should live in the machine-readable contract/schema location, not be duplicated as competing authorities in prose. At minimum, the contract should preserve:

- protocol/schema version and unique action ID;
- conversation/object association and participants;
- action type and typed content;
- transport preferences, actual route, delivery state and structured error;
- evidence references and an explicit unknown/unassessed state;
- creation time, validity and supersession relationships;
- correlation/idempotency key and audit linkage where needed.

A trust score is not a probability that a statement is true, and it is not authorization. Evidence provenance must be inspectable and independently assessed.

### 5.4 Adapter contract

Each transport adapter should provide send, receive, and health/capability reporting using typed results. A health check must be bounded in time. An unavailable adapter must not be selected as healthy. Delivery failure must return an explicit failure/unknown state, never a false success. Protocol-specific details belong in the transport boundary.

## 6. Model-independent AI interface

The AI layer is a replaceable interpretation/planning subsystem, not the security kernel.

Proposed semantic interface:

```text
interpret_intent(text, context, allowed_actions)
  -> ActionProposal | Abstain | Error
```

The exact types and schemas must be versioned in code. The interface must not expose OS APIs or transport-specific operations to a model.

### EiraLang

Intended for language understanding, translation, entity extraction, and interpretation of user intent. It produces a typed intermediate representation, not an independently executable EDP message.

### EiraAI

Intended for multi-step task planning, tool selection, and action-sequence proposals. It consumes the validated intermediate representation and proposes typed actions. It performs no protected action itself.

### Model selection status

Teuken, Devstral Small 2, Soofi S, and other candidates are evaluation candidates, not architectural dependencies. Before selecting a model, verify exact model revision, weights access, license, runtime compatibility, local-only behavior, language performance, tool-call reliability, hardware requirements, and maintenance status. A model's advertised support for tool calling does not establish EiraOS-level safety.

The default must be local inference. Any cloud inference must be an explicit, policy-checked choice with clear user consent and data-classification rules; ambiguity must not automatically send sensitive data to a cloud service.

## 7. Gate and protected execution

Every model-generated or AI-assisted protected action must use one authoritative path:

1. Receive an untrusted action proposal.
2. Validate syntax and schema.
3. Validate semantic completeness and allowed action type.
4. Validate resource identity, target, scope, and parameters.
5. Check current permissions and policy.
6. Require explicit consent/confirmation where policy demands it, bound to the exact action and parameters.
7. Re-check authorization and relevant resource state immediately before execution.
8. Execute through a narrow capability adapter.
9. Verify the resulting state and record an honest outcome.

### Required invariants

- **Fail closed:** missing, malformed, stale, ambiguous, or unauthorized decisions are rejected.
- **No alternate path:** direct executor calls cannot bypass authorization.
- **Bound confirmation:** changing action parameters invalidates prior approval.
- **Idempotency:** duplicate or concurrent confirmation must not cause duplicate effects.
- **State correctness:** pending-to-running/completed transitions must be concurrency-safe.
- **Honest partial failure:** record partial completion and recovery/resume state; do not claim a universal rollback for irreversible OS/network operations.
- **Fresh authorization:** revocation or session changes are rechecked at execution time.
- **Auditability:** distinguish requested, proposed, blocked, confirmed, started, succeeded, failed, and partially completed states.
- **Reversibility classification:** classify actions as idempotent, compensatable, or irreversible; irreversible/high-impact actions require explicit confirmation and audit.

JSON-schema-constrained generation can help with syntax and shape; it cannot prove semantic correctness, permissions, or safety.

## 8. Privacy, sovereignty, and evidence

- Local processing is the default; no data should leave the device without an explicit, policy-compliant reason.
- A local runtime does not by itself prove that telemetry or network traffic is absent. Verify the runtime and configuration.
- Cloud escalation is never automatic. Require explicit user choice, network policy, and data-type checks.
- Treat all model output as untrusted.
- Separate AI confidence from provenance/evidence assessments.
- Audit sensitive actions without logging secrets, private content, or raw credentials.
- Clearly show denial, delivery failure, unavailable capabilities, and degraded operation.

## 9. Veritas / evidence assessment

Evidence and provenance assessment may consider signed source claims, content credentials such as C2PA, identity evidence, source references, and temporal consistency when available. Do not claim a source is authentic merely because a model assigns high confidence or a numeric trust score.

Any proposed “red/green/blue shield” UX or 0–100 indicator is a presentation concept until the evidence inputs, calibration, failure states, false-positive/negative behavior, and validation tests are documented. Missing evidence must be represented as unknown/unassessed, not silently interpreted as trustworthy.

## 10. Development and acceptance rules

1. Harden and test the Gate before enabling new model-driven execution paths.
2. Keep presentation, domain logic, contracts/adapters, and OS integration separate.
3. Make model providers replaceable behind a stable contract.
4. Test authorization failures and bypass attempts, not just successful workflows.
5. Do not claim a capability is implemented without code, automated tests, and target-Ubuntu integration evidence.
6. Verify all Ubuntu system interfaces against the actual supported 26.04.x packages, D-Bus APIs, authorization rules, and desktop session.
7. Keep server/enterprise features out of the default PC profile unless explicitly approved.

### Minimum Gate regression suite

- Invalid JSON and invalid schema.
- Missing required fields and unknown action types.
- Forbidden path/resource, traversal, symlink escape, or changed resource.
- Missing/expired consent or confirmation bound to different parameters.
- Rights revoked or session changed after planning.
- Duplicate and concurrent confirmation.
- Direct executor invocation without Gate authorization.
- Adapter unavailable, timeout, and malformed result.
- Partial/irreversible failure and recovery-state reporting.
- Prompt injection and model attempts to request prohibited operations.

## 11. Roadmap principle

The Gate and contracts are the stable core; model selection is an implementation choice. Continue building EDP, authorization, model adapters, and test harnesses without waiting for a future model release. Evaluate candidate models against the same test set and only switch defaults after license, local operation, quality, resource use, and security acceptance criteria pass.

## 12. Summary

EiraOS is an operating-system experience with an authoritative security gate and replaceable AI interpretation components. Its defining properties are controlled execution, local-first data sovereignty, clear boundaries between UI/domain/infrastructure, provider-neutral semantic communication, and the ability to change models without weakening the security core.

**Models come and go. The Gate remains.**
