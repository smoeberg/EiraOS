import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// jsdom has no canvas. xterm.js (imported by App via TerminalPanel) probes it
// for glyph measurement; answer "no 2D context" instead of logging an error.
HTMLCanvasElement.prototype.getContext = (() => null) as typeof HTMLCanvasElement.prototype.getContext;

afterEach(() => {
  cleanup();
  delete window.__EIRA_TEST_IPC__;
  delete window.__EIRA_TEST_GATE__;
  delete window.__EIRA_TEST_DELEGATION__;
});
