"""
C2PA Content Credentials Validator Module for EiraOS & Veritas Shield
"""
import json
import os

class C2PAValidator:
    def __init__(self, trusted_roots_path: str = None):
        self.trusted_roots = trusted_roots_path

    def inspect_image(self, file_path_or_url: str) -> dict:
        """
        Extracts C2PA JUMBF Manifest and validates provenance chain.
        """
        # Simulated C2PA manifest extraction for demonstration / PoC
        lower_path = file_path_or_url.lower()

        if "ai" in lower_path or "midjourney" in lower_path or "dall-e" in lower_path:
            return {
                "has_c2pa_manifest": True,
                "badge": "CR_AI_GENERATED",
                "badge_color": "PURPLE_ROBOT",
                "signer": "Midjourney Inc. (AI Generator)",
                "actions": [
                    {"action": "c2pa.created", "software": "Midjourney v6.0"},
                    {"action": "c2pa.edited", "software": "Adobe Photoshop Generative Fill"}
                ],
                "authenticity": "SYNTHETIC_MEDIA",
                "summary_da": "Billedet indeholder syntetisk AI-genereret materiale."
            }

        elif "canon" in lower_path or "leica" in lower_path or "press" in lower_path or "dr" in lower_path:
            return {
                "has_c2pa_manifest": True,
                "badge": "CR_AUTHENTIC_HARDWARE",
                "badge_color": "GREEN_SHIELD",
                "signer": "Pressefotograf Jens Hansen / Politiken Foto",
                "camera": "Canon EOS R5 (Hardware Signed)",
                "actions": [
                    {"action": "c2pa.captured", "device": "Canon EOS R5", "time": "2026-07-31T08:30:00Z"},
                    {"action": "c2pa.color_adjustments", "software": "Lightroom Classic"}
                ],
                "authenticity": "AUTHENTIC_PHOTO",
                "summary_da": "Autentisk foto. Optaget med hardware-signeret kamera uden AI-manipulation."
            }

        else:
            return {
                "has_c2pa_manifest": False,
                "badge": "CR_UNVERIFIED",
                "badge_color": "YELLOW_OR_RED",
                "signer": None,
                "authenticity": "LEGACY_OR_UNVERIFIED_MEDIA",
                "summary_da": "Billedet har intet C2PA-manifest. Kræver kildekritisk opmærksomhed."
            }

if __name__ == "__main__":
    validator = C2PAValidator()
    
    test_samples = [
        "https://dr.dk/images/klima_demo_canon_press.jpg",
        "https://socialmedia.com/pave_dynejakke_midjourney_ai.png",
        "https://random-site.com/old_photo.jpg"
    ]
    
    for sample in test_samples:
        print(f"=== Testing: {sample} ===")
        res = validator.inspect_image(sample)
        print(json.dumps(res, indent=2, ensure_ascii=False))
        print()
