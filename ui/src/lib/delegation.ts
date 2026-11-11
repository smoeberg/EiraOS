import { invoke } from "@tauri-apps/api/core";

import { sendIpcRequest } from "./ipc";

/**
 * "På vegne af" (specs/EIRA-DELEGATION-1.0.md). The model may only prepare
 * actions; the user still consents to and confirms each one.
 *
 * Giving the model that power is a decision: `propose` returns the exact
 * text to show, and `approve` goes through the app's Rust core, which signs
 * it with the session's consent key. Neither this webview nor any other
 * program can create a delegation on its own.
 */
export type DelegationScope = { actions: ["prepare"]; targets: string[] };

export type DelegationProposal = {
  proposal_id: string;
  content_hash: string;
  rendering: { text: string; hash: string; lang: string };
};

export function propose(
  sessionId: string,
  delegeeId: string,
  scope: DelegationScope,
  expiresInSeconds: number,
): Promise<DelegationProposal> {
  return sendIpcRequest<DelegationProposal>("delegationd", "delegation.propose", {
    session_id: sessionId,
    delegee_id: delegeeId,
    scope,
    expires_in: expiresInSeconds,
  });
}

/** Call only after the user has seen `proposal.rendering.text` and said yes. */
export function approve<T = unknown>(proposal: DelegationProposal): Promise<T> {
  return invoke<T>("delegation_create", {
    proposalId: proposal.proposal_id,
    contentHash: proposal.content_hash,
    renderingHash: proposal.rendering.hash,
  });
}

/** Revoking takes power away and needs no proof. */
export function revoke(sessionId: string, delegationId: string): Promise<{ status: string }> {
  return sendIpcRequest("delegationd", "delegation.revoke", {
    session_id: sessionId,
    delegation_id: delegationId,
  });
}
