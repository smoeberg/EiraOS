import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { SpatialCanvas } from "../SpatialCanvas";

function installTestIpc() {
  window.__EIRA_TEST_IPC__ = vi.fn(async (_daemon, method) => {
    if (method === "state.list") {
      return { states: [], count: 0 };
    }
    return { nodes: [], edges: [] };
  });
}

describe("SpatialCanvas accessibility", () => {
  it("supports keyboard pan, zoom, and reset", async () => {
    installTestIpc();
    render(<SpatialCanvas pollIntervalMs={60_000} />);

    const canvas = screen.getByTestId("spatial-canvas");
    await waitFor(() => expect(canvas).toHaveAttribute("data-zoom", "1.00"));

    fireEvent.keyDown(canvas, { key: "ArrowRight" });
    fireEvent.keyDown(canvas, { key: "ArrowUp" });
    expect(screen.getByTestId("spatial-canvas").querySelector(".canvas-scene")).toHaveStyle(
      "transform: translate(40px, -40px) scale(1)",
    );

    fireEvent.keyDown(canvas, { key: "+" });
    expect(canvas).toHaveAttribute("data-zoom", "1.15");
    expect(screen.getByLabelText("Zoomniveau")).toHaveTextContent("115%");

    fireEvent.keyDown(canvas, { key: "PageDown" });
    expect(canvas).toHaveAttribute("data-zoom", "1.00");

    fireEvent.keyDown(canvas, { key: "0" });
    expect(canvas).toHaveAttribute("data-zoom", "1.00");
    expect(screen.getByTestId("spatial-canvas").querySelector(".canvas-scene")).toHaveStyle(
      "transform: translate(0px, 0px) scale(1)",
    );
  });

  it("exposes keyboard instructions and zoom through ARIA", () => {
    installTestIpc();
    render(<SpatialCanvas pollIntervalMs={60_000} />);

    const canvas = screen.getByRole("application", {
      name: "Spatial Canvas, interaktiv tilstandsgraf",
    });

    expect(canvas).toHaveAttribute("tabindex", "0");
    expect(canvas).toHaveAttribute("aria-describedby", "spatial-canvas-instructions");
    expect(
      document.getElementById("spatial-canvas-instructions"),
    ).toHaveTextContent("Brug piletaster til at panorere");

    const zoom = screen.getByLabelText("Zoomniveau");
    expect(zoom).toHaveAttribute("aria-live", "polite");
    expect(zoom).toHaveTextContent("100%");
  });

  it("announces keyboard zoom changes through the live output", () => {
    installTestIpc();
    render(<SpatialCanvas pollIntervalMs={60_000} />);

    const canvas = screen.getByTestId("spatial-canvas");
    const zoom = screen.getByLabelText("Zoomniveau");

    fireEvent.keyDown(canvas, { key: "PageUp" });
    expect(zoom).toHaveTextContent("115%");

    fireEvent.keyDown(canvas, { key: "-" });
    expect(zoom).toHaveTextContent("100%");
  });
});
