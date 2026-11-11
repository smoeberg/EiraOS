# Specifications

This directory contains protocol and interface specifications for EiraOS. The integrated architecture map is [EiraOS Architecture Baseline 1.0](../docs/architecture/eiraos-architecture-baseline-1.0.md).

## Contexts, storage and sync

- [EIRA Context 1.0](EIRA-CONTEXT-1.0.md) — the context as data, one Linux user per context, lifecycle on a device, key hierarchy, the open storage format (exit guarantee), sync over S3/WebDAV, ID home contents, glimt (ADR-0005, ADR-0006 L5).

**Status:** v0.3, accepted by the owner 11 November 2026; binding. [Test plan](EIRA-CONTEXT-1.0-TESTPLAN.md) accepted 11 November 2026. Nothing is implemented yet.

## Gate Kernel

- [Gate Kernel 1.0](GATE-KERNEL-1.0.md) — authoritative protected-action boundary: validation, semantic/policy checks, consent, authorization, state safety, execution and result verification.

**Status:** Draft, binding as an implementation target; not proof that all Gate checks are implemented or tested. Reconcile its decision/error semantics with the actual intent pipeline and regression tests before enabling new protected actions.

## Conversation layer

- [EIRA-CONVERSATION-1.0](EIRA-CONVERSATION-1.0.md) — membership (who may act and see in a conversation) and the read-only event stream for Explorer.

**Status:** Draft, implemented in `app/conversation/`. Membership is derived only from events the gate records; there is no write method.

## Model-independent AI interface

- [AI Interface 1.0](AI-INTERFACE-1.0.md) — model adapter, EiraLang intent extraction, EiraAI action proposals, abstention and orchestration boundaries.

**Status:** Draft, binding as an implementation target; not proof that model adapters or the full orchestration flow are implemented. Models propose; they do not authorize or execute.

## EiraOS Dialog Protocol (EDP)

- [EDP 1.0 specification](EDP-1.0.md) — proposed internal semantic envelope for conversation actions, independent of transport.
- [EDP 1.0 JSON Schema](edp-1.0.schema.json) — structural validation for event envelopes and action content.

**Status:** EDP 1.0 is a draft for review. It does not mean adapters, daemons, delivery guarantees, trust assessments, or payment integrations are implemented. Before treating it as binding, review it against existing repository contracts, security policy, IPC/event contracts, and tests.

EDP does not replace external protocols. Adapters map supported actions to and from external systems and must report unsupported or degraded mappings honestly. Schema validation does not establish identity, authorization, delivery, provenance validity, consent, or truth.

## Consistency rule

The architecture baseline describes how these specifications fit together. If a spec, schema, implementation, or test disagrees with another, record the discrepancy and reconcile the source contract and tests before relying on it. Do not silently treat a draft as runtime behavior.
