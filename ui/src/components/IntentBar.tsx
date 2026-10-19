import { useState } from "react";
import { sendIpcRequest } from "../lib/ipc";

interface IntentBarProps {
  onExecuted?: () => void | Promise<void>;
}

interface IntentExecuteResult {
  state?: { id?: string; payload?: Record<string, unknown> };
  knowledge?: Record<string, unknown>;
}

function violationMessage(error: unknown): string | null {
  const raw =
    error instanceof Error && typeof (error as { message?: unknown }).message === "string"
      ? (error as { message: string }).message
      : error;
  if (typeof raw !== "string") return null;
  try {
    const parsed = JSON.parse(raw) as {
      code?: number;
      data?: { user_message?: string; step_up_required?: boolean };
    };
    if (parsed?.data?.step_up_required) {
      return parsed.data.user_message ?? "Step-up godkendelse påkrævet.";
    }
    if (parsed?.data?.user_message) return parsed.data.user_message;
    if (parsed?.code === -32002) return "Intentionen skal præciseres — omformuler.";
  } catch {
    return null;
  }
  return null;
}

export function IntentBar({ onExecuted }: IntentBarProps) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    const intent = text.trim();
    if (!intent || busy) return;
    setBusy(true);
    setMessage(null);
    setError(null);
    try {
      await sendIpcRequest<IntentExecuteResult>("intentd", "intent.execute", { intent });
      setText("");
      setMessage("Intentionen er eksekveret.");
      await onExecuted?.();
    } catch (caught) {
      const violation = violationMessage(caught);
      if (violation) setError(violation);
      else if (String(caught).includes("CLARIFICATION_REQUIRED")) {
        setError("Intentionen skal præciseres — omformuler.");
      } else setError("Intentionen kunne ikke eksekveres.");
    } finally {
      setBusy(false);
    }
  }

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
        {busy ? "Eksekverer…" : "Eksekvér"}
      </button>
      {message ? <p className="intent-status intent-ok">{message}</p> : null}
      {error ? <p className="intent-status intent-error">{error}</p> : null}
    </form>
  );
}
