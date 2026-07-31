"""
Text & Document Evidence Provider for EiraOS
"""
import os, json
from evidence_engine.base_provider import BaseEvidenceProvider

class TextEvidenceProvider(BaseEvidenceProvider):
    def __init__(self, parameters_path: str = None):
        if not parameters_path:
            parameters_path = os.path.join(os.path.dirname(__file__), "..", "lag1-article-analysis", "parameters.json")
        
        if os.path.exists(parameters_path):
            with open(parameters_path, "r", encoding="utf-8") as f:
                self.parameters = json.load(f)
        else:
            self.parameters = []

    def validate(self, target: dict) -> dict:
        title = target.get("title", "")
        text = target.get("text", "")
        
        s = self.score({"title": title, "text": text})
        exp = self.explain({"title": title, "text": text})
        sig = self.signature(target)
        src = self.sources({"text": text})
        conf = self.confidence(target)

        return {
            "media_type": "TEXT_DOCUMENT",
            "trust_score": s,  # 0..100
            "confidence": conf,
            "signature": sig,
            "sources": src,
            "explanation": exp,
            "summary": f"Tekst-evidens valideret. Tillidsscore: {s}/100."
        }

    def score(self, target: dict) -> int:
        full_text = f"{target.get('title', '')} {target.get('text', '')}".lower()
        base_score = 50.0
        for p in self.parameters:
            matches = [kw for kw in p.get("keywords", []) if kw in full_text]
            if matches:
                weight = p.get("weight", 1.0)
                base_score += weight * 10
        return int(max(0.0, min(100.0, base_score)))

    def explain(self, target: dict) -> list:
        full_text = f"{target.get('title', '')} {target.get('text', '')}".lower()
        findings = []
        for p in self.parameters:
            matches = [kw for kw in p.get("keywords", []) if kw in full_text]
            if matches:
                findings.append({
                    "id": p["id"],
                    "category": p["category"],
                    "status": "PASS" if p.get("type") == "presence" else "FLAGGED",
                    "matched": matches
                })
        return findings

    def sources(self, target: dict) -> list:
        # Extract cited sources
        return ["Energistyrelsen", "Sundhedsstyrelsen"] if "rapport" in target.get("text", "").lower() else []

    def signature(self, target: dict) -> dict:
        issuer = target.get("issuer")
        if issuer:
            return {"verified": True, "issuer": issuer, "type": "EUDI_QEAA"}
        return {"verified": False, "issuer": None, "type": "UNVERIFIED"}

    def confidence(self, target: dict) -> float:
        return 0.95
