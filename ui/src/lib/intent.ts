import { approve, propose as proposeDelegation } from "./delegation";
import { confirm, consentTo } from "./gate";
import { sendIpcRequest } from "./ipc";

/**
 * The first whole path (UDVIKLINGSPLAN F1b): a sentence in the IntentBar, or
 * a button in the power menu, becomes a proposal to the Gate; the person
 * decides in the consent agent's own window; this module only reports what
 * actually happened.
 *
 * This webview never shows the Gate's rendering as something to approve:
 * that text is shown by the consent agent (EIRA-CONSENT-AGENT), and it
 * passes only the action id. Every outcome has a truthful message and,
 * where one exists, a safe next step (MASTER-PLAN principles 13-14).
 */

export type PowerAction = "poweroff" | "reboot" | "suspend";

type GateReply = {
  decision?: string | null;
  action_id?: string | null;
  error?: string | null;
  detail?: string | null;
  state?: string | null;
  content_hash?: string | null;
  data?: { rendering?: { hash?: string } };
};

type ModelReply = {
  gate?: GateReply;
  action_type?: string;
  abstain?: string;
  error?: string;
  needs_delegation?: { delegee_id: string; target: string };
};

export type Proposal = {
  actionId: string;
  actionType: string;
  contentHash: string;
  /** Only passed on to the Rust core; never shown here. */
  renderingHash: string;
};

export type IntentOutcome =
  | { kind: "login_required" }
  | { kind: "not_understood"; reason: string }
  | { kind: "model_unavailable" }
  | { kind: "needs_delegation"; delegeeId: string; target: string; actionType: string }
  | { kind: "awaiting_consent"; proposal: Proposal }
  | { kind: "refused"; code: string }
  | { kind: "declined" }
  | { kind: "closed" }
  | { kind: "agent_unavailable" }
  | { kind: "done"; state: string; visibleState: string | null }
  | { kind: "failed"; message: string };

/** How long the model may prepare on the person's behalf (the protocol's maximum). */
const DELEGATION_SECONDS = 30 * 24 * 3600;

async function sessionId(): Promise<string | null> {
  const who = await sendIpcRequest<{ session_id?: string | null; authenticated?: boolean }>(
    "identityd",
    "identity.session",
    {},
  );
  return who.authenticated && who.session_id ? who.session_id : null;
}

function fromGate(gate: GateReply | undefined, actionType: string): IntentOutcome {
  if (!gate) return { kind: "failed", message: "Gaten svarede ikke." };
  // Pending is the Gate holding the action for the person's decision:
  // E_NEED_CONSENT (irreversible) or ready for confirmation.
  if (gate.state === "pending" && gate.action_id && gate.content_hash) {
    return {
      kind: "awaiting_consent",
      proposal: {
        actionId: gate.action_id,
        actionType,
        contentHash: gate.content_hash,
        renderingHash: gate.data?.rendering?.hash ?? "",
      },
    };
  }
  if (gate.state === "executed") return { kind: "done", state: "executed", visibleState: null };
  return { kind: "refused", code: gate.error ?? "E_UNKNOWN" };
}

/** A sentence from the IntentBar, through the model process. */
export async function ask(text: string): Promise<IntentOutcome> {
  const session = await sessionId();
  if (!session) return { kind: "login_required" };
  const reply = await sendIpcRequest<ModelReply>("modeld", "model.prepare", {
    session_id: session,
    text,
    now: new Date().toISOString(),
    lang: "da",
  });
  if (reply.abstain) return { kind: "not_understood", reason: reply.abstain };
  if (reply.error) return { kind: "model_unavailable" };
  if (reply.needs_delegation) {
    return {
      kind: "needs_delegation",
      delegeeId: reply.needs_delegation.delegee_id,
      target: reply.needs_delegation.target,
      actionType: reply.action_type ?? "",
    };
  }
  return fromGate(reply.gate, reply.action_type ?? "");
}

/** The manual path: the person proposes a power action directly. */
export async function proposePower(action: PowerAction): Promise<IntentOutcome> {
  const session = await sessionId();
  if (!session) return { kind: "login_required" };
  const gate = await sendIpcRequest<GateReply>("intentd", "gate.propose", {
    session_id: session,
    origin: "user",
    lang: "da",
    edp: {
      eira_system: "1",
      id: `sys-${crypto.randomUUID().replace(/-/g, "")}`,
      operation: "power.request_action",
      input: { action },
      created_at: new Date().toISOString(),
    },
  });
  return fromGate(gate, "system:power.request_action");
}

function agentOutcome(error: unknown): IntentOutcome {
  const text = error instanceof Error ? error.message : String(error);
  if (text.includes("E_CONSENT_AGENT_UNAVAILABLE")) return { kind: "agent_unavailable" };
  if (text.includes("not logged in")) return { kind: "login_required" };
  return { kind: "failed", message: text };
}

