"""eira-intentd: the gate process (GATE-KERNEL 1.0).

It holds the gate, the read-only conversation stream for Explorer, the
dashboard and presentation mode (app/daemons/intent_engine.py) and the audit
anchor. Nothing here writes state outside the gate: the old intent.execute,
intent.parse and intent.plan are gone (UDVIKLINGSPLAN F1.2, fundregister
S-7, S-8, S-9); intent.execute still answers E_GATE_REQUIRED, so an old
client learns where to go instead of getting "method not found".
"""

from __future__ import annotations

from app.ipc.access import read


def register_intent_handlers(server):
    """Registers the gate process' methods and returns the gate."""
    from app.daemons.intent_engine import register_intent_handlers as register_engine
    from app.gate.ipc import gate_required, register_gate_handlers

    register_engine(server)
    server.register("intent.execute", gate_required("intent.execute"))

    gate = register_gate_handlers(server)
    from app.conversation.ipc import register_conversation_handlers

    # Read-only: the event stream for Explorer (EIRA-CONVERSATION-1.0 §5).
    register_conversation_handlers(server, gate)
    _start_audit_anchor(server)
    server.register("health", read(lambda _: {"daemon": "eira-intentd", "ok": True}))
    return gate


def _start_audit_anchor(server) -> None:
    """GATE-KERNEL bilag A pkt. 2: anchor the audit chain in the journal (and,
    via the rights agent's heartbeat, at Fleet) on an installed system."""
    from app.gate.caller import installed

    if not installed():
        return
    from app.gate import audit_anchor
    from app.gate.ipc import default_gate

    anchorer = audit_anchor.Anchorer(default_gate().store)
    anchorer.start()
    server.add_cleanup(anchorer.stop)
