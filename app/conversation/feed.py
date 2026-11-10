"""Medlemskab og hændelsesstrøm (EIRA-CONVERSATION-1.0 §3–§5).

Alt her arbejder på en rå ``sqlite3``-forbindelse, så samme kode bruges i
gatens lag 4 (læsning) og i executorens transaktion (skrivning). Reglen for,
hvem der må handle i en samtale, findes derfor ét sted.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from typing import Any

FEED_SCHEMA = """
CREATE TABLE IF NOT EXISTS conversation_feed (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE,
    conversation_id TEXT NOT NULL,
    action_type TEXT NOT NULL,
    author TEXT NOT NULL,
    ref_id TEXT,
    recorded_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS conversation_feed_by_conversation
    ON conversation_feed (conversation_id, seq);
CREATE TRIGGER IF NOT EXISTS conversation_feed_no_update
    BEFORE UPDATE ON conversation_feed
    BEGIN SELECT RAISE(ABORT, 'conversation_feed is append-only'); END;
CREATE TRIGGER IF NOT EXISTS conversation_feed_no_delete
    BEFORE DELETE ON conversation_feed
    BEGIN SELECT RAISE(ABORT, 'conversation_feed is append-only'); END;
"""

# Only verified local identities can be members; an external address
# (external:sms:…) is a recipient, not someone who logs in here.
LOCAL_IDENTITY_PREFIX = "did:eira:"
MEMBER_ROLES = ("member", "observer")  # "service" is never a member
REFERENCE_FIELD = "commitment_id"
MAX_PAGE = 200
MAX_WAIT_S = 20.0


class OutsideDomain(Exception):
    """The identity may not act in this conversation (lag 4)."""


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(FEED_SCHEMA)


def _role(conn: sqlite3.Connection, conversation_id: str, identity: str) -> str | None:
    row = conn.execute(
        "SELECT role FROM gate_members WHERE conversation_id = ? AND identity = ?",
        (conversation_id, identity),
    ).fetchone()
    return row[0] if row else None


def _claimed(conn: sqlite3.Connection, conversation_id: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM gate_members WHERE conversation_id = ? LIMIT 1", (conversation_id,)
    ).fetchone()
    return row is not None


def _acting_member(envelope: dict[str, Any], identity: str) -> bool:
    return any(p["identity"] == identity and p["role"] == "member" for p in envelope["participants"])


def check_domain(conn: sqlite3.Connection, envelope: dict[str, Any], identity: str) -> None:
    """§3.2: who may act in a conversation.

    - A member may act.
    - An observer may see, never act.
    - A conversation nobody is a member of yet may be opened by an acting
      member participant. Whether that user may act on this scope at all is
      lag 6's decision (the Fleet set), not this one's.
    """
    conversation = envelope["conversation_id"]
    role = _role(conn, conversation, identity)
    if role == "member":
        return
    if role is not None:
        raise OutsideDomain(f"{role} may not act in this conversation")
    if _claimed(conn, conversation):
        raise OutsideDomain("not a member of this conversation")
    if not _acting_member(envelope, identity):
        raise OutsideDomain("opening a conversation requires being an acting participant")


def record(conn: sqlite3.Connection, envelope: dict[str, Any], author: str) -> int:
    """Append the event and derive membership from it, inside the caller's
    transaction (§3.3). The domain is checked again here, so two users cannot
    both open the same new conversation. Returns the feed position."""
    check_domain(conn, envelope, author)
    content = envelope["action"]["content"]
    cursor = conn.execute(
        """INSERT INTO conversation_feed (event_id, conversation_id, action_type, author, ref_id,
           recorded_at) VALUES (?, ?, ?, ?, ?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))""",
        (
            envelope["id"],
            envelope["conversation_id"],
            envelope["action"]["type"],
            author,
            content.get(REFERENCE_FIELD) if isinstance(content.get(REFERENCE_FIELD), str) else None,
        ),
    )
    seq = int(cursor.lastrowid)
    joining = {author: "member"}
    for participant in envelope["participants"]:
        identity, role = participant["identity"], participant["role"]
        if identity.startswith(LOCAL_IDENTITY_PREFIX) and role in MEMBER_ROLES:
            if joining.get(identity) != "member":
                joining[identity] = role
    for identity, role in joining.items():
        existing = _role(conn, envelope["conversation_id"], identity)
        if existing is None:
            conn.execute(
                "INSERT INTO gate_members (conversation_id, identity, role, joined_seq) VALUES (?, ?, ?, ?)",
                (envelope["conversation_id"], identity, role, seq),
            )
        elif existing == "observer" and role == "member":
            # Membership only grows (§3.4): addressing an observer as member
            # promotes; nothing in an event can demote or remove.
            conn.execute(
                "UPDATE gate_members SET role = 'member' WHERE conversation_id = ? AND identity = ?",
                (envelope["conversation_id"], identity),
            )
    return seq


# --- the stream ------------------------------------------------------------------


class Notifier:
    """Wakes long-polls when intentd records an event (same process)."""

    def __init__(self) -> None:
        self._cond = threading.Condition()
        self._latest = 0

    def notify(self, seq: int) -> None:
        with self._cond:
            self._latest = max(self._latest, seq)
            self._cond.notify_all()

    def wait_beyond(self, cursor: int, timeout: float) -> None:
        with self._cond:
            self._cond.wait_for(lambda: self._latest > cursor, timeout=max(0.0, min(timeout, MAX_WAIT_S)))


NOTIFIER = Notifier()

_EVENT_SELECT = """
SELECT f.seq, f.event_id, f.conversation_id, f.action_type, f.author, f.ref_id, f.recorded_at,
       o.envelope, o.delivery_state, m.role
  FROM conversation_feed f
  JOIN gate_members m ON m.conversation_id = f.conversation_id AND m.identity = ?
  LEFT JOIN conversation_outbox o ON o.event_id = f.event_id
