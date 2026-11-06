import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { PowerMenu } from "../src/components/PowerMenu";
import type { EiraResponse, PowerStatus } from "../src/lib/system";

const laptop: PowerStatus = {
  on_battery: true,
  battery: { percentage: 73.4, state: "discharging", time_to_empty_s: 5400 },
  actions: { poweroff: "available", reboot: "needs_authentication", suspend: "unavailable" },
  sources: { upower: true, logind: true },
};

type Req = { api_version: "1"; request_id: string; operation: string; input: unknown };

function system(handler: (req: Req) => Partial<EiraResponse<unknown>>) {
  const calls: Req[] = [];
  window.__EIRA_TEST_SYSTEM__ = vi.fn(async (req: Req) => {
    calls.push(req);
    return { api_version: "1", request_id: req.request_id, operation_id: "op-1", ...handler(req) };
  }) as typeof window.__EIRA_TEST_SYSTEM__;
  return calls;
}

afterEach(() => {
  delete window.__EIRA_TEST_SYSTEM__;
});

describe("PowerMenu", () => {
  it("shows the battery as reported by UPower", async () => {
    system(() => ({ result: laptop }));
    render(<PowerMenu />);
    expect(await screen.findByText("73 % · 1 t 30 min tilbage")).toBeInTheDocument();
  });

  it("shows no battery on a desktop machine", async () => {
    const calls = system(() => ({ result: { ...laptop, on_battery: false, battery: null } }));
    render(<PowerMenu />);
    await waitFor(() => expect(calls.length).toBe(1));
    expect(screen.queryByLabelText(/Batteri/)).not.toBeInTheDocument();
  });

  it("asks before powering off and only then sends a confirmed request", async () => {
    const calls = system((req) =>
      req.operation === "power.get_status"
        ? { result: laptop }
        : { result: { action: "poweroff", accepted: true } },
    );
    render(<PowerMenu />);
    fireEvent.click(await screen.findByRole("button", { name: "Strøm" }));
    expect(screen.getByRole("menuitem", { name: "Slumre" })).toBeDisabled();

    fireEvent.click(await screen.findByRole("menuitem", { name: "Sluk" }));
    expect(screen.getByText("Vil du slukke computeren? Åbne programmer lukkes.")).toBeInTheDocument();
    expect(calls.some((c) => c.operation === "power.request_action")).toBe(false);

    fireEvent.click(screen.getByRole("button", { name: "Sluk" }));
    expect(await screen.findByText("Lukker ned…")).toBeInTheDocument();
    const action = calls.find((c) => c.operation === "power.request_action");
    expect(action?.input).toEqual({ action: "poweroff", confirmed: true });
    expect(action?.api_version).toBe("1");
  });

  it("cancel sends nothing", async () => {
    const calls = system(() => ({ result: laptop }));
    render(<PowerMenu />);
    fireEvent.click(await screen.findByRole("button", { name: "Strøm" }));
    fireEvent.click(await screen.findByRole("menuitem", { name: "Genstart" }));
    fireEvent.click(screen.getByRole("button", { name: "Annuller" }));
    expect(calls.some((c) => c.operation === "power.request_action")).toBe(false);
    expect(screen.getByRole("menuitem", { name: "Genstart" })).toBeInTheDocument();
  });

  it("shows Ubuntu's refusal instead of pretending", async () => {
    system((req) =>
      req.operation === "power.get_status"
        ? { result: laptop }
        : {
            error: {
              code: "PERMISSION_DENIED",
              message: "Du har ikke tilladelse til at genstarte computeren",
              retryable: false,
              operation_id: "op-2",
            },
          },
    );
    render(<PowerMenu />);
    fireEvent.click(await screen.findByRole("button", { name: "Strøm" }));
    fireEvent.click(await screen.findByRole("menuitem", { name: "Genstart" }));
    fireEvent.click(screen.getByRole("button", { name: "Genstart" }));
    expect(
      await screen.findByText("Du har ikke tilladelse til at genstarte computeren"),
    ).toBeInTheDocument();
  });

  it("disables every action when the system bus is unavailable", async () => {
    system(() => ({
      error: {
        code: "CAPABILITY_UNAVAILABLE",
        message: "Systemets D-Bus er ikke tilgængelig",
        retryable: true,
        operation_id: "op-3",
      },
    }));
    render(<PowerMenu />);
    fireEvent.click(await screen.findByRole("button", { name: "Strøm" }));
    expect(await screen.findByText("Systemets D-Bus er ikke tilgængelig")).toBeInTheDocument();
    for (const name of ["Slumre", "Genstart", "Sluk"]) {
      expect(screen.getByRole("menuitem", { name })).toBeDisabled();
    }
  });
});
