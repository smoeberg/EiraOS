"""The model process (GATE-KERNEL bilag A, AI-INTERFACE-1.0).

Runs as its own system user, ``eira-model``. It reads the user's text and the
conversation context the app hands it, and proposes an EDP action to the gate
as itself. It cannot consent, confirm or execute, reads no database, and has
no network: whatever it proposes waits for the human's consent on the
trusted path.
"""
