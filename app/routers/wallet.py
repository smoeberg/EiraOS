"""
FastAPI Router for walletd (Payment Optimization & EUDI Credentials)
"""
from fastapi import APIRouter
from pydantic import BaseModel
from typing import List
from app.daemons.walletd import WalletDaemon

router = APIRouter(prefix="/v1/wallet", tags=["Eira Wallet & Payments"])
wallet_daemon = WalletDaemon()

class PaymentRequest(BaseModel):
    amount_dkk: float
    merchant: str
    supported_rails: List[str] = ["sepa_instant", "digital_euro", "visa_mastercard"]

@router.post("/pay")
def process_payment(req: PaymentRequest):
    return wallet_daemon.optimize_and_pay(req.amount_dkk, req.merchant, req.supported_rails)

@router.get("/credentials")
def get_credentials():
    return wallet_daemon.list_credentials()
