"""
Lag 1 Artikelanalyse - Rule Engine for Veritas Shield EiraOS
"""
import json
import os

class VeritasRuleEngine:
    def __init__(self, parameters_path: str):
        with open(parameters_path, "r", encoding="utf-8") as f:
            self.parameters = json.load(f)

    def analyze(self, article_text: str, title: str = "") -> dict:
        full_text = f"{title} {article_text}".lower()
        score = 50.0  # Baseline neutral score
        findings = []

        for param in self.parameters:
            matches = [kw for kw in param["keywords"] if kw in full_text]
            if matches:
                weight = param["weight"]
                if param["type"] == "presence":
                    score += weight * 10
                    findings.append({
                        "id": param["id"],
                        "category": param["category"],
                        "status": "PASS",
                        "impact": f"+{weight * 10}",
                        "matched": matches
                    })
                elif param["type"] == "penalty":
                    score += weight * 10  # negative impact
                    findings.append({
                        "id": param["id"],
                        "category": param["category"],
                        "status": "FLAGGED",
                        "impact": f"{weight * 10}",
                        "matched": matches
                    })

        final_score = max(0.0, min(100.0, score))
        
        if final_score >= 70:
            risk_level = "LOW_RISK_GREEN"
            recommendation = "Høj kildeforankring og neutral tone. Kan anvendes som pålidelig kilde."
        elif final_score >= 45:
            risk_level = "MEDIUM_RISK_YELLOW"
            recommendation = "Brugbar artikel, men vær opmærksom på manglende parthøring eller ladet sprog."
        else:
            risk_level = "HIGH_RISK_RED"
            recommendation = "Høj risiko for vildledning eller sensationalisme. Anbefales ikke som primær kilde."

        return {
            "title": title,
            "final_score": round(final_score, 1),
            "risk_level": risk_level,
            "recommendation": recommendation,
            "findings": findings
        }

if __name__ == "__main__":
    params_path = os.path.join(os.path.dirname(__file__), "parameters.json")
    engine = VeritasRuleEngine(params_path)
    
    test_article = """
    En ny undersøgelse og rapport fra Energistyrelsen viser, at den grønne omstilling fremrider.
    Ministeriet har forsøgt at få en kommentar fra oppositionen, som er forelagt kritikken.
    Skandaløst og vanviddet præger dog debatten.
    """
    
    result = engine.analyze(test_article, title="Status på Grøn Omstilling")
    print(json.dumps(result, indent=2, ensure_ascii=False))
