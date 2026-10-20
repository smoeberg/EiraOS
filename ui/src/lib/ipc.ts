import { invoke } from "@tauri-apps/api/core";

export type EiraDaemon =
  | "stated"
  | "identityd"
  | "fleetd"
  | "veritasd"
  | "intentd"
  | "graphd";

type TestIpc = (
  daemon: EiraDaemon,
  method: string,
  params: Record<string, unknown>,
) => Promise<unknown>;

declare global {
  interface Window {
    __EIRA_TEST_IPC__?: TestIpc;
  }
}

export async function sendIpcRequest<T>(
  daemon: EiraDaemon,
  method: string,
  params: Record<string, unknown> = {},
): Promise<T> {
  if (window.__EIRA_TEST_IPC__) {
    return window.__EIRA_TEST_IPC__(daemon, method, params) as Promise<T>;
  }
  return invoke<T>("send_ipc_request", { daemon, method, params });
}

export function ipcErrorMessage(error: unknown): string {
  const message = error instanceof Error ? error.message : error;
  if (typeof message !== "string") return "Ukendt IPC-fejl";

  try {
    const value = JSON.parse(message) as { message?: unknown };
    if (typeof value.message === "string") return value.message;
  } catch {
    // The error was plain text rather than a serialized IPC error object.
  }
  return message;
}
