# EIRA Delegation Protocol v1.0

Status: Normative
Scope: human-to-model preparation delegation only.

## Security invariants

1. The model may prepare/propose only; it can never receive execute, decide or admin.
2. Delegations are bounded by action and target scope and expire automatically.
3. Delegation creation and revocation require an authenticated human session bound to the caller's OS UID.
4. A model proposal is accepted by the Gate only when an active delegation exists for that model, the requested action type is in scope, and the delegation's delegator is the human session used for the proposal.
5. Consent and confirmation remain human-only and continue through the existing Gate Kernel.
6. Delegation create/revoke/use are audit events. If the audit append fails, delegation creation is rolled back and delegated preparation is rejected.
7. The implementation fails closed on missing caller/session/delegation/audit state.

## JSON-RPC

- delegation.create
- delegation.revoke
- delegation.check
- delegation.list

The management API takes a session_id; the delegator identity is derived from the authenticated session and socket peer credentials rather than trusted request input.

## Scope

    {"actions":["prepare"],"targets":["intent:*"],"conditions":{}}

Targets support exact matches and a terminal * prefix.

## Lifecycle

Human -> delegation.create -> delegationd -> Delegation DB
Model -> gate.propose -> delegation check -> pending action
Human -> gate.consent / gate.confirm -> executor

The model never reaches the executor directly.
