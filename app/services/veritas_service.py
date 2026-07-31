"""
EiraOS Veritas Shield Integration Service
Integrates Lag 1 Rule Engine, C2PA Image Validator, and EUDI Wallet Trust Engine.
"""
import os
import sys

# Add veritas-shield to Python path
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "..", "veritas-shield"))

from lag1_article_analysis.rule_engine import VeritasRuleEngine
from adapters.c2pa_image_validator.validator import C2PAValidator

class EiraOSVeritasService:
    def __init__(self):
        params_path = os.path.join(os.path.dirname(__file__), "..", "..", "veritas-shield", "lag1-article-analysis", "parameters.json")
        self.rule_engine = VeritasRuleEngine(params_path)
        self.c2pa_validator = C2PAValidator()

    def audit_article(self, title: str, text: str) -> dict:
        return self.rule_engine.analyze(text, title=title)

    def validate_image(self, image_url_or_path: str) -> dict:
        return self.c2pa_validator.inspect_image(image_url_or_path)

if __name__ == "__main__":
    service = EiraOSVeritasService()
    res = service.audit_article("Test Artikel", "Energistyrelsen udtaler i en ny rapport...")
    print(res)
