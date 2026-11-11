import { invoke } from "@tauri-apps/api/core";

/** EiraSystemAPI v1 (docs/architecture/eira-system-api.md). */
export type EiraErrorCode =
  | "INVALID_ARGUMENT"
  | "PERMISSION_DENIED"
  | "CONFIRMATION_REQUIRED"
  | "CAPABILITY_UNAVAILABLE"
  | "UNSUPPORTED"
  | "IO_ERROR"
  | "VERSION_MISMATCH"
  | "INTERNAL_ERROR";

export interface EiraError {
  code: EiraErrorCode;
  message: string;
  retryable: boolean;
  operation_id: string;
}

export interface EiraResponse<T> {
  api_version: "1";
  request_id: string;
  operation_id: string;
  result?: T;
  error?: EiraError;
}

export class EiraSystemError extends Error {
  constructor(public readonly detail: EiraError) {
    super(detail.message);
  }
}

export type Availability = "available" | "needs_authentication" | "unavailable";
export type PowerAction = "poweroff" | "reboot" | "suspend";
export type BatteryState =
  | "charging"
  | "discharging"
  | "empty"
  | "fully_charged"
  | "pending_charge"
  | "pending_discharge"
  | "unknown";

export interface PowerStatus {
  on_battery: boolean | null;
  battery: {
    percentage: number;
    state: BatteryState;
    time_to_empty_s?: number;
    time_to_full_s?: number;
  } | null;
  actions: Record<PowerAction, Availability>;
  sources: { upower: boolean; logind: boolean };
}

type SystemTransport = (request: {
  api_version: "1";
  request_id: string;
  operation: string;
  input: unknown;
}) => Promise<EiraResponse<unknown>>;

declare global {
  interface Window {
    __EIRA_TEST_SYSTEM__?: SystemTransport;
  }
}

let counter = 0;
function requestId(): string {
  counter += 1;
  const random =
    typeof crypto !== "undefined" && "randomUUID" in crypto
      ? crypto.randomUUID()
      : Math.random().toString(36).slice(2);
  return `ui-${counter}-${random}`;
}

export async function callSystem<T>(operation: string, input: unknown = {}): Promise<T> {
  const request = { api_version: "1" as const, request_id: requestId(), operation, input };
  const transport: SystemTransport =
    window.__EIRA_TEST_SYSTEM__ ?? ((req) => invoke<EiraResponse<unknown>>("eira_system", { request: req }));
  const response = (await transport(request)) as EiraResponse<T>;
  if (response.error) throw new EiraSystemError(response.error);
  if (response.result === undefined) {
    throw new EiraSystemError({
      code: "INTERNAL_ERROR",
      message: "Tomt svar fra EiraSystemAPI",
      retryable: false,
      operation_id: response.operation_id,
    });
  }
  return response.result;
}

// Read-only. Turning the machine off, restarting or suspending is a protected
// action: it is proposed as an intention and executed only through the Gate,
// never by a direct call from the UI.
export const power = {
  status: () => callSystem<PowerStatus>("power.get_status"),
};

export function systemErrorMessage(error: unknown): string {
  if (error instanceof EiraSystemError) return error.detail.message;
  return error instanceof Error ? error.message : "Ukendt fejl fra systemet";
}
