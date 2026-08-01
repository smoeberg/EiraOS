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
  if (typeof error === "string") {
    try {
      const value = JSON.parse(error) as { message?: unknown };
      if (typeof value.message === "string") return value.message;
    } catch {
      return error;
    }
  }
  return error instanceof Error ? error.message : "Ukendt IPC-fejl";
}
