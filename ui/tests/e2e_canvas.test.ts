import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createElement } from "react";
import { describe, expect, it, vi } from "vitest";
import App from "../src/App";

const documentState = {
  id: "state-1",
  version: 1,
  timestamp_ns: 1,
  type: "DocumentState",
  payload: { title: "Byggetilladelse · Bygaden 12" },
  previous_state_id: null,
  hash: "a".repeat(64),
};

const proposalState = {
  id: "proposal-state-1",
  version: 1,
  timestamp_ns: 2,
  type: "ProposalState",
  payload: {
    proposal_id: "proposal-1",
    suggested_transformation: "approve_building_permit",
    candidate_state: {
      ...documentState,
      id: "state-2",
      version: 2,
      previous_state_id: "state-1",
      payload: { title: "Godkend byggetilladelse" },
      hash: "b".repeat(64),
    },
    confidence_score: 0.94,
    rationale: "Alle deterministiske regler er opfyldt.",
  },
  previous_state_id: "state-1",
  hash: "c".repeat(64),
};

function installIpcMock() {
  const mock = vi.fn(async (daemon: string, method: string) => {
    if (daemon === "stated" && method === "state.list") {
      return { states: [documentState, proposalState], count: 2 };
    }
    if (daemon === "graphd" && method === "graph.spatial_snapshot") {
      return {
        nodes: [
          { id: "state-1", label: "Byggetilladelse · Bygaden 12", type: "DocumentState", x: 120, y: 100 },
          { id: "proposal-state-1", label: "Forslag", type: "ProposalState", x: 430, y: 260 },
        ],
        edges: [
          { id: "edge-1", source: "state-1", target: "proposal-state-1", relation: "proposes" },
        ],
      };
    }
    if (daemon === "veritasd" && method === "veritas.evaluate") {
      return {
        trust_score: 92,
        layers: {
          layer1: { score: 0.96, flags: [] },
          layer2: { score: 0.91, flags: [] },
          layer3: { score: 0.9, flags: [] },
          c2pa: { score: 0.8, flags: [], manifest: { signer: "camera" } },
        },
        rationale: ["Lag 1: ingen identificerede risikoflag"],
        hud_certificate: { certificate_id: "veritas:test" },
      };
    }
    throw new Error(`Unexpected IPC call: ${daemon}.${method}`);
  });
  window.__EIRA_TEST_IPC__ = mock;
  return mock;
}

describe("Spatial Canvas and Tauri IPC integration", () => {
  it("loads graph/state data and supports canvas zoom", async () => {
    const ipc = installIpcMock();
    render(createElement(App));

    expect(await screen.findByText("Byggetilladelse · Bygaden 12")).toBeInTheDocument();
    expect(screen.getByText("proposes", { exact: false })).toBeInTheDocument();
    const canvas = screen.getByTestId("spatial-canvas");
    expect(canvas).toHaveAttribute("data-zoom", "1.00");
    fireEvent.wheel(canvas, { deltaY: -120 });
    expect(canvas).toHaveAttribute("data-zoom", "1.10");
    expect(ipc).toHaveBeenCalledWith("stated", "state.list", { limit: 2000 });
    expect(ipc).toHaveBeenCalledWith("graphd", "graph.spatial_snapshot", { limit: 2000 });
  });

  it("renders ProposalState action cards and an interactive Veritas HUD", async () => {
    installIpcMock();
    const user = userEvent.setup();
    render(createElement(App));

    expect(await screen.findByText("Approve building permit")).toBeInTheDocument();
    await user.click(screen.getByTestId("canvas-node-state-1"));

    const hud = await screen.findByTestId("veritas-hud");
    expect(hud).toHaveTextContent("92");
    expect(hud).toHaveTextContent("Lag 1 · Kilde");
    expect(hud).toHaveTextContent("C2PA · Medie");
    expect(hud).toHaveTextContent("Manifest fundet");

    await user.click(screen.getByText("Se forklaring"));
    expect(screen.getByText("Lag 1: ingen identificerede risikoflag")).toBeVisible();
    await waitFor(() => expect(screen.getByText("veritas:test")).toBeVisible());
  });
});
