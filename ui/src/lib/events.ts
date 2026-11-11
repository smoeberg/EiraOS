import { sendIpcRequest } from "./ipc";

/**
 * Client for the event stream (specs/EIRA-CONVERSATION-1.0.md §5).
 *
 * Read-only. Everything here shows what the gate has recorded; nothing here
 * can change a conversation or its members. A recorded event is not a
 * delivered one: `delivery` stays "pending" until a receiver acknowledges it.
 */

export type Participant = { identity: string; role: "member" | "observer" | "service" };

export type ConversationEvent = {
  seq: number;
  event_id: string;
  conversation_id: string;
  type: string;
  author: string;
  participants: Participant[];
  content: Record<string, unknown>;
  temporal: { created_at?: string; valid_from?: string | null; supersedes?: string | null };
  ref_id: string | null;
  recorded_at: string;
  delivery: string;
};

export type EventPage = { events: ConversationEvent[]; cursor: number; more: boolean };

export type Awaiting = {
  commitments: ConversationEvent[];
  decisions: Array<{
    action_id: string;
    conversation_id: string;
    action_type: string;
    origin: "user" | "model";
    content_hash: string;
    rendering: { text: string; hash: string; lang: string } | null;
    created_at: string;
  }>;
};

/** Stays below the app's default IPC timeout (5 s, ui/src-tauri/src/ipc.rs). */
export const LONG_POLL_MS = 3_000;

export function eventsSince(sessionId: string, cursor: number, waitMs = 0): Promise<EventPage> {
  return sendIpcRequest<EventPage>("intentd", "events.since", {
    session_id: sessionId,
    cursor,
    wait_ms: waitMs,
  });
}

export function awaiting(sessionId: string): Promise<Awaiting> {
  return sendIpcRequest<Awaiting>("intentd", "conversation.awaiting", { session_id: sessionId });
}

export function conversationEvents(
  sessionId: string,
  conversationId: string,
  before?: number,
): Promise<{ conversation_id: string; events: ConversationEvent[] }> {
  return sendIpcRequest("intentd", "conversation.events", {
    session_id: sessionId,
    conversation_id: conversationId,
    ...(before === undefined ? {} : { before }),
  });
}

/**
 * Follow the stream until `signal` aborts. Pages arrive in order; the cursor
 * only moves forward. On an error the loop waits and resumes from the last
 * cursor, so nothing is skipped and nothing is shown twice.
 */
export async function follow(
  sessionId: string,
  onPage: (page: EventPage) => void,
  signal: AbortSignal,
  { cursor = 0, retryMs = 2_000 }: { cursor?: number; retryMs?: number } = {},
): Promise<number> {
  let position = cursor;
  while (!signal.aborted) {
    try {
      const page = await eventsSince(sessionId, position, LONG_POLL_MS);
      if (signal.aborted) break;
      if (page.cursor < position) throw new Error("cursor moved backwards");
      position = page.cursor;
      if (page.events.length) onPage(page);
      if (page.more) continue;
    } catch {
      await new Promise((resolve) => setTimeout(resolve, retryMs));
    }
  }
  return position;
}
