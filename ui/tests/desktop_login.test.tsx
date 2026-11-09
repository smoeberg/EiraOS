import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { createElement } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AuthButton } from "../src/AuthButton";
import { clearSessionId, getSessionId } from "../src/api";
import { loginErrorMessage } from "../src/lib/login";

afterEach(() => {
  delete window.__EIRA_TEST_DESKTOP_LOGIN__;
  clearSessionId();
  vi.unstubAllGlobals();
});

describe("Desktop-login", () => {
  it("logger ind via appen og gemmer kun sessionen", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => { throw new Error("ingen HTTP-bro på desktop"); }));
    const login = vi.fn(async () => ({
      session_id: "sess-123",
      identity: "did:eira:entra.7a9c",
      expires_at: "2026-11-10T03:00:00Z",
    }));
    window.__EIRA_TEST_DESKTOP_LOGIN__ = login;
    const onAuthChange = vi.fn();
    render(createElement(AuthButton, { onAuthChange }));

    fireEvent.click(await screen.findByRole("button", { name: "Log ind med Entra" }));

    await waitFor(() => expect(onAuthChange).toHaveBeenCalled());
    expect(login).toHaveBeenCalledOnce();
    expect(getSessionId()).toBe("sess-123");
  });

  it("viser en dansk besked, når login afbrydes", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => { throw new Error("ingen HTTP-bro"); }));
    window.__EIRA_TEST_DESKTOP_LOGIN__ = vi.fn(async () => {
      throw new Error("login_denied: access_denied");
    });
    render(createElement(AuthButton, { onAuthChange: vi.fn() }));

    fireEvent.click(await screen.findByRole("button", { name: "Log ind med Entra" }));

    expect(await screen.findByText("Login blev afbrudt i browseren.")).toBeInTheDocument();
    expect(getSessionId()).toBeNull();
  });

  it("oversætter identityd's afvisninger", () => {
    expect(loginErrorMessage("caller_not_in_a_login_session")).toBe("Appen kører ikke i din login-session.");
    expect(loginErrorMessage(new Error("login_timed_out"))).toBe("Login tog for lang tid. Prøv igen.");
    expect(loginErrorMessage("noget helt andet")).toBe("Login fejlede.");
  });
});
