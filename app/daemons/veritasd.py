"""
eira-veritasd — EiraOS Core Veritas Trust & Evidence Daemon
Listens on system bus / IPC, evaluates all incoming objects for Trust Score (0-100%).
"""
import time
import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "..", "veritas-shield"))

from evidence_engine.providers.text_provider import TextEvidenceProvider
from evidence_engine.providers.image_provider import ImageEvidenceProvider

class VeritasDaemon:
    def __init__(self):
        self.name = "eira-veritasd"
        self.text_provider = TextEvidenceProvider()
        self.image_provider = ImageEvidenceProvider()

    def process_evidence(self, input_data: dict) -> dict:
        media_type = input_data.get("type", "text").lower()
        if media_type in ["text", "document", "pdf", "article"]:
            return self.text_provider.validate(input_data)
        elif media_type in ["image", "photo", "c2pa"]:
            return self.image_provider.validate(input_data)
        else:
            return {
                "media_type": media_type.upper(),
                "trust_score": 50,
                "confidence": 0.50,
                "summary": "Standard uverificeret objekt"
            }

    def run_loop(self):
        print(f"[{self.name}] Daemon started. Ready to evaluate Trust Scores across EiraOS Knowledge Graph.")

if __name__ == "__main__":
    daemon = VeritasDaemon()
    daemon.run_loop()
