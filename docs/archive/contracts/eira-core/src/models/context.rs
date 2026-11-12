use serde::{Serialize, Deserialize};

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct ContextSwitchRequest {
    pub context: String, // "ARBEJDE", "PRIVAT", "REJSE", "FAMILIE", "PROJEKT"
}

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct ContextStateResponse {
    pub active_context: String,
    pub available_contexts: Vec<String>,
}
