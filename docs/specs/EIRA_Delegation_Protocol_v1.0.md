# EIRA Delegation Protocol v1.1

Status: Normative
Scope: human-to-model preparation delegation only ("på vegne af", GATE-KERNEL bilag A pkt. 1).

**v1.1 (November 2026):** A delegation is now created only through the trusted path (two steps, proof with the session's consent key), and the gate records the delegation in its own audit chain.

## Security invariants

1. The model may only prepare (propose). `execute`, `decide`, `admin`, `consent`, `confirm` and `*` can never be delegated.
2. Delegations are bounded by action and target scope and expire automatically (at most 30 days).
3. **Creating a delegation is a decision and takes the trusted path** (§ Lifecycle). The delegator must hold an authenticated human session bound to the caller's OS UID, *and* the request must carry a proof made with that session's consent key (`app/gate/consent_proof.py`, verb `delegate`). Only the desktop app's Rust core holds the key, so another program running as the same user, even with the session id, cannot delegate. The command line cannot create delegations.
4. A model proposal passes gate layer 4 only under an active delegation from **the human whose session it acts in**, for that model and the action type (`intent:<type>`). Another human's delegation never counts.
5. Consent and confirmation remain human-only and continue through the existing Gate Kernel.
6. The gate records which delegation let the model propose in its own hash-chained audit entry (`delegation: {delegation_id, delegator, delegee, target}`). No other system is called on the decision path. Creating and revoking are also appended to stated's audit log; if that append fails, creation is rolled back.
7. Revoking needs only the delegator's own session: it takes power away.
8. The implementation fails closed on missing caller, session, proof or delegation.

## JSON-RPC (eira-delegationd)

| Method | Who | Params | Result |
|---|---|---|---|
| `delegation.propose` | human, own session | `session_id`, `delegee_id`, `scope`, `expires_in` (seconds) | `proposal_id`, `content_hash`, `rendering {text, hash, lang}` |
| `delegation.create` | the app's Rust core | `session_id`, `proposal_id`, `content_hash`, `rendering_hash`, `proof` | the delegation |
| `delegation.revoke` | the delegator | `session_id`, `delegation_id` | `revoked` / `not_found` |
| `delegation.list` | human, own session | `session_id` | own active delegations |
| `delegation.check` | any caller; a model only about itself | `delegee_id`, `action`, `target` | `valid` |

`proof = HMAC-SHA256(consent_key, "EIRA-CONSENT-V1" 0 "delegate" 0 uid 0 session_id 0 proposal_id 0 content_hash 0 rendering_hash)`. Shared test vectors: `tests/vectors/consent-proof.json`.

A proposal is single-use, bound to the delegator, the session, the content and the exact text shown, and expires after 5 minutes.

## Scope

    {"actions":["prepare"],"targets":["intent:*"],"conditions":{}}

Targets support exact matches and a terminal `*` prefix.

## Lifecycle

    App   -> delegation.propose  -> delegationd          (text the user will see)
    User  sees the text and says yes
    App   -> delegation_create (Tauri, signs with the consent key)
          -> delegation.create   -> delegationd -> app database (/data/eira-app.db)
    Model -> gate.propose        -> gate layer 4: delegation from this human? -> pending action
    Human -> gate.consent / gate.confirm (trusted path) -> executor

The model never reaches the executor directly.

## Open

- Delegations use wall-clock expiry, not the gate's boot-time clock.
- Revoking does not cancel the model's proposals that are already pending; the human still has to consent and confirm each one.
- A UI for giving and revoking delegations (`ui/src/lib/delegation.ts` is the client).
