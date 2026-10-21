# Architecture Principle: Communication as Dialogue, Not Technology

**Status:** Proposed architectural principle; intended to become binding after review  
**Scope:** Communication UX, intent handling, conversation model, routing adapters, identity, trust, context, and relevant daemons  
**Implementation status:** This document records requirements and candidate responsibilities. It does not assert that these capabilities are implemented or verified in the current codebase.

## 1. Principle

People communicate with people—not protocols. The primary user concept is the person, relationship, conversation, or object being discussed. SMS, email, chat, voice, video, file exchange, and other transports are delivery routes behind that experience.

> We speak with a person, whether we send a letter, make a call, or send a text. The transport is secondary.

EiraOS must not force users into app silos or require them to understand protocols to communicate. Users express an intention; EiraOS helps carry it out through a supported route while preserving user control, privacy, and clear delivery outcomes.

Channel independence is a user-experience principle, not a claim that all networks are interoperable. The system must not imply cross-network delivery when the destination service does not support it.

## 2. Normative requirements

### 2.1 Conversation-first model

- The primary interaction is a person, group, relationship, project, or other relevant object—not a protocol-specific inbox.
- Where identity and context can be linked reliably, supported messages and related activities may appear in one coherent conversation history.
- Do not merge identities based only on a guess. The user must be able to inspect, correct, and unlink identity associations.
- Preserve source account, route, sender identity, timestamps, attachments, security properties, and delivery state as structured metadata. These details are secondary in the main UI, but must remain available when relevant.
- A conversation model must not pretend that independent native threads on different services are one server-side thread.

### 2.2 Intention before protocol

- The user should be able to express an outcome, such as contacting a person, arranging a meeting, or sharing a document, without first navigating to a protocol-specific application.
- Routing logic may select or recommend a route only when recipient reachability, provider capability, authorization, user settings, consent, and applicable policy permit it.
- The system must never silently change the route when the route affects meaning, privacy, cost, identity, delivery expectations, or user intent.
- When a choice is ambiguous or consequential, ask the user before sending.
- A route must never be described as available unless its capability has been discovered or verified.

### 2.3 Failure, queueing, expiry, and retry

Every outbound operation must have an explicit state, such as draft, waiting for route selection, queued, sending, accepted by provider, delivered (only when confirmed), failed, expired, or cancelled. Provider-specific states may require additional values.

- Never show success merely because a request was queued or accepted by an adapter.
- If the requested route is unavailable, explain this in plain language, identify the affected message, and offer valid choices where available.
- Keep an unsent message as a draft or explicitly marked queued item; do not silently discard it.
- Define expiry and retry policy per route. Do not automatically retry a potentially non-idempotent send unless duplicate behavior is controlled or clearly disclosed.
- Before fallback to a different route, obtain user approval whenever it changes recipient reachability, privacy, cost, security, or the expected delivery channel.
- Record provider receipts accurately. Distinguish “accepted by provider” from “delivered to recipient” and from “read”.

### 2.4 Metadata privacy and lifecycle

Channel, account, recipient, timing, routing, and delivery metadata can be sensitive personal data.

- Collect and retain only metadata required for the feature, user-visible history, security, and operational reliability.
- Document what is stored locally, what is synchronized, which providers receive it, and whether AI services process it.
- Enforce account- and operation-scoped access controls. UI components must not receive provider credentials or unrestricted access to communication stores.
- Define retention, export, deletion, backup, and synchronization behavior for messages and associated metadata. Deletion must describe whether it affects only the local EiraOS copy or also a provider's copy.
- Protect metadata in transit and at rest using the platform's supported security mechanisms.
- Include identity-linking, metadata exposure, provider compromise, unauthorized routing, notification previews, AI processing, and cross-device sync in the threat model.

### 2.5 Trust and identity

- Preserve authenticated sender information and the source's security properties.
- Show provenance or trust information when it helps the user assess authenticity or risk; do not imply that one numeric score proves that a message is true.
- Identity verification and step-up authorization must be enforced by the relevant trusted service, not by presentation logic.
- Do not assume EUDI, signatures, end-to-end encryption, or other identity/security mechanisms are supported for every route. Document the actual guarantees per provider and route.

## 3. Architecture boundaries

Use provider-neutral contracts and replaceable adapters. The interface must express capability differences honestly; unsupported actions must return explicit unsupported-capability results rather than simulated success.

Candidate responsibility mapping (must be checked against the current repository before being treated as the actual implementation):

| Area or candidate component | Intended responsibility to validate |
|---|---|
| Intent handling (candidate: `intentd`) | Interpret user intent and request an authorized operation; do not let an LLM or UI bypass policy gates. |
| Presence/relationship handling (candidate: `presenced`) | Provide verified presence or relationship data only if that is its documented and implemented role. |
| Conversation/object graph (candidate: `graphd`) | Potentially link conversations to people and relevant objects with provenance and temporal history; canonical ownership must be decided explicitly. |
| Trust/provenance (candidate: `veritasd`) | Evaluate source and evidence under a documented model; do not treat a trust score as proof of truth. |
| Identity (candidate: `identityd`) | Enforce identity and session assurance only to the extent demonstrated by code and tests. |
| Context (candidate: `contextd`) | Provide authorized, scoped context; do not make all user data globally visible by default. |
| Routing adapters | Discover capabilities, enforce route-specific authorization, report explicit states and failures, and avoid unsafe retries. |
| UI and HTTP bridge | Present intent, status, route details when relevant, and clear failure recovery; contain no provider secrets or privileged protocol logic. |

No daemon's responsibility, trust guarantee, or integration status should be inferred from its name. Verify the implementation, permissions, tests, and runtime wiring before assigning ownership.

## 4. Anti-patterns

- Requiring the user to choose an app or protocol as the first step for contacting a person.
- Hiding route failure behind a success indicator.
- Automatically falling back to another route when this changes privacy, identity, cost, or delivery expectations.
- Merging contacts or conversations based on speculative identity matches.
- Treating provider acceptance as proof of recipient delivery.
- Duplicating communication histories across channel silos without a defined identity and provenance model.
- Exposing protocol details as the primary user vocabulary.
- Claiming that a daemon or adapter provides behavior that has not been verified in code and tests.
- Treating channel/account/delivery metadata as non-sensitive simply because it is secondary in the UI.

## 5. Testable acceptance criteria

1. A user can continue a linked conversation across at least two supported routes without navigating into separate channel-specific application silos.
2. The UI identifies the destination and route before sending whenever the route is ambiguous or materially affects privacy, cost, identity, or delivery expectations.
3. An unavailable route produces an understandable error, preserves the message, and offers only valid recovery options.
4. Queueing, provider acceptance, delivery, read receipt, failure, expiry, and cancellation are not conflated.
5. Automatic retry and fallback tests demonstrate that they cannot silently create duplicate sends or change the route against user intent.
6. Identity links can be inspected and undone; uncertain identities are not silently merged.
7. Access-control tests cover message content and associated routing/account metadata.
8. Retention, deletion, export, sync, backup, and AI-processing behavior are documented and tested for each implemented integration.
9. Every capability claim is backed by automated tests and target-platform integration evidence; design mockups alone do not count as implementation.

## 6. Relationship to existing documents

This principle complements:

- `docs/architecture/eiraos-communication-principles.md`
- `docs/architecture/unified-communication-experience.md`
- `docs/architecture/eiraos-design-principles.md`
- `docs/architecture/eira-cross-device-principles.md`

Where wording conflicts, the more specific security, authorization, privacy, and implementation-verification requirements take precedence. Before this principle is marked binding, review those documents together and reconcile any conflicts.
