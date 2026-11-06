import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type {
  TerminalBackend,
  TerminalExit,
  TerminalOutput,
  TerminalSession,
} from "../src/lib/terminal";

// xterm.js needs a real canvas/layout; the panel's job is wiring, so the
// terminal itself is replaced by a recorder.
const terminals: FakeTerminal[] = [];

class FakeTerminal {
  cols = 100;
  rows = 30;
  written: string[] = [];
  disposed = false;
  private dataHandler: ((data: string) => void) | null = null;
  private resizeHandler: ((size: { cols: number; rows: number }) => void) | null = null;
  constructor() {
    terminals.push(this);
  }
  loadAddon() {}
  open() {}
  focus() {}
  write(data: string) {
    this.written.push(data);
  }
  onData(handler: (data: string) => void) {
    this.dataHandler = handler;
    return { dispose: () => (this.dataHandler = null) };
  }
  onResize(handler: (size: { cols: number; rows: number }) => void) {
    this.resizeHandler = handler;
    return { dispose: () => (this.resizeHandler = null) };
  }
  dispose() {
    this.disposed = true;
  }
  type(data: string) {
    this.dataHandler?.(data);
  }
  resizeTo(cols: number, rows: number) {
    this.resizeHandler?.({ cols, rows });
  }
}

vi.mock("@xterm/xterm", () => ({ Terminal: FakeTerminal }));
vi.mock("@xterm/addon-fit", () => ({ FitAddon: class { fit() {} } }));
vi.mock("@xterm/xterm/css/xterm.css", () => ({}));

const { TerminalPanel } = await import("../src/components/TerminalPanel");
const { default: App } = await import("../src/App");

function fakeBackend(overrides: Partial<TerminalBackend> = {}) {
  let output: ((event: TerminalOutput) => void) | null = null;
  let exit: ((event: TerminalExit) => void) | null = null;
  let next = 7;
  const backend = {
    create: vi.fn(
      async (): Promise<TerminalSession> => ({
        session_id: next++,
        shell: "/bin/bash",
        cwd: "/home/soren",
        pid: 4242,
      }),
    ),
    write: vi.fn(async () => {}),
    resize: vi.fn(async () => {}),
    signal: vi.fn(async () => {}),
    close: vi.fn(async () => {}),
    onOutput: vi.fn(async (handler: (event: TerminalOutput) => void) => {
      output = handler;
      return () => (output = null);
    }),
    onExit: vi.fn(async (handler: (event: TerminalExit) => void) => {
      exit = handler;
      return () => (exit = null);
    }),
    ...overrides,
  };
  window.__EIRA_TEST_TERMINAL__ = backend as TerminalBackend;
  return {
    backend,
    emitOutput: (event: TerminalOutput) => act(() => output?.(event)),
    emitExit: (event: TerminalExit) => act(() => exit?.(event)),
  };
}

beforeEach(() => {
  terminals.length = 0;
});

afterEach(() => {
  delete window.__EIRA_TEST_TERMINAL__;
});

