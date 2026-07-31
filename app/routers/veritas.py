"""
FastAPI Router for Veritas Shield (Tekst- og Billedvalidering for EiraOS)
Endpoints:
  - POST /v1/veritas/validate-text
  - POST /v1/veritas/validate-image
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.services.text_validation_service import TextValidationService
from app.services.veritas_service import EiraOSVeritasService

router = APIRouter(prefix="/v1/veritas", tags=["Veritas Shield Validation"])

text_service = TextValidationService()
veritas_service = EiraOSVeritasService()

class TextValidationRequest(BaseModel):
    title: str = ""
    text: str

class ImageValidationRequest(BaseModel):
    image_url: str

@router.post("/validate-text")
def validate_text(req: TextValidationRequest):
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="Tekst kan ikke være tom.")
    return text_service.validate_text(title=req.title, text=req.text)

@router.post("/validate-image")
def validate_image(req: ImageValidationRequest):
    if not req.image_url.strip():
        raise HTTPException(status_code=400, detail="Billed-URL kan ikke være tom.")
    return veritas_service.validate_image(req.image_url)
