"""Wallet/payment daemon with fail-closed behavior until real providers are configured.

No payment rail or credential status is inferred locally. Production success
must come from an authenticated provider integration, not a fee estimate.
"""

from __future__ import annotations

from typing import Any


class WalletDaemon:
    def __init__(self) -> None:
        self.name = "walletd"

    def optimize_and_pay(
        self, amount_dkk: float, merchant: str, supported_rails: list[str]
    ) -> dict[str, Any]:
        """Decline safely until a real payment provider and consent verifier exist."""
        return {
            "status": "NOT_CONFIGURED",
            "reason": "payment_provider_and_consent_verifier_not_configured",
            "amount_dkk": amount_dkk,
            "merchant": merchant,
            "selected_rail": None,
            "transaction_id": None,
            "eudi_consent_verified": False,
        }

    def list_credentials(self) -> list[dict[str, Any]]:
        """No credentials are claimed valid without a live trusted issuer."""
        return []


if __name__ == "__main__":
    import json

    wallet = WalletDaemon()
    print(json.dumps(wallet.optimize_and_pay(
        150.0, "DSB Billet", ["sepa_instant", "visa_mastercard", "mobilepay"]
    )))
