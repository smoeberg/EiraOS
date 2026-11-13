import { useState } from "react";
import { ask, decide, delegate, describe, type IntentOutcome } from "../lib/intent";

interface IntentBarProps {
  onExecuted?: () => void | Promise<void>;
}

type NeedsDelegation = Extract<IntentOutcome, { kind: "needs_delegation" }>;

const GOOD = new Set(["done"]);
const WAITING = new Set(["awaiting_consent"]);

/**
 * The central input (UDVIKLINGSPLAN F1b). The sentence goes to the model
 * process, which may propose to the Gate; the person decides in the
 * consent agent's window, never here. What is shown afterwards is the
 * Gate's own record of what happened.
 */
export function IntentBar({ onExecuted }: IntentBarProps) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [outcome, setOutcome] = useState<IntentOutcome | null>(null);

  async function follow(first: IntentOutcome): Promise<IntentOutcome> {
    setOutcome(first);
    if (first.kind !== "awaiting_consent") return first;
    const final = await decide(first.proposal);
    setOutcome(final);
    return final;
  }

  async function run(work: () => Promise<IntentOutcome>) {
    if (busy) return;
    setBusy(true);
    try {
      const final = await follow(await work());
      if (final.kind === "done" && final.state === "executed") {
        setText("");
        await onExecuted?.();
      }
    } catch {
      setOutcome({ kind: "failed", message: "" });
    } finally {
      setBusy(false);
    }
  }

  async function submit() {
    const intent = text.trim();
    if (!intent) return;
    await run(() => ask(intent));
  }

  async function allow(needed: NeedsDelegation) {
    const intent = text.trim();
    await run(async () => {
      const given = await delegate(needed);
      // With the permission in place, the same sentence goes again.
      return given.kind === "done" ? ask(intent) : given;
    });
  }

  const tone = outcome
    ? GOOD.has(outcome.kind)
      ? "intent-ok"
      : WAITING.has(outcome.kind)
        ? "intent-waiting"
        : "intent-error"
    : "";

  return (
    <form
      className="intent-bar"
      role="search"
      onSubmit={(event) => {
        event.preventDefault();
        void submit();
      }}
    >
      <input
        type="text"
        value={text}
        placeholder="Beskriv din intention…"
        aria-label="Intention"
        disabled={busy}
        onChange={(event) => setText(event.target.value)}
      />
      <button type="submit" disabled={busy || !text.trim()}>
        {busy ? "Venter…" : "Spørg Eira"}
      </button>
      {outcome ? (
        <p className={`intent-status ${tone}`} role="status">
          {describe(outcome)}
        </p>
      ) : null}
      {outcome?.kind === "needs_delegation" ? (
        <button type="button" className="intent-allow" disabled={busy} onClick={() => void allow(outcome)}>
          Giv Eira lov til at forberede det
        </button>
      ) : null}
    </form>
  );
}
