"""Error codes of EIRA-CONTEXT §12 used by the storage format."""

from __future__ import annotations

E_CONTEXT_INTEGRITY = "E_CONTEXT_INTEGRITY"
E_CONTEXT_HOME_UNSUPPORTED = "E_CONTEXT_HOME_UNSUPPORTED"


class ContextError(Exception):
    """A context operation failed with one of the contract's codes.

    The message never contains plaintext or key material."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail
