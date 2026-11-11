import { invoke } from "@tauri-apps/api/core";

/** Result of the desktop login (ui/src-tauri/src/login.rs). */
export type DesktopLogin = {
  session_id: string;
  identity: string;
  expires_at: string | null;
};

declare global {
  interface Window {
    __TAURI_INTERNALS__?: unknown;
    __EIRA_TEST_DESKTOP_LOGIN__?: () => Promise<DesktopLogin>;
  }
}

/** Running inside the EiraOS desktop app (Tauri), not a browser. */
export function isDesktop(): boolean {
  return Boolean(window.__TAURI_INTERNALS__ || window.__EIRA_TEST_DESKTOP_LOGIN__);
}

/**
 * Desktop login: the app opens the system browser on Entra, catches the
 * loopback redirect itself and completes the login with identityd. The
 * authorization code never reaches this webview; only the session id does.
 */
export async function desktopLogin(): Promise<DesktopLogin> {
  if (window.__EIRA_TEST_DESKTOP_LOGIN__) return window.__EIRA_TEST_DESKTOP_LOGIN__();
  return invoke<DesktopLogin>("desktop_login");
}

/** Forget the session and the consent key held by the app. */
export async function desktopLogout(): Promise<void> {
  if (window.__EIRA_TEST_DESKTOP_LOGIN__) return;
  if (window.__TAURI_INTERNALS__) await invoke("desktop_logout");
}

const MESSAGES: Array<[RegExp, string]> = [
  [/login_denied/, "Login blev afbrudt i browseren."],
  [/login_timed_out/, "Login tog for lang tid. Prøv igen."],
  [/could not open the browser/, "Browseren kunne ikke åbnes."],
  [/caller_not_in_a_login_session|loginuid_does_not_match_peer/, "Appen kører ikke i din login-session."],
  [/live_login_unavailable/, "Login med Entra er ikke sat op på denne maskine."],
  [/invalid_or_expired_state/, "Login udløb. Prøv igen."],
];

export function loginErrorMessage(error: unknown): string {
  const text = error instanceof Error ? error.message : String(error);
  for (const [pattern, message] of MESSAGES) {
    if (pattern.test(text)) return message;
  }
  return "Login fejlede.";
}
