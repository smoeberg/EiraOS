use serde::{Serialize, Deserialize};

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct EvidenceRequest {
    pub media_type: String, // "text", "image", "pdf", "audio", "video"
    pub title: Option<String>,
    pub text: Option<String>,
    pub url: Option<String>,
    pub issuer: Option<String>,
}

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct TrustScoreResponse {
    pub media_type: String,
    pub trust_score: u8, // Exact 0..100 score
    pub confidence: f32,
    pub summary: String,
    pub signature_verified: bool,
}
