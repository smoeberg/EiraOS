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

type TestDelegation = (proposal: DelegationProposal) => Promise<unknown>;

declare global {
  interface Window {
    __EIRA_TEST_DELEGATION__?: TestDelegation;
  }
}

/**
 * Asks the Rust core to have the person decide. On an installed system the
 * consent agent shows `proposal.rendering.text` in its own window; this
 * webview does not.
 */
export function approve<T = unknown>(proposal: DelegationProposal): Promise<T> {
  if (window.__EIRA_TEST_DELEGATION__) return window.__EIRA_TEST_DELEGATION__(proposal) as Promise<T>;
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
