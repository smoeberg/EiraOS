use crate::ipc::UnixSocketClient;
use crate::models::*;

pub struct EiraCoreBridge {
    veritas_client: UnixSocketClient,
    wallet_client: UnixSocketClient,
    presence_client: UnixSocketClient,
}

impl EiraCoreBridge {
    pub fn new() -> Self {
        Self {
            veritas_client: UnixSocketClient::new("/run/eira/veritasd.sock"),
            wallet_client: UnixSocketClient::new("/run/eira/walletd.sock"),
            presence_client: UnixSocketClient::new("/run/eira/presenced.sock"),
        }
    }

    /// Evaluates Evidence and returns Trust Score (0-100%)
    pub async fn audit_trust(&self, req: EvidenceRequest) -> Result<TrustScoreResponse, String> {
        self.veritas_client
            .send_rpc::<EvidenceRequest, TrustScoreResponse>(&req)
            .await
            .map_err(|e| e.to_string())
    }

    /// Executes cost-optimized payment via walletd (SEPA Instant / Open Banking PSD3)
    pub async fn process_payment(&self, req: PaymentRequest) -> Result<PaymentResponse, String> {
        self.wallet_client
            .send_rpc::<PaymentRequest, PaymentResponse>(&req)
            .await
            .map_err(|e| e.to_string())
    }

    /// Annotates Knowledge Graph Object via presenced
    pub async fn annotate_object(&self, req: AnnotationRequest) -> Result<ObjectPresenceResponse, String> {
        self.presence_client
            .send_rpc::<AnnotationRequest, ObjectPresenceResponse>(&req)
            .await
            .map_err(|e| e.to_string())
    }
}
