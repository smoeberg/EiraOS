use serde::{Serialize, Deserialize};

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct PaymentRequest {
    pub amount_dkk: f64,
    pub merchant: String,
    pub supported_rails: Vec<String>,
}

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct PaymentResponse {
    pub status: String,
    pub amount_dkk: f64,
    pub merchant: String,
    pub selected_rail: String,
    pub transaction_fee_dkk: f64,
    pub fee_saved_dkk: f64,
}
