# Specifications

This directory contains protocol and interface specifications for EiraOS.

## EiraOS Dialog Protocol (EDP)

- [EDP 1.0 specification](EDP-1.0.md) — proposed internal semantic envelope for conversation actions, independent of transport.
- [EDP 1.0 JSON Schema](edp-1.0.schema.json) — structural validation for event envelopes and action content.

**Status:** EDP 1.0 is a draft for review. It does not mean adapters, daemons, delivery guarantees, trust assessments, or payment integrations are implemented. Before treating it as binding, review it against existing repository contracts, security policy, and tests.

EDP does not replace external protocols. Adapters map supported actions to and from external systems and must report unsupported or degraded mappings honestly. Schema validation does not establish identity, authorization, delivery, provenance validity, or truth.
