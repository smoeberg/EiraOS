"""Gate Kernel 1.0 — EiraOS' autoritative sikkerhedsgrænse.

Normativ tekst: ``specs/GATE-KERNEL-1.0.md``. "AI'en foreslår. Gaten afgør.
Systemet udfører." Intet modeloutput, ingen adapter og ingen daemon må udføre
en beskyttet handling uden om :class:`app.gate.kernel.Gate`.
"""

from app.gate.errors import Decision, GateCode, GateResult
from app.gate.kernel import Gate

__all__ = ["Decision", "Gate", "GateCode", "GateResult"]
