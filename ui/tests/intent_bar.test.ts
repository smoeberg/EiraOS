import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { createElement } from "react";
import { describe, expect, it, vi } from "vitest";
import App from "../src/App";

/**
 * F1b: the IntentBar goes through the model process and the Gate, and the
 * person decides in the consent agent's window (here: __EIRA_TEST_GATE__,
 * standing in for the Rust core that asks the agent). The webview never
 * shows the Gate's rendering as something to approve.
 */

const documentState = {
  id: "state-1",
  version: 1,
  timestamp_ns: 1,
  type: "DocumentState",
  payload: { title: "Byggetilladelse · Bygaden 12" },
  previous_state_id: null,
  hash: "a".repeat(64),
};

const RENDERING = "Sluk computeren nu. Ikke-gemt arbejde går tabt.";
const PENDING = {
  decision: "REJECT",
  error: "E_NEED_CONSENT",
  state: "pending",
  action_id: "sys-1",
  content_hash: "sha256:c",
  data: { rendering: { text: RENDERING, hash: "sha256:r" } },
};

type Handler = (daemon: string, method: string, params: Record<string, unknown>) => unknown;

function installIpc(handler: Handler, loggedIn = true) {
  const calls: string[] = [];
  window.__EIRA_TEST_IPC__ = vi.fn(async (daemon: string, method: string, params: Record<string, unknown>) => {
    calls.push(`${daemon}.${method}`);
    if (daemon === "stated" && method === "state.list") return { states: [documentState], count: 1 };
    if (daemon === "graphd" && method === "graph.spatial_snapshot") return { nodes: [], edges: [] };
    if (daemon === "identityd" && method === "identity.session") {
      return loggedIn ? { session_id: "s-anne", authenticated: true } : { session_id: null, authenticated: false };
    }
    return handler(daemon, method, params);
  }) as never;
  return calls;
}

async function say(text: string) {
  render(createElement(App));
  const input = await screen.findByPlaceholderText("Beskriv din intention…");
  fireEvent.change(input, { target: { value: text } });
  fireEvent.click(screen.getByRole("button", { name: "Spørg Eira" }));
  return input;
}

