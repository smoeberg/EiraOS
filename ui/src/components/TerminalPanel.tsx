import { useCallback, useEffect, useRef, useState } from "react";
import { FitAddon } from "@xterm/addon-fit";
import { Terminal } from "@xterm/xterm";
import "@xterm/xterm/css/xterm.css";
import {
  terminalBackend,
  terminalErrorMessage,
  type TerminalSession,
} from "../lib/terminal";

type Status =
  | { kind: "starting" }
  | { kind: "running"; session: TerminalSession }
  | { kind: "exited"; session: TerminalSession; code: number | null }
  | { kind: "error"; message: string };

interface TerminalPanelProps {
  onClose: () => void;
}

const THEME = {
  background: "#0b1117",
  foreground: "#e6edf3",
  cursor: "#5ccfe6",
  selectionBackground: "#264f78",
  black: "#0b1117",
  brightBlack: "#6e7681",
  cyan: "#5ccfe6",
  brightCyan: "#95e6f5",
};

/**
 * A real Linux terminal: the user's own shell in a PTY (SYS-TERM-01).
 * Presentation only; the session, its shell and its cleanup live in Rust.
 */
export function TerminalPanel({ onClose }: TerminalPanelProps) {
  const hostRef = useRef<HTMLDivElement>(null);
  const [status, setStatus] = useState<Status>({ kind: "starting" });
  const [generation, setGeneration] = useState(0);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    const backend = terminalBackend();
    const term = new Terminal({
      cursorBlink: true,
      fontFamily: "'Ubuntu Mono', 'DejaVu Sans Mono', monospace",
      fontSize: 14,
      scrollback: 5000,
      theme: THEME,
    });
    const fit = new FitAddon();
    term.loadAddon(fit);
    term.open(host);
    try {
      fit.fit();
    } catch {
      // Not laid out yet (hidden or zero-sized); the observer fits it later.
    }

    let sessionId: number | null = null;
    let disposed = false;
    const unlisten: Array<() => void> = [];

    const start = async () => {
      try {
        unlisten.push(
          await backend.onOutput((event) => {
            if (event.session_id === sessionId) term.write(event.data);
          }),
        );
        unlisten.push(
          await backend.onExit((event) => {
            if (event.session_id !== sessionId) return;
            setStatus((current) =>
              current.kind === "running"
                ? { kind: "exited", session: current.session, code: event.code }
                : current,
            );
            sessionId = null;
          }),
        );
        const session = await backend.create(Math.max(term.cols, 2), Math.max(term.rows, 2));
        if (disposed) {
          void backend.close(session.session_id);
          return;
        }
        sessionId = session.session_id;
        setStatus({ kind: "running", session });
        term.focus();
      } catch (error) {
        if (!disposed) setStatus({ kind: "error", message: terminalErrorMessage(error) });
      }
    };
    void start();

    const input = term.onData((data) => {
      if (sessionId !== null) void backend.write(sessionId, data);
    });
    const resize = term.onResize(({ cols, rows }) => {
      if (sessionId !== null) void backend.resize(sessionId, cols, rows);
    });
    const observer =
      typeof ResizeObserver === "undefined"
        ? null
        : new ResizeObserver(() => {
            try {
              fit.fit();
            } catch {
              // Ignore transient zero-size layouts.
            }
          });
    observer?.observe(host);

    return () => {
      disposed = true;
      observer?.disconnect();
      input.dispose();
      resize.dispose();
      unlisten.forEach((stop) => stop());
      if (sessionId !== null) void backend.close(sessionId);
      term.dispose();
    };
  }, [generation]);

  const restart = useCallback(() => {
    setStatus({ kind: "starting" });
    setGeneration((value) => value + 1);
  }, []);

  const interrupt = useCallback(() => {
    if (status.kind === "running") void terminalBackend().signal(status.session.session_id, "SIGINT");
  }, [status]);

  return (
    <section className="terminal-panel" role="region" aria-label="Terminal">
      <header className="terminal-bar">
        <span className="terminal-title">Terminal</span>
        <span className="terminal-status" aria-live="polite">
          {status.kind === "starting" && "Starter shell…"}
          {status.kind === "running" && `${status.session.shell} · ${status.session.cwd}`}
          {status.kind === "exited" &&
            `Shellen er afsluttet${status.code === null ? "" : ` (kode ${status.code})`}`}
          {status.kind === "error" && status.message}
        </span>
        <span className="terminal-actions">
          {status.kind === "running" && (
            <button type="button" onClick={interrupt} title="Afbryd det kørende program (Ctrl+C)">
              Afbryd
            </button>
          )}
          {(status.kind === "exited" || status.kind === "error") && (
            <button type="button" onClick={restart}>
              Ny shell
            </button>
          )}
          <button type="button" onClick={onClose} aria-label="Luk terminal">
            Luk
          </button>
        </span>
      </header>
      <div className="terminal-host" ref={hostRef} data-testid="terminal-host" />
    </section>
  );
}
