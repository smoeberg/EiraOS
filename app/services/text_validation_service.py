"""
EiraOS Text & Article Sandheds- og Troværdighedsvalidering Service (Lag 1 Rule Engine)
"""
import os
import json

class TextValidationService:
    def __init__(self):
        # Locate parameters.json
        base_dir = os.path.dirname(__file__)
        params_path = os.path.abspath(os.path.join(base_dir, "..", "..", "veritas-shield", "lag1-article-analysis", "parameters.json"))
        
        if os.path.exists(params_path):
            with open(params_path, "r", encoding="utf-8") as f:
                self.parameters = json.load(f)
        else:
            self.parameters = []

    def validate_text(self, title: str, text: str) -> dict:
        full_text = f"{title} {text}".lower()
        score = 50.0  # Baseline

        findings = []
        for param in self.parameters:
            matches = [kw for kw in param.get("keywords", []) if kw in full_text]
            if matches:
                weight = param.get("weight", 1.0)
                if param.get("type") == "presence":
                    impact = weight * 10
                    score += impact
                    findings.append({
                        "id": param["id"],
                        "category": param["category"],
                        "status": "PASS",
                        "impact": f"+{impact}",
                        "matched": matches
                    })
                elif param.get("type") == "penalty":
                    impact = weight * 10
                    score += impact
                    findings.append({
                        "id": param["id"],
                        "category": param["category"],
                        "status": "FLAGGED",
                        "impact": f"{impact}",
                        "matched": matches
                    })

        # Clamp exact score between 0 and 100 integer
        exact_score = int(max(0.0, min(100.0, score)))

        return {
            "title": title,
            "veritas_score": exact_score,  # Exact 0-100 level
            "total_parameters_audited": len(self.parameters),
            "findings": findings,
            "status": "SUCCESS"
        }
