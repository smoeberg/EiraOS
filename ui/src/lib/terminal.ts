import { invoke } from "@tauri-apps/api/core";
import type { UnlistenFn } from "@tauri-apps/api/event";
import { getCurrentWebviewWindow } from "@tauri-apps/api/webviewWindow";

/** A shell session owned by this window (see ui/src-tauri/src/terminal.rs). */
export interface TerminalSession {
  session_id: number;
  shell: string;
  cwd: string;
  pid: number | null;
}

export interface TerminalOutput {
  session_id: number;
  data: string;
}

export interface TerminalExit {
  session_id: number;
  code: number | null;
}

export type TerminalSignal = "SIGINT" | "SIGTERM" | "SIGHUP";

/** Typed terminal commands and events; never a generic command runner. */
export interface TerminalBackend {
  create(cols: number, rows: number): Promise<TerminalSession>;
  write(sessionId: number, data: string): Promise<void>;
  resize(sessionId: number, cols: number, rows: number): Promise<void>;
  signal(sessionId: number, signal: TerminalSignal): Promise<void>;
  close(sessionId: number): Promise<void>;
  onOutput(handler: (event: TerminalOutput) => void): Promise<UnlistenFn>;
  onExit(handler: (event: TerminalExit) => void): Promise<UnlistenFn>;
}

declare global {
  interface Window {
    __EIRA_TEST_TERMINAL__?: TerminalBackend;
  }
}

const OUTPUT_EVENT = "eira://terminal/output";
const EXIT_EVENT = "eira://terminal/exit";

const tauriBackend: TerminalBackend = {
  create: (cols, rows) => invoke<TerminalSession>("terminal_create", { cols, rows }),
  write: (sessionId, data) => invoke("terminal_write", { sessionId, data }),
  resize: (sessionId, cols, rows) => invoke("terminal_resize", { sessionId, cols, rows }),
  signal: (sessionId, signal) => invoke("terminal_signal", { sessionId, signal }),
  close: (sessionId) => invoke("terminal_close", { sessionId }),
  // Events are emitted only to the window that owns the session.
  onOutput: (handler) =>
    getCurrentWebviewWindow().listen<TerminalOutput>(OUTPUT_EVENT, (event) => handler(event.payload)),
  onExit: (handler) =>
    getCurrentWebviewWindow().listen<TerminalExit>(EXIT_EVENT, (event) => handler(event.payload)),
};

export function terminalBackend(): TerminalBackend {
  return window.__EIRA_TEST_TERMINAL__ ?? tauriBackend;
}

/** Backend errors look like "code: message"; show the message to people. */
export function terminalErrorMessage(error: unknown): string {
  const text = error instanceof Error ? error.message : String(error);
  if (text.startsWith("permission_denied")) return "Terminalen kører aldrig som root.";
  if (text.startsWith("limit")) return "Der er allerede åbnet det maksimale antal terminaler.";
  if (text.startsWith("spawn_failed")) return "Shellen kunne ikke startes.";
  const separator = text.indexOf(": ");
  return separator > 0 ? text.slice(separator + 2) : text;
}
