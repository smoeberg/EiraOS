import { fireEvent, render, screen, waitFor } from "@testing-library/react";
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
  it("eksekverer en intention via intentd og opfrisker canvasset", async () => {
    const ipc = installIpcMock((daemon, method) => {
      if (daemon === "intentd" && method === "intent.execute") {
        return { state: { id: "state-2" }, knowledge: { proof_type: "CEL_CONSTRAINT" } };
      }
      throw new Error(`Unexpected IPC call: ${daemon}.${method}`);
    });
    window.__EIRA_TEST_IPC__ = ipc;
    render(createElement(App));

    const input = await screen.findByPlaceholderText("Beskriv din intention…");
    fireEvent.change(input, { target: { value: "Godkend byggetilladelsen" } });
    fireEvent.click(screen.getByText("Eksekvér"));

    await waitFor(() =>
      expect(ipc).toHaveBeenCalledWith("intentd", "intent.execute", {
        intent: "Godkend byggetilladelsen",
      }),
    );
    expect(await screen.findByText("Intentionen er eksekveret.")).toBeVisible();
    await waitFor(() =>
      expect(ipc).toHaveBeenCalledWith("stated", "state.list", { limit: 2000 }),
    );
    expect(input).toHaveValue("");
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
