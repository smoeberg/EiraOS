import { useState } from "react";
import { decide, describe, proposePower, type IntentOutcome, type PowerAction } from "../lib/intent";

const ACTIONS: { action: PowerAction; label: string }[] = [
  { action: "suspend", label: "Dvale" },
  { action: "reboot", label: "Genstart" },
  { action: "poweroff", label: "Sluk" },
];

/**
 * The manual path to power (MASTER-PLAN principle 14): the same Gate and the
 * same consent agent as the IntentBar, proposed by the person directly, so it
 * works when the model does not understand or is unavailable.
 *
 * Builder Mode only: ADR-0001 keeps system controls out of Explorer, where
 * power goes through the IntentBar.
 */
export function PowerMenu() {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [outcome, setOutcome] = useState<IntentOutcome | null>(null);

  async function request(action: PowerAction) {
    if (busy) return;
    setBusy(true);
    try {
      const first = await proposePower(action);
      setOutcome(first);
      if (first.kind === "awaiting_consent") setOutcome(await decide(first.proposal));
    } catch {
      setOutcome({ kind: "failed", message: "" });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="power-menu">
      <button
        type="button"
        className="header-button"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
      >
        Strøm
      </button>
      {open ? (
        <div className="power-menu-panel" role="menu" aria-label="Strøm">
          {ACTIONS.map(({ action, label }) => (
            <button
              key={action}
              type="button"
              role="menuitem"
              disabled={busy}
              onClick={() => void request(action)}
            >
              {label}
            </button>
          ))}
          {outcome ? <p role="status">{describe(outcome)}</p> : null}
        </div>
      ) : null}
    </div>
  );
}
