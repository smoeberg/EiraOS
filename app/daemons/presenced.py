"""
presenced — EiraOS Core Object-Based Presence & Collaboration Daemon
"Conversation follows Object" — Anchors discussions, decisions, votes, and expert knowledge directly to Knowledge Graph Objects.
"""

class PresenceDaemon:
    def __init__(self):
        self.name = "presenced"
        self.object_discussions = {}

    def annotate_object(self, object_id: str, author: str, comment: str, decision_point: bool = False) -> dict:
        if object_id not in self.object_discussions:
            self.object_discussions[object_id] = []

        entry = {
            "object_id": object_id,
            "author": author,
            "comment": comment,
            "is_decision_point": decision_point,
            "timestamp": "2026-07-31T10:42:00Z"
        }
        self.object_discussions[object_id].append(entry)
        return {"status": "SUCCESS", "entry": entry, "total_annotations": len(self.object_discussions[object_id])}

    def get_object_presence(self, object_id: str) -> dict:
        annotations = self.object_discussions.get(object_id, [])
        return {
            "object_id": object_id,
            "active_collaborators": ["Søren Møberg (Expert: AI/Linux)"],
            "annotations": annotations,
            "decision_history": [a for a in annotations if a["is_decision_point"]]
        }

if __name__ == "__main__":
    p = PresenceDaemon()
    print(p.annotate_object("doc_klima_2026", "Søren Møberg", "Godkendt ifølge EUDI attest", decision_point=True))
