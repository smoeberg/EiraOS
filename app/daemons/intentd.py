"""The gate process (eira-intentd).

It holds Gate Kernel and the read side around it: the dashboard, the
presentation mode and the conversation layer's event stream. It contains no
language model client and no free-text parser (UDVIKLINGSPLAN F1.2, fundregister
S-7, S-8, S-9): proposals come from eira-modeld through ``gate.propose``.
"""

from __future__ import annotations

from app.ipc.access import read


def register_intent_handlers(server) -> None:
    from app.daemons.intent_engine import register_intent_handlers as register_reads

    register_reads(server)
    from app.gate.ipc import gate_required, register_gate_handlers

    # The old free-text executor is gone; protected actions go through the gate.
    server.register("intent.execute", gate_required("intent.execute"))

    gate = register_gate_handlers(server)
    from app.conversation.ipc import register_conversation_handlers

    # Read-only: the event stream for Explorer (EIRA-CONVERSATION-1.0 §5).
    register_conversation_handlers(server, gate)
    _start_audit_anchor(server)
    server.register("health", read(lambda _: {"daemon": "eira-intentd", "ok": True}))


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
