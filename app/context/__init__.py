"""Contexts (EIRA-CONTEXT 1.0): the open storage format (§6).

Everything here is a pure function or works on a context home given to it;
nothing runs as a daemon yet (that is eira-contextd, UDVIKLINGSPLAN F2.4).
The format is part of the exit guarantee: tools/eira-context-export reads it
with nothing but the CMK and the ``cryptography`` package.
"""

from app.context.errors import ContextError

__all__ = ["ContextError"]
