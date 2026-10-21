# EDP 1.0 — EiraOS Dialog Protocol

**Status:** Draft for architecture review; not yet binding  
**Version:** 1.0  
**Scope:** Internal, channel-independent representation of communication actions  
**Related:** `docs/architecture/principle-dialog-not-technology.md`, `docs/architecture/unified-communication-experience.md`

## 1. Purpose and boundaries

The EiraOS Dialog Protocol (EDP) is an internal semantic envelope for actions in a conversation. It does not replace SMS, SMTP, SIP, XMPP, WhatsApp, or other external protocols. Adapters translate between EDP and the external protocols they support.

EDP 1.0 defines a common envelope and a deliberately controlled action taxonomy. It does not itself provide delivery, encryption, identity, payment, media transport, or truth verification. Those guarantees must come from implementations and their underlying systems, and must be reported honestly.

**Core rule:** no EDP message may require one specific transport. A route is a delivery mechanism, not the meaning of the action.

## 2. Design principles

1. **Conversation follows the object.** A conversation is anchored to a stable object or conversation record, not to an app or channel. Use a canonical reference such as `obj:project:42`; the exact object-reference registry remains a separate contract.
2. **Actions are semantic.** Action types describe the user's communication intent, not an external protocol.
3. **Transport is technical metadata.** Keep route details out of the primary conversation UX, but expose relevant route, privacy, cost, reachability, delivery, and failure information when it affects the user's decision.
4. **No silent material change.** Do not silently fall back to a route if it materially changes privacy, cost, recipient reachability, delivery guarantees, or user expectations. Ask for consent or report the limitation.
5. **Trust is evidence, not truth.** Provenance, signature validity, identity assurance, and content credibility are different properties. A numeric score or color is not proof that a message is true.
6. **Temporal history is explicit.** Events have timestamps and may refer to an event they supersede; consumers must not silently erase history.
7. **Capabilities are declared.** Adapters must state what they support, including lossy mappings and relevant security constraints.
8. **Implementation status is evidence-based.** A specification does not imply that a daemon, adapter, UI, or integration test exists.

## 3. Action taxonomy

The initial taxonomy is:

| Type | Meaning |
|---|---|
| `utterance` | Text or other conversational message |
| `live_session` | Call/meeting lifecycle signalling; media travels outside EDP |
| `artifact_shared` | Reference to a shared file, image, or document |
| `commitment_proposed` | Proposed meeting, task, or commitment |
| `commitment_accepted` | Acceptance of a referenced commitment |
| `commitment_declined` | Decline of a referenced commitment |
| `value_transfer_requested` | Request to initiate a payment or transfer |
| `value_transfer_confirmed` | Report that a transfer has been confirmed by an authoritative provider |
| `consent_requested` | Request for consent with explicit scope and purpose |
| `consent_granted` | Record of consent, with evidence reference where available |
| `presence_changed` | Presence-state change |

New action types require an intentional specification change and compatibility review. Minor releases may add backward-compatible types only if consumers are required to handle unknown types safely; a major release is required for incompatible envelope or interpretation changes. An unsupported action must fail explicitly rather than be misinterpreted.

## 4. Canonical envelope

Each EDP event is a UTF-8 JSON object. For newline-framed IPC, each complete JSON object occupies one line; transports must define framing, size limits, and error behavior separately.

Example:

```json
{
  "edp": "1.0",
  "id": "0190f5a0-0000-7000-8000-000000000001",
  "conversation_id": "obj:project:42",
  "participants": [
    {"identity": "did:eira:anne", "role": "member"},
    {"identity": "external:sms:+4512345678", "role": "member"}
  ],
  "action": {
    "type": "utterance",
    "content": {"text": "Kan vi mødes torsdag?", "lang": "da"}
  },
  "transport": {
    "preferred": ["eira-native", "xmpp", "sms"],
    "actual": "sms",
    "degraded": true,
    "error": {"code": "E_DEGRADED_CONTENT", "detail": "The external recipient receives text only"}
  },
  "veritas": {
    "status": "unassessed",
    "trust_score": null,
    "evidence_refs": []
  },
  "temporal": {
    "created_at": "2026-10-21T10:00:00Z",
    "valid_from": null,
    "supersedes": null
  }
}
```

### 4.1 Required fields and semantics

- `edp`: protocol version string.
- `id`: unique event identifier. Receivers should deduplicate repeated IDs.
- `conversation_id`: stable conversation/object reference, not a transport or account ID.
- `participants`: identities and roles relevant to the action. An external participant may be represented by a scheme-qualified address; this is not automatically a verified identity.
- `action.type`: one of the taxonomy values above.
- `action.content`: content matching the selected action type.
- `transport.degraded`: required boolean. True when the selected representation loses meaningful capability or fidelity.
- `transport.actual`: actual route, when known. It must not be populated with a preferred-but-unused route.
- `transport.error`: structured error information when a routing or delivery error is known. Absence of an error does not mean delivery succeeded.
- `veritas`: required assessment container. `status` distinguishes `unassessed`, `assessed`, and `unavailable`; `trust_score` may be null. Evidence references are references, not proof by themselves.
- `temporal.created_at`: event creation time in RFC 3339 / ISO 8601 format with timezone.
- `temporal.valid_from`: optional time at which the event becomes applicable.
- `temporal.supersedes`: optional ID of a prior event superseded by this one. Supersession preserves audit history and does not by itself revoke a delivered message.

## 5. Action content