"""


def _event(row: sqlite3.Row | tuple) -> dict[str, Any]:
    seq, event_id, conversation, action_type, author, ref_id, recorded_at, envelope, delivery, _ = row
    body = json.loads(envelope) if envelope else {}
    return {
        "seq": seq,
        "event_id": event_id,
        "conversation_id": conversation,
        "type": action_type,
        "author": author,
        "participants": body.get("participants", []),
        "content": (body.get("action") or {}).get("content", {}),
        "temporal": body.get("temporal", {}),
        "ref_id": ref_id,
        "recorded_at": recorded_at,
        # Honest state: recorded is not delivered (Phase 1-beslutningen).
        "delivery": delivery or "pending",
    }


def _limit(value: Any) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        return 50
    return min(value, MAX_PAGE)


def since(conn: sqlite3.Connection, identity: str, cursor: int, limit: int = 50) -> dict[str, Any]:
    """Events after ``cursor`` in conversations the identity can see. History
    before the identity joined is visible too (§4.2): the conversation belongs
    to the object, not to the moment someone was added."""
    rows = conn.execute(
        _EVENT_SELECT + " WHERE f.seq > ? ORDER BY f.seq LIMIT ?",
        (identity, cursor, _limit(limit) + 1),
    ).fetchall()
    page = rows[: _limit(limit)]
    events = [_event(row) for row in page]
    # The cursor moves past everything examined, also rows of conversations
    # the identity cannot see: a client never learns where those are.
    latest = conn.execute("SELECT COALESCE(MAX(seq), 0) FROM conversation_feed").fetchone()[0]
    next_cursor = events[-1]["seq"] if len(rows) > len(page) else max(cursor, int(latest))
    return {"events": events, "cursor": next_cursor, "more": len(rows) > len(page)}


def history(
    conn: sqlite3.Connection, identity: str, conversation_id: str, before: int | None, limit: int = 50
) -> list[dict[str, Any]] | None:
    """Newest first. ``None`` if the identity cannot see the conversation —
    the same answer as for one that does not exist."""
    if _role(conn, conversation_id, identity) is None:
        return None
    bound = before if isinstance(before, int) and not isinstance(before, bool) else 2**62
    rows = conn.execute(
        _EVENT_SELECT + " WHERE f.conversation_id = ? AND f.seq < ? ORDER BY f.seq DESC LIMIT ?",
        (identity, conversation_id, bound, _limit(limit)),
    ).fetchall()
    return [_event(row) for row in rows]


def conversations(conn: sqlite3.Connection, identity: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """SELECT m.conversation_id, m.role,
                  (SELECT MAX(seq) FROM conversation_feed f WHERE f.conversation_id = m.conversation_id),
                  (SELECT MAX(recorded_at) FROM conversation_feed f WHERE f.conversation_id = m.conversation_id),
                  (SELECT COUNT(*) FROM gate_members x WHERE x.conversation_id = m.conversation_id)
             FROM gate_members m WHERE m.identity = ?
            ORDER BY 3 DESC""",
        (identity,),
    ).fetchall()
    return [
        {
            "conversation_id": conversation,
            "role": role,
            "last_seq": last_seq,
            "last_event_at": last_at,
            "members": count,
        }
        for conversation, role, last_seq, last_at, count in rows
        if last_seq is not None  # fixture-only memberships have no events
    ]


def members(conn: sqlite3.Connection, identity: str, conversation_id: str) -> list[dict[str, Any]] | None:
    if _role(conn, conversation_id, identity) is None:
        return None
    rows = conn.execute(
        "SELECT identity, role FROM gate_members WHERE conversation_id = ? ORDER BY joined_seq, identity",
        (conversation_id,),
    ).fetchall()
    return [{"identity": member, "role": role} for member, role in rows]


def awaiting(conn: sqlite3.Connection, identity: str) -> dict[str, Any]:
    """What waits for this user's decision (§4.3):

    - ``commitments``: proposed to the user as an acting member by someone
      else, and not yet accepted or declined by the user.
    - ``decisions``: gate actions pending for this user (for instance a model
      proposal), with the exact text the user would consent to.
    """
    rows = conn.execute(
        _EVENT_SELECT
        + """ WHERE f.action_type = 'commitment_proposed' AND f.author != ? AND m.role = 'member'
               AND NOT EXISTS (SELECT 1 FROM conversation_feed r
                                WHERE r.ref_id = f.event_id AND r.author = ?
                                  AND r.action_type IN ('commitment_accepted', 'commitment_declined'))
             ORDER BY f.seq""",
        (identity, identity, identity),
    ).fetchall()
    commitments = [
        event
        for event in (_event(row) for row in rows)
        if any(p.get("identity") == identity and p.get("role") == "member" for p in event["participants"])
    ]
    decisions = [
        {
            "action_id": action_id,
            "conversation_id": conversation,
            "action_type": action_type,
            "origin": origin,
            "content_hash": content_hash,
            "rendering": {"text": text, "hash": rhash, "lang": lang} if text else None,
            "created_at": created_at,
        }
        for action_id, conversation, action_type, origin, content_hash, text, rhash, lang, created_at in conn.execute(
            """SELECT action_id, conversation_id, action_type, origin, content_hash,
                      rendering_text, rendering_hash, render_lang, created_at
                 FROM gate_actions WHERE state = 'pending' AND actor_identity = ?
                ORDER BY created_at""",
            (identity,),
        ).fetchall()
    ]
    return {"commitments": commitments, "decisions": decisions}
