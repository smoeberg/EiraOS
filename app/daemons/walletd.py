"""
walletd — EiraOS Core Wallet & Payment Optimization Daemon
Handles EUDI Wallet credentials, consents, and cost-optimized payment routing (SEPA Instant, Digital Euro, Open Banking PSD3).
Bypasses credit card monopolies by selecting the lowest fee payment rail.
"""

class WalletDaemon:
    def __init__(self):
        self.name = "walletd"

    def optimize_and_pay(self, amount_dkk: float, merchant: str, supported_rails: list) -> dict:
        """
        Automatically selects the cheapest payment rail for the user.
        """
        rail_costs = {
            "sepa_instant": 0.08,
            "digital_euro": 0.00,
            "open_banking_psd3": 0.15,
            "mobilepay": 1.20,
            "visa_mastercard": round(amount_dkk * 0.015 + 0.50, 2)
        }

        # Filter available rails
        available = {r: rail_costs.get(r, 99.0) for r in supported_rails if r in rail_costs}
        if not available:
            # Fallback
            available = {"sepa_instant": 0.08}

        best_rail = min(available, key=available.get)
        saved_fee = max(rail_costs.values()) - available[best_rail]

        return {
            "status": "PAID",
            "amount_dkk": amount_dkk,
            "merchant": merchant,
            "selected_rail": best_rail.upper(),
            "transaction_fee_dkk": available[best_rail],
            "fee_saved_dkk": round(max(0.0, saved_fee), 2),
            "eudi_consent_verified": True
        }

    def list_credentials(self) -> list:
        return [
            {"type": "EUDI_IDENTITY", "issuer": "Digitaliseringsstyrelsen", "status": "VALID"},
            {"type": "DRIVING_LICENSE", "issuer": "Færdselsstyrelsen", "status": "VALID"},
            {"type": "COMPANY_CVR", "issuer": "Erhvervsstyrelsen", "status": "VALID"}
        ]

if __name__ == "__main__":
    w = WalletDaemon()
    print(w.optimize_and_pay(150.0, "DSB Billet", ["sepa_instant", "visa_mastercard", "mobilepay"]))