describe("TerminalPanel", () => {
  it("opens the user's shell at the terminal's size and shows where it runs", async () => {
    const { backend } = fakeBackend();
    render(<TerminalPanel onClose={() => {}} />);
    expect(await screen.findByText("/bin/bash · /home/soren")).toBeInTheDocument();
    expect(backend.create).toHaveBeenCalledWith(100, 30);
    expect(screen.getByRole("region", { name: "Terminal" })).toBeInTheDocument();
  });

  it("streams only its own session's output and sends keystrokes and resizes", async () => {
    const { backend, emitOutput } = fakeBackend();
    render(<TerminalPanel onClose={() => {}} />);
    await screen.findByText("/bin/bash · /home/soren");
    const term = terminals[0];

    emitOutput({ session_id: 7, data: "soren@eira:~$ " });
    emitOutput({ session_id: 99, data: "another window's secret" });
    expect(term.written).toEqual(["soren@eira:~$ "]);

    term.type("ls -la\r");
    term.resizeTo(132, 43);
    expect(backend.write).toHaveBeenCalledWith(7, "ls -la\r");
    expect(backend.resize).toHaveBeenCalledWith(7, 132, 43);

    fireEvent.click(screen.getByRole("button", { name: "Afbryd" }));
    expect(backend.signal).toHaveBeenCalledWith(7, "SIGINT");
  });

  it("shows the exit code and can start a new shell", async () => {
    const { backend, emitExit } = fakeBackend();
    render(<TerminalPanel onClose={() => {}} />);
    await screen.findByText("/bin/bash · /home/soren");

    emitExit({ session_id: 7, code: 130 });
    expect(screen.getByText("Shellen er afsluttet (kode 130)")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Afbryd" })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Ny shell" }));
    await waitFor(() => expect(backend.create).toHaveBeenCalledTimes(2));
    expect(terminals[0].disposed).toBe(true);
  });

  it("closes the session and disposes the terminal when it unmounts", async () => {
    const { backend } = fakeBackend();
    const { unmount } = render(<TerminalPanel onClose={() => {}} />);
    await screen.findByText("/bin/bash · /home/soren");
    unmount();
    expect(backend.close).toHaveBeenCalledWith(7);
    expect(terminals[0].disposed).toBe(true);
  });

  it("explains why a shell could not start", async () => {
    fakeBackend({
      create: vi.fn(async () => {
        throw "permission_denied: the terminal never runs as root";
      }),
    });
    render(<TerminalPanel onClose={() => {}} />);
    expect(await screen.findByText("Terminalen kører aldrig som root.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Ny shell" })).toBeInTheDocument();
  });
});

describe("App terminal entry points", () => {
  const ipcWithMode = (mode: string) => async (_daemon: string, method: string) =>
    method === "presentation.mode_get" ? { mode } : { states: [], proposals: [] };

  it("in Builder Mode, toggles the terminal with the header button and Ctrl+Alt+T", async () => {
    fakeBackend();
    window.__EIRA_TEST_IPC__ = ipcWithMode("builder");
    render(<App />);

    const button = await screen.findByRole("button", { name: "Terminal" });
    expect(screen.queryByRole("region", { name: "Terminal" })).not.toBeInTheDocument();
    fireEvent.keyDown(window, { key: "t", ctrlKey: true, altKey: true });
    expect(await screen.findByRole("region", { name: "Terminal" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Luk terminal" }));
    expect(screen.queryByRole("region", { name: "Terminal" })).not.toBeInTheDocument();

    fireEvent.click(button);
    expect(await screen.findByRole("region", { name: "Terminal" })).toBeInTheDocument();
  });

  it.each(["explorer", "normal"])("in %s mode, offers no terminal at all", async (mode) => {
    fakeBackend();
    window.__EIRA_TEST_IPC__ = ipcWithMode(mode);
    render(<App />);
    await screen.findByText("Lokal Unix IPC");
    await new Promise((resolve) => setTimeout(resolve, 0));

    expect(screen.queryByRole("button", { name: "Terminal" })).not.toBeInTheDocument();
    fireEvent.keyDown(window, { key: "t", ctrlKey: true, altKey: true });
    expect(screen.queryByRole("region", { name: "Terminal" })).not.toBeInTheDocument();
  });

  it("falls back to Explorer when the mode cannot be confirmed", async () => {
    fakeBackend();
    window.__EIRA_TEST_IPC__ = async (_daemon: string, method: string) => {
      if (method === "presentation.mode_get") throw "daemon_unavailable";
      return { states: [], proposals: [] };
    };
    render(<App />);
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(screen.queryByRole("button", { name: "Terminal" })).not.toBeInTheDocument();
  });

  it("shows no power controls in Explorer", async () => {
    fakeBackend();
    window.__EIRA_TEST_IPC__ = ipcWithMode("explorer");
    render(<App />);
    await screen.findByText("Lokal Unix IPC");
    expect(screen.queryByRole("button", { name: /strøm|sluk|genstart/i })).not.toBeInTheDocument();
  });
});