type AgentReply = {
  status?: string;
  error?: string;
  steps?: { step: string; result: GateReply & { result?: { visible_state?: string } } }[];
};

/** The person decides in the consent agent's window; this waits for it. */
export async function decide(proposal: Proposal): Promise<IntentOutcome> {
  const target = {
    actionId: proposal.actionId,
    contentHash: proposal.contentHash,
    renderingHash: proposal.renderingHash,
  };
  let reply: AgentReply & GateReply;
  try {
    reply = await consentTo<AgentReply & GateReply>(target);
    if (reply.status === "declined") return { kind: "declined" };
    if (reply.status === "closed") return { kind: "closed" };
    if (reply.status === "error") return { kind: "failed", message: reply.error ?? "Samtykkevinduet fejlede." };
    if (reply.status !== "decided") {
      // Without the agent (development): consent and confirm are separate.
      if (reply.error) return { kind: "refused", code: reply.error };
      await confirm(target);
    }
  } catch (error) {
    return agentOutcome(error);
  }
  return status(proposal);
}

/** The Gate's record is the truth about what happened, not any reply above. */
export async function status(proposal: Proposal): Promise<IntentOutcome> {
  const session = await sessionId();
  if (!session) return { kind: "login_required" };
  const found = await sendIpcRequest<{ state: string; result?: { visible_state?: string } | null }>(
    "intentd",
    "gate.status",
    { action_id: proposal.actionId, session_id: session },
  );
  if (found.state === "pending") return { kind: "refused", code: "E_NOT_CONFIRMED" };
  return { kind: "done", state: found.state, visibleState: found.result?.visible_state ?? null };
}

/** The person lets Eira prepare this kind of action; decided in the agent's window. */
export async function delegate(outcome: Extract<IntentOutcome, { kind: "needs_delegation" }>): Promise<IntentOutcome> {
  const session = await sessionId();
  if (!session) return { kind: "login_required" };
  const proposal = await proposeDelegation(
    session,
    outcome.delegeeId,
    { actions: ["prepare"], targets: [outcome.target] },
    DELEGATION_SECONDS,
  );
  try {
    const reply = await approve<{ status?: string; error?: string }>(proposal);
    if (reply?.status === "declined") return { kind: "declined" };
    if (reply?.status === "closed") return { kind: "closed" };
    if (reply?.status === "error") return { kind: "failed", message: reply.error ?? "Samtykkevinduet fejlede." };
  } catch (error) {
    return agentOutcome(error);
  }
  return { kind: "done", state: "delegated", visibleState: null };
}

const POWER_DONE: Record<string, string> = {
  requested: "Anmodningen er sendt. Computeren gør det nu.",
};

const REFUSED: Record<string, string> = {
  E_UNAUTHORIZED: "Du har ikke ret til det på denne computer. Rettigheder kommer fra din organisation (Fleet).",
  E_NOT_CONFIRMED: "Handlingen blev ikke bekræftet. Intet er sket.",
  E_CONSENT: "Godkendelsen gælder ikke længere. Prøv igen.",
  E_POLICY: "Det tillader EiraOS' regler ikke.",
  E_STEP_UP_REQUIRED: "Det kræver en stærkere godkendelse (MitID), som ikke er sat op endnu.",
  E_EXECUTOR_UNAVAILABLE: "Systemet kan ikke udføre det lige nu. Intet er sket.",
};

/** One truthful sentence per outcome. */
export function describe(outcome: IntentOutcome): string {
  switch (outcome.kind) {
    case "login_required":
      return "Log ind for at bruge Eira.";
    case "not_understood":
      return "Eira forstod det ikke. Prøv fx “sluk computeren”, “genstart” eller “sæt computeren i dvale”.";
    case "model_unavailable":
      return "Eira kan ikke fortolke lige nu. Prøv igen om lidt.";
    case "needs_delegation":
      return "Eira må ikke forberede det på dine vegne endnu.";
    case "awaiting_consent":
      return "Godkend eller afvis i samtykkevinduet.";
    case "declined":
      return "Du afviste. Intet er sket.";
    case "closed":
      return "Samtykkevinduet blev lukket. Intet er sket.";
    case "agent_unavailable":
      return "Samtykkevinduet kører ikke, så intet kan godkendes lige nu.";
    case "refused":
      return REFUSED[outcome.code] ?? `Gaten afviste handlingen (${outcome.code}). Intet er sket.`;
    case "done":
      if (outcome.state === "delegated") return "Eira må nu forberede det på dine vegne. Du godkender stadig hver gang.";
      if (outcome.state === "executed") {
        return (outcome.visibleState && POWER_DONE[outcome.visibleState]) ?? "Udført.";
      }
      if (outcome.state === "failed") return "Det mislykkedes. Se loggen for detaljer.";
      return `Status: ${outcome.state}.`;
    case "failed":
      return "Noget gik galt, og intet er sket.";
  }
}
