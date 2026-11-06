import { useCallback, useEffect, useRef, useState } from "react";
import {
  power,
  systemErrorMessage,
  type PowerAction,
  type PowerStatus,
} from "../lib/system";

const LABEL: Record<PowerAction, string> = {
  suspend: "Slumre",
  reboot: "Genstart",
  poweroff: "Sluk",
};

const QUESTION: Record<PowerAction, string> = {
  suspend: "Vil du lade computeren slumre?",
  reboot: "Vil du genstarte computeren? Åbne programmer lukkes.",
  poweroff: "Vil du slukke computeren? Åbne programmer lukkes.",
};

const REFRESH_MS = 60_000;

function batteryText(status: PowerStatus): string | null {
  const battery = status.battery;
  if (!battery) return null;
  const percent = `${Math.round(battery.percentage)} %`;
  if (battery.state === "charging") return `${percent} · lader`;
  if (battery.state === "fully_charged") return `${percent} · fuldt opladet`;
  if (battery.time_to_empty_s) {
    const minutes = Math.round(battery.time_to_empty_s / 60);
    const hours = Math.floor(minutes / 60);
    return `${percent} · ${hours > 0 ? `${hours} t ` : ""}${minutes % 60} min tilbage`;
  }
  return percent;
}

/**
 * Battery and power actions from Ubuntu (UPower, systemd-logind) through
 * EiraSystemAPI. Shows only what the services report, and every action is
 * confirmed before it is sent.
 */
export function PowerMenu() {
  const [status, setStatus] = useState<PowerStatus | null>(null);
  const [statusError, setStatusError] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const [pending, setPending] = useState<PowerAction | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  const refresh = useCallback(async () => {
    try {
      setStatus(await power.status());
      setStatusError(null);
    } catch (error) {
      setStatusError(systemErrorMessage(error));
    }
  }, []);

  useEffect(() => {
    void refresh();
    const timer = window.setInterval(() => void refresh(), REFRESH_MS);
    return () => window.clearInterval(timer);
  }, [refresh]);

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpen(false);
        setPending(null);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  const confirm = useCallback(async () => {
    if (!pending) return;
    setBusy(true);
    setMessage(null);
    try {
      await power.request(pending, true);
      // logind accepted it; the machine changing state is the real confirmation.
      setMessage(pending === "suspend" ? "Computeren går i slumre…" : "Lukker ned…");
      setPending(null);
    } catch (error) {
      setMessage(systemErrorMessage(error));
    } finally {
      setBusy(false);
    }
  }, [pending]);

  const battery = status ? batteryText(status) : null;
  const actions: PowerAction[] = ["suspend", "reboot", "poweroff"];

  return (
    <div className="power-menu" ref={menuRef}>
      {battery && (
        <span className="battery-status" aria-label={`Batteri ${battery}`}>
          {battery}
        </span>
      )}
      <button
        type="button"
        className="header-button"
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => {
          setOpen((value) => !value);
          setPending(null);
          setMessage(null);
          void refresh();
        }}
      >
        Strøm
      </button>
      {open && (
        <div className="power-popover" role="menu" aria-label="Strøm">
          {statusError && <p className="power-note">{statusError}</p>}
          {!pending &&
            actions.map((action) => {
              const availability = status?.actions[action] ?? "unavailable";
              return (
                <button
                  key={action}
                  type="button"
                  role="menuitem"
                  disabled={availability === "unavailable"}
                  title={
                    availability === "needs_authentication"
                      ? "Kræver godkendelse"
                      : availability === "unavailable"
                        ? "Ikke muligt på denne computer lige nu"
                        : undefined
                  }
                  onClick={() => {
                    setPending(action);
                    setMessage(null);
                  }}
                >
                  {LABEL[action]}
                </button>
              );
            })}
          {pending && (
            <div className="power-confirm" role="alertdialog" aria-label={LABEL[pending]}>
              <p>{QUESTION[pending]}</p>
              <div>
                <button type="button" onClick={() => setPending(null)} disabled={busy}>
                  Annuller
                </button>
                <button type="button" className="danger" onClick={() => void confirm()} disabled={busy}>
                  {LABEL[pending]}
                </button>
              </div>
            </div>
          )}
          {message && (
            <p className="power-note" role="status">
              {message}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
