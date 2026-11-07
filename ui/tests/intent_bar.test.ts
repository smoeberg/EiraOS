import { fireEvent, render, screen } from "@testing-library/react";
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

function installIpcMock(handler: (daemon: string, method: string) => unknown) {
  return vi.fn(async (daemon: string, method: string) => {
    if (daemon === "stated" && method === "state.list") {
      return { states: [documentState], count: 1 };
    }
    if (daemon === "graphd" && method === "graph.spatial_snapshot") {
      return { nodes: [], edges: [] };
    }
    return handler(daemon, method);
  }) as never;
}

describe("IntentBar", () => {
  it("udfører intet direkte: intentd henviser til Gaten, og brugeren får besked", async () => {
    const ipc = installIpcMock((daemon, method) => {
      if (daemon === "intentd" && method === "intent.execute") {
        throw new Error(
          JSON.stringify({
            code: -32010,
            message: "E_GATE_REQUIRED",
            data: {
              method: "intent.execute",
              use: "gate.propose",
              user_message: "Handlingen skal foreslås og bekræftes gennem Gaten, før den udføres.",
            },
          }),
        );
      }
      throw new Error(`Unexpected IPC call: ${daemon}.${method}`);
    });
    window.__EIRA_TEST_IPC__ = ipc;
    render(createElement(App));

    const input = await screen.findByPlaceholderText("Beskriv din intention…");
    fireEvent.change(input, { target: { value: "Godkend byggetilladelsen" } });
    fireEvent.click(screen.getByText("Eksekvér"));

    expect(
      await screen.findByText("Handlingen skal foreslås og bekræftes gennem Gaten, før den udføres."),
    ).toBeVisible();
    expect(screen.queryByText("Intentionen er eksekveret.")).not.toBeInTheDocument();
    // The user's words are kept so nothing is lost.
    expect(input).toHaveValue("Godkend byggetilladelsen");
  });

  it("viser constraint-violation-brugerbesked", async () => {
    const ipc = installIpcMock((daemon, method) => {
      if (daemon === "intentd" && method === "intent.execute") {
        throw new Error(
          JSON.stringify({
            code: -32001,
            message: "CONSTRAINT_VIOLATION",
            data: {
              user_message: "Kræver godkendelse med MitID Erhverv.",
              step_up_required: true,
            },
          }),
        );
      }
      throw new Error(`Unexpected IPC call: ${daemon}.${method}`);
    });
    window.__EIRA_TEST_IPC__ = ipc;
    render(createElement(App));

    const input = await screen.findByPlaceholderText("Beskriv din intention…");
    fireEvent.change(input, { target: { value: "Slet arkivet" } });
    fireEvent.click(screen.getByText("Eksekvér"));

    expect(
      await screen.findByText("Kræver godkendelse med MitID Erhverv."),
    ).toBeVisible();
  });
});
