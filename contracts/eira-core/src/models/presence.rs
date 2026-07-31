use serde::{Serialize, Deserialize};

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct AnnotationRequest {
    pub object_id: String,
    pub author: String,
    pub comment: String,
    pub is_decision_point: bool,
}

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct ObjectPresenceResponse {
    pub object_id: String,
    pub active_collaborators: Vec<String>,
    pub total_annotations: usize,
}