describe("IntentBar", () => {
  it("kræver login og spørger ikke modellen uden en session", async () => {
    const calls = installIpc(() => {
      throw new Error("unexpected");
    }, false);
    await say("sluk computeren");
    expect(await screen.findByText("Log ind for at bruge Eira.")).toBeVisible();
    expect(calls).not.toContain("modeld.model.prepare");
  });

  it("siger ærligt, at Eira ikke forstod, og peger på den manuelle vej", async () => {
    installIpc((daemon, method) => {
      if (daemon === "modeld" && method === "model.prepare") return { abstain: "ambiguous_input" };
      throw new Error(`Unexpected IPC call: ${daemon}.${method}`);
    });
    const input = await say("hvad er klokken");
    expect(await screen.findByText(/Eira forstod det ikke/)).toBeVisible();
    expect(screen.getByText(/“sluk computeren”/)).toBeVisible(); // what it does understand
    expect(input).toHaveValue("hvad er klokken"); // the words are kept
  });

  it("sender teksten til modellen uden samtale og med sessionen", async () => {
    let sent: Record<string, unknown> = {};
    installIpc((daemon, method, params) => {
      if (daemon === "modeld" && method === "model.prepare") {
        sent = params;
        return { abstain: "ambiguous_input" };
      }
      throw new Error("unexpected");
    });
    await say("sluk computeren");
    await screen.findByText(/Eira forstod det ikke/);
    expect(sent).toMatchObject({ session_id: "s-anne", text: "sluk computeren", lang: "da" });
    expect(sent).not.toHaveProperty("conversation_id");
  });

  it("hele vejen: forslag, beslutning i samtykkevinduet, og gatens egen status", async () => {
    const calls = installIpc((daemon, method) => {
      if (daemon === "modeld" && method === "model.prepare") {
        return { gate: PENDING, action_type: "system:power.request_action" };
      }
      if (daemon === "intentd" && method === "gate.status") {
        return { state: "executed", result: { visible_state: "requested" } };
      }
      throw new Error(`Unexpected IPC call: ${daemon}.${method}`);
    });
    const agent = vi.fn(async () => ({ status: "decided", steps: [] }));
    window.__EIRA_TEST_GATE__ = agent as never;

    await say("sluk computeren");

    expect(await screen.findByText("Anmodningen er sendt. Computeren gør det nu.")).toBeVisible();
    // Only the id and hashes go to the Rust core; the agent shows the text.
    expect(agent).toHaveBeenCalledWith("consent", {
      actionId: "sys-1",
      contentHash: "sha256:c",
      renderingHash: "sha256:r",
    });
    expect(calls).toContain("intentd.gate.status");
    // The Gate's rendering is never shown in the webview as a consent surface.
    expect(screen.queryByText(RENDERING)).not.toBeInTheDocument();
  });

  it("viser, når personen afviser i samtykkevinduet, og at intet er sket", async () => {
    const calls = installIpc((daemon, method) => {
      if (daemon === "modeld" && method === "model.prepare") return { gate: PENDING };
      throw new Error(`Unexpected IPC call: ${daemon}.${method}`);
    });
    window.__EIRA_TEST_GATE__ = vi.fn(async () => ({ status: "declined" })) as never;
    await say("sluk computeren");
    expect(await screen.findByText("Du afviste. Intet er sket.")).toBeVisible();
    expect(calls).not.toContain("intentd.gate.status");
  });

  it("siger det, når samtykkevinduet ikke kører", async () => {
    installIpc((daemon, method) => {
      if (daemon === "modeld" && method === "model.prepare") return { gate: PENDING };
      throw new Error("unexpected");
    });
    window.__EIRA_TEST_GATE__ = vi.fn(async () => {
      throw new Error("E_CONSENT_AGENT_UNAVAILABLE: samtykkevinduet kører ikke");
    }) as never;
    await say("sluk computeren");
    expect(await screen.findByText("Samtykkevinduet kører ikke, så intet kan godkendes lige nu.")).toBeVisible();
  });

  it("uden tilladelse beder Eira om den, og sætningen går igen bagefter", async () => {
    let asked = 0;
    let delegationParams: Record<string, unknown> = {};
    installIpc((daemon, method, params) => {
      if (daemon === "modeld" && method === "model.prepare") {
        asked += 1;
        if (asked === 1) {
          return {
            gate: { decision: "REJECT", error: "E_UNAUTHORIZED" },
            action_type: "system:power.request_action",
            needs_delegation: { delegee_id: "model:eira-model", target: "intent:system:power.request_action" },
          };
        }
        return { gate: PENDING, action_type: "system:power.request_action" };
      }
      if (daemon === "delegationd" && method === "delegation.propose") {
        delegationParams = params;
        return { proposal_id: "dlgp-1", content_hash: "h", rendering: { text: "Eira må …", hash: "rh", lang: "da" } };
      }
      if (daemon === "intentd" && method === "gate.status") {
        return { state: "executed", result: { visible_state: "requested" } };
      }
      throw new Error(`Unexpected IPC call: ${daemon}.${method}`);
    });
    const delegationAgent = vi.fn(async () => ({ status: "decided" }));
    window.__EIRA_TEST_DELEGATION__ = delegationAgent as never;
    window.__EIRA_TEST_GATE__ = vi.fn(async () => ({ status: "decided", steps: [] })) as never;

    await say("sluk computeren");
    expect(await screen.findByText("Eira må ikke forberede det på dine vegne endnu.")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Giv Eira lov til at forberede det" }));

    expect(await screen.findByText("Anmodningen er sendt. Computeren gør det nu.")).toBeVisible();
    expect(delegationParams).toMatchObject({
      session_id: "s-anne",
      delegee_id: "model:eira-model",
      scope: { actions: ["prepare"], targets: ["intent:system:power.request_action"] },
    });
    expect(delegationAgent).toHaveBeenCalledOnce();
    expect(asked).toBe(2);
  });

  it("oversætter gatens afvisning til en sand besked", async () => {
    installIpc((daemon, method) => {
      if (daemon === "modeld" && method === "model.prepare") {
        return { gate: { decision: "REJECT", error: "E_UNAUTHORIZED" }, action_type: "system:power.request_action" };
      }
      throw new Error("unexpected");
    });
    await say("sluk computeren");
    expect(await screen.findByText(/Du har ikke ret til det på denne computer/)).toBeVisible();
  });
});

describe("Strøm-menuen (den manuelle vej, kun i Builder Mode)", () => {
  it("findes ikke i Explorer (ADR-0001)", async () => {
    installIpc(() => {
      throw new Error("no mode");
    });
    render(createElement(App));
    await screen.findByText("Lokal Unix IPC");
    expect(screen.queryByRole("button", { name: "Strøm" })).not.toBeInTheDocument();
  });

  it("foreslår direkte til gaten som brugeren og går gennem samtykkevinduet", async () => {
    let proposed: Record<string, unknown> = {};
    installIpc((daemon, method, params) => {
      if (daemon === "intentd" && method === "presentation.mode_get") {
        return { mode: "builder", builder_allowed: true };
      }
      if (daemon === "intentd" && method === "gate.propose") {
        proposed = params;
        return PENDING;
      }
      if (daemon === "intentd" && method === "gate.status") {
        return { state: "executed", result: { visible_state: "requested" } };
      }
      throw new Error(`Unexpected IPC call: ${daemon}.${method}`);
    });
    window.__EIRA_TEST_GATE__ = vi.fn(async () => ({ status: "decided", steps: [] })) as never;
    render(createElement(App));

    fireEvent.click(await screen.findByRole("button", { name: "Strøm" }));
    const menu = screen.getByRole("menu", { name: "Strøm" });
    fireEvent.click(within(menu).getByRole("menuitem", { name: "Genstart" }));

    await waitFor(() =>
      expect(within(menu).getByText("Anmodningen er sendt. Computeren gør det nu.")).toBeVisible(),
    );
    expect(proposed).toMatchObject({
      session_id: "s-anne",
      origin: "user",
      edp: { eira_system: "1", operation: "power.request_action", input: { action: "reboot" } },
    });
  });
});
