"""
contextd — EiraOS Core Life Context Daemon
Manages active user contexts (Arbejde, Privat, Rejse, Familie, Indkøb, Projekt).
Filters all intents, notifications, wallet actions, and presence views through the active context.
"""

class ContextDaemon:
    def __init__(self):
        self.name = "contextd"
        self.active_context = "ARBEJDE"  # Default
        self.available_contexts = ["ARBEJDE", "PRIVAT", "REJSE", "FAMILIE", "INDKØB", "PROJEKT"]

    def set_context(self, context_name: str) -> dict:
        context_upper = context_name.upper()
        if context_upper in self.available_contexts:
            self.active_context = context_upper
            return {
                "status": "SUCCESS",
                "active_context": self.active_context,
                "summary": f"EiraOS livskontekst skiftet til: {self.active_context}"
            }
        return {"status": "ERROR", "message": f"Ukendt kontekst: {context_name}"}

    def get_context(self) -> dict:
        return {
            "active_context": self.active_context,
            "available_contexts": self.available_contexts,
            "context_filters": {
                "notifications_muted": self.active_context == "PRIVAT",
                "wallet_auto_approve_limit_dkk": 500.0 if self.active_context == "ARBEJDE" else 200.0
            }
        }

if __name__ == "__main__":
    c = ContextDaemon()
    print(c.set_context("Rejse"))
