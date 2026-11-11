import { afterEach, describe, expect, it } from "vitest";

import { follow, LONG_POLL_MS } from "../events";

type Call = { daemon: string; method: string; params: Record<string, unknown> };

function stub(pages: Array<unknown | Error>) {
  const calls: Call[] = [];
  const g = globalThis as unknown as { window: Record<string, unknown> };
  g.window = g.window ?? {};
  g.window.__EIRA_TEST_IPC__ = async (daemon: string, method: string, params: Record<string, unknown>) => {
    calls.push({ daemon, method, params });
    const next = pages.shift();
    if (next === undefined) return new Promise(() => {}); // the stream is quiet
    if (next instanceof Error) throw next;
    return next;
  };
  return calls;
}

const event = (seq: number) => ({ seq, event_id: `e${seq}`, conversation_id: "obj:sag:1", type: "utterance" });

afterEach(() => {
  delete (globalThis as unknown as { window: Record<string, unknown> }).window.__EIRA_TEST_IPC__;
});

describe("follow", () => {
  it("reads in order, moves the cursor forward and resumes after an error", async () => {
    const calls = stub([
      { events: [event(1)], cursor: 1, more: true },
      { events: [], cursor: 5, more: false }, // invisible events: cursor moves, nothing shown
      new Error("timeout"),
      { events: [event(6)], cursor: 6, more: false },
    ]);
    const seen: number[] = [];
    const stop = new AbortController();
    const done = follow("s-1", (page) => {
      seen.push(...page.events.map((e) => e.seq));
      if (seen.includes(6)) stop.abort();
    }, stop.signal, { retryMs: 1 });
    await done;
    expect(seen).toEqual([1, 6]);
    expect(calls.map((c) => c.params.cursor)).toEqual([0, 1, 5, 5]);
    expect(new Set(calls.map((c) => `${c.daemon} ${c.method}`))).toEqual(new Set(["intentd events.since"]));
    expect(calls[0].params.wait_ms).toBe(LONG_POLL_MS);
  });

  it("never accepts a cursor that moves backwards", async () => {
    stub([
      { events: [event(3)], cursor: 3, more: false },
      { events: [event(1)], cursor: 1, more: false },
    ]);
    const seen: number[] = [];
    const stop = new AbortController();
    const done = follow("s-1", (page) => seen.push(...page.events.map((e) => e.seq)), stop.signal, { retryMs: 1 });
    await new Promise((resolve) => setTimeout(resolve, 30));
    stop.abort();
    expect(seen).toEqual([3]);
    void done;
  });
});
