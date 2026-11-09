import { invoke } from "@tauri-apps/api/core";

/**
 * The user's decisions on a gate proposal. They go through the app's Rust
 * core, which signs each one with the session's consent key (trusted path,
 * GATE-KERNEL bilag A pkt. 1). This webview never sees the key, so neither
 * it nor any other program can produce a valid decision on its own.
 */
export type GateDecisionTarget = {
  actionId: string;
  contentHash: string;
  renderingHash: string;
};

type TestGate = (verb: "consent" | "confirm", target: GateDecisionTarget) => Promise<unknown>;

declare global {
  interface Window {
    __EIRA_TEST_GATE__?: TestGate;
  }
}

function args(target: GateDecisionTarget) {
  return {
    actionId: target.actionId,
    contentHash: target.contentHash,
    renderingHash: target.renderingHash,
  };
}

export async function consentTo<T = unknown>(target: GateDecisionTarget): Promise<T> {
  if (window.__EIRA_TEST_GATE__) return window.__EIRA_TEST_GATE__("consent", target) as Promise<T>;
  return invoke<T>("gate_consent", args(target));
}

export async function confirm<T = unknown>(target: GateDecisionTarget): Promise<T> {
  if (window.__EIRA_TEST_GATE__) return window.__EIRA_TEST_GATE__("confirm", target) as Promise<T>;
  return invoke<T>("gate_confirm", args(target));
}