- `utterance`: `text` and optional BCP 47 `lang`, reply reference, and artifact references.
- `live_session`: lifecycle operation (`start`, `join`, `end`, or `reject`), optional media capabilities, and a session reference. EDP signals session intent/lifecycle only; real-time audio/video is out of band.
- `artifact_shared`: artifact reference and optional MIME type and provenance reference. Do not treat a claimed C2PA field as validated unless validation actually occurred.
- `commitment_proposed`: description and optional time/location references.
- `commitment_accepted` / `commitment_declined`: referenced commitment ID and optional decline reason.
- `value_transfer_requested`: decimal amount represented as a string, ISO 4217 currency, and optional route hints. This event requests a transfer; it does not authorize or execute payment.
- `value_transfer_confirmed`: provider/transfer reference and confirmation evidence. Emit only when an authoritative result supports the claim.
- `consent_requested`: explicit scopes and purpose.
- `consent_granted`: consent reference and evidence reference where available. A message claiming consent is not a substitute for the required authorization workflow.
- `presence_changed`: declared presence state and optional expiry. Presence is time-sensitive and must not be treated as a guarantee of reachability.

Detailed action-specific schemas may be tightened in a compatible minor revision. Until then, producers and consumers must validate the fields they rely on and reject malformed or unsupported security-sensitive actions.

## 6. Adapter contract

Every adapter documents:
- supported EDP versions and action types;
- external protocol and account requirements;
- mapping from each supported action to and from EDP;
- which fields, guarantees, or semantics are lost;
- authentication, privacy, delivery receipt, retry, and idempotency behavior;
- health and capability reporting.

Conceptual interface:

```text
capabilities() -> declared supported actions and constraints
health()       -> availability plus diagnostic detail
send(event)    -> accepted/queued/delivered/failed result, with evidence
receive()      -> event or explicit mapping/error result
```

Requirements:

1. Mapping is explicit and documented; unsupported actions return `E_UNSUPPORTED_ACTION`.
2. A queued or accepted send is not reported as delivered. Delivery claims require a delivery receipt or equivalent evidence.
3. Retries must be bounded and designed for idempotency; uncertain outcomes must not cause duplicate side effects.
4. An unhealthy adapter must not be selected for execution. Health is advisory and can race with a later failure, so execution must still handle failure.
5. Lossy mapping sets `transport.degraded=true` and describes the limitation. A fallback that changes privacy, cost, recipient, or delivery expectations requires user policy/consent.
6. Protocol-specific details belong in transport metadata or adapter-private state, not in semantic action fields.
7. Never log message content, credentials, or sensitive metadata by default. Apply least privilege, retention limits, and redaction.

Minimum error codes: `E_ROUTE_UNAVAILABLE`, `E_PARTY_UNREACHABLE`, `E_UNSUPPORTED_ACTION`, `E_DEGRADED_CONTENT`, `E_AUTH_FAILED`, `E_DELIVERY_UNKNOWN`, `E_DELIVERY_FAILED`, `E_INVALID_MESSAGE`, `E_POLICY_DENIED`.

## 7. Route selection

Route selection is a policy decision, not merely “first healthy adapter wins”:

1. Check user intent, recipient reachability, authorization, provider capability, and user preferences.
2. Exclude routes that cannot carry the action or violate privacy/security/cost constraints.
3. Evaluate preferred routes among the remaining eligible routes.
4. If a fallback materially changes expectations, obtain consent or clearly report the trade-off before sending.
5. If no permitted route remains, return `E_ROUTE_UNAVAILABLE`; do not claim success.
6. Record the actual route and any degradation after selection. Report later delivery state changes as separate status events or receipts.

## 8. Trust, identity, and payments

- Identity validation and step-up authentication are separate from EDP syntax validation.
- `veritas` records the assessment state and evidence references. Do not assume `veritasd` exists or provides a particular score until verified in the repository.
- EDP does not define a universal trust-score algorithm or a universal green/yellow/red threshold.
- A payment request is not a payment instruction with authority. Wallet, payment, consent, and identity services must apply their own authorization and confirmation requirements.
- EUDI, C2PA, QEAA, or other references must only be emitted with accurate claims about what was checked and by whom.

## 9. Candidate component boundaries

Potential responsibilities for `intentd`, `presenced`, `graphd`, `veritasd`, `identityd`, `walletd`, and `contextd` must be confirmed against actual repository code before being treated as architecture facts. This specification does not establish that these daemons or integrations are implemented.

A future implementation should separate: intent interpretation, EDP validation, policy/routing, transport adapters, durable event storage, identity/authorization, trust evidence, and presentation. UI components must not implement transport or privileged system logic.

## 10. Acceptance criteria for an implementation

1. Schema validation rejects malformed envelopes, unknown required fields/types, and invalid version values.
2. A conversation can span two supported routes without requiring the user to switch conversation context.
3. Failed or uncertain delivery is never presented as successful delivery.
4. Lossy mappings are marked degraded and surfaced when relevant to user expectations.
5. A prohibited or unhealthy route is not executed; execution-time failures are handled.
6. Retries and duplicate events do not duplicate non-idempotent side effects.
7. Supersession preserves history and has defined consumer behavior.
8. Trust and provenance claims can be traced to recorded evidence; no numeric score is presented as proof of truth.
9. Sensitive content and metadata are covered by explicit access, retention, and logging policies.
10. Tests cover each action type, adapter mapping failures, fallback consent, version compatibility, and delivery-state transitions.

## 11. Versioning and review

- Producers declare the EDP version they emit; consumers define supported versions.
- Breaking envelope or semantic changes require a major version.
- Additive fields and action types require compatibility analysis and tests; consumers must fail safely on unknown action types.
- This document remains a draft until reviewed against existing IPC/event contracts, daemon responsibilities, security policy, and integration tests.
