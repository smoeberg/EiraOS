# C2PA Image & Media Authenticity Module (`adapters/c2pa-image-validator`)

Dette modul implementerer validering af billeder og medier i **EiraOS** baseret på **C2PA-standarden** (Coalition for Content Provenance and Authenticity).

## Funktioner

1. **JUMBF Manifest Extractor:** Læser og udvinder kryptografiske manifest-kæder direkte fra billed- og videofiler.
2. **Hardware Signature Tjek:** Bekræfter om et billede er taget med et C2PA-kompatibelt kamera (Leica, Canon, Sony, Nikon).
3. **AI Generation & Edits Tracing:** Flagging af syntetisk indhold fremstillet via Midjourney, DALL-E eller Photoshop Generative Fill.
4. **eIDAS / EUDI Wallet Integration:** Verificering af mediers og fotojournalisters digitale signaturer.

## Brug i EiraOS

```python
from validator import C2PAValidator

validator = C2PAValidator()
result = validator.inspect_image("billede.jpg")
print(result["summary_da"])
```
