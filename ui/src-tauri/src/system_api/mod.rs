//! EiraSystemAPI v1 — the typed boundary between the EiraOS GUI and Ubuntu.
//!
//! See docs/architecture/eira-system-api.md. The GUI sends an envelope
//! (`api_version`, `request_id`, `operation`, `input`) and always gets back
//! either a result or a structured `EiraError`, never both. Operations are a
//! closed set; there is no generic command or D-Bus passthrough.
//!
//! It runs in the shell process, i.e. as the logged-in user in their session,
//! because Ubuntu authorises actions such as power-off for the *active local
//! session* through polkit. Ubuntu stays the source of truth: every status is
//! read from the owning service, and an action is reported as accepted only
//! when that service accepted it.

pub mod power;

use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::sync::atomic::{AtomicU64, Ordering};

pub const API_VERSION: &str = "1";

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub enum ErrorCode {
    InvalidArgument,
    PermissionDenied,
    ConfirmationRequired,
    CapabilityUnavailable,
    Unsupported,
    IoError,
    VersionMismatch,
    InternalError,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct EiraError {
    pub code: ErrorCode,
    /// Safe, user-facing text (Danish); never secrets or raw tracebacks.
    pub message: String,
    pub retryable: bool,
    pub operation_id: String,
}

impl EiraError {
    pub fn new(code: ErrorCode, message: impl Into<String>) -> Self {
        let retryable = matches!(code, ErrorCode::IoError | ErrorCode::CapabilityUnavailable);
        Self {
            code,
            message: message.into(),
            retryable,
            operation_id: String::new(),
        }
    }
}

#[derive(Debug, Clone, Deserialize)]
pub struct EiraRequest {
    pub api_version: String,
    pub request_id: String,
    pub operation: String,
    /// Part of the v1 contract; no operation currently exposed takes input.
    #[serde(default)]
    #[allow(dead_code)]
    pub input: Value,
}

#[derive(Debug, Clone, Serialize)]
pub struct EiraResponse {
    pub api_version: &'static str,
    pub request_id: String,
    pub operation_id: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub result: Option<Value>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub error: Option<EiraError>,
}

/// Operations this build implements. Anything else fails closed.
pub const OPERATIONS: &[&str] = &["system.capabilities", "power.get_status"];

static NEXT_OPERATION: AtomicU64 = AtomicU64::new(1);

pub struct SystemApi {
    power: Box<dyn power::PowerAdapter>,
}

impl SystemApi {
    pub fn new(power: Box<dyn power::PowerAdapter>) -> Self {
        Self { power }
    }

    pub async fn handle(&self, request: EiraRequest) -> EiraResponse {
        let operation_id = format!("op-{}", NEXT_OPERATION.fetch_add(1, Ordering::Relaxed));
        let outcome = self.dispatch(&request).await;
        let (result, error) = match outcome {
            Ok(value) => (Some(value), None),
            Err(mut error) => {
                error.operation_id = operation_id.clone();
                (None, Some(error))
            }
        };
        EiraResponse {
            api_version: API_VERSION,
            request_id: request.request_id,
            operation_id,
            result,
            error,
        }
    }

    async fn dispatch(&self, request: &EiraRequest) -> Result<Value, EiraError> {
        if request.api_version != API_VERSION {
            return Err(EiraError::new(
                ErrorCode::VersionMismatch,
                format!(
                    "EiraSystemAPI version {} understøttes ikke",
                    request.api_version
                ),
            ));
        }
        if request.request_id.is_empty() || request.request_id.len() > 128 {
            return Err(EiraError::new(
                ErrorCode::InvalidArgument,
                "request_id mangler eller er for langt",
            ));
        }
        match request.operation.as_str() {
            "system.capabilities" => Ok(serde_json::json!({
                "api_version": API_VERSION,
                "operations": OPERATIONS,
            })),
            "power.get_status" => to_value(self.power.status().await),
            // Turning the machine off is a protected action. It must arrive as
            // an intention through the Gate (Gate Kernel 1.0) and never as a
            // direct UI call. Until the Gate exists this fails closed.
            "power.request_action" => Err(EiraError::new(
                ErrorCode::Unsupported,
                "Sluk, genstart og dvale udføres kun via en bekræftet intention gennem Gaten",
            )),
            other => Err(EiraError::new(
                ErrorCode::Unsupported,
                format!("Operationen {other:?} findes ikke i EiraSystemAPI v1"),
            )),
        }
    }
}

fn to_value<T: Serialize>(value: Result<T, EiraError>) -> Result<Value, EiraError> {
    value.and_then(|value| {
        serde_json::to_value(value)
            .map_err(|_| EiraError::new(ErrorCode::InternalError, "Svaret kunne ikke serialiseres"))
    })
}

/// Used when the system bus cannot be reached: every power operation fails
/// closed with CAPABILITY_UNAVAILABLE instead of pretending.
pub struct UnavailablePower;

impl power::PowerAdapter for UnavailablePower {
    fn status(&self) -> power::BoxFuture<'_, Result<power::PowerStatus, EiraError>> {
        Box::pin(async {
            Err(EiraError::new(
                ErrorCode::CapabilityUnavailable,
                "Systemets D-Bus er ikke tilgængelig",
            ))
        })
    }
    fn perform(&self, _action: power::PowerAction) -> power::BoxFuture<'_, Result<(), EiraError>> {
        Box::pin(async {
            Err(EiraError::new(
                ErrorCode::CapabilityUnavailable,
                "Systemets D-Bus er ikke tilgængelig",
            ))
        })
    }
}

#[cfg(test)]
mod tests {
    use super::power::{Availability, mock_power};
    use super::*;
    use serde_json::json;

    fn request(operation: &str, input: Value) -> EiraRequest {
        EiraRequest {
            api_version: "1".into(),
            request_id: "req-1".into(),
            operation: operation.into(),
            input,
        }
    }

    fn api() -> SystemApi {
        SystemApi::new(Box::new(mock_power(Availability::Available)))
    }

    #[tokio::test]
    async fn returns_result_or_error_never_both() {
        let ok = api().handle(request("power.get_status", json!({}))).await;
        assert!(ok.result.is_some() && ok.error.is_none());
        assert_eq!(ok.request_id, "req-1");
        assert_eq!(ok.api_version, "1");

        let err = api()
            .handle(request(
                "power.request_action",
                json!({"action": "poweroff"}),
            ))
            .await;
        assert!(err.result.is_none());
        let error = err.error.unwrap();
        assert_eq!(error.code, ErrorCode::Unsupported);
        assert_eq!(error.operation_id, err.operation_id);
    }

    #[tokio::test]
    async fn fails_closed_on_unknown_operations_versions_and_input() {
        let unknown = api()
            .handle(request("shell.run", json!({"cmd": "rm -rf /"})))
            .await;
        assert_eq!(unknown.error.unwrap().code, ErrorCode::Unsupported);

        let mut old = request("power.get_status", json!({}));
        old.api_version = "0".into();
        assert_eq!(
            api().handle(old).await.error.unwrap().code,
            ErrorCode::VersionMismatch
        );

        let bad = api()
            .handle(request(
                "power.request_action",
                json!({"action": "format_disk", "confirmed": true}),
            ))
            .await;
        assert_eq!(bad.error.unwrap().code, ErrorCode::Unsupported);

        let extra = api()
            .handle(request(
                "power.request_action",
                json!({"action": "poweroff", "confirmed": true, "force": true}),
            ))
            .await;
        assert_eq!(extra.error.unwrap().code, ErrorCode::Unsupported);
    }

    #[tokio::test]
    async fn power_actions_never_execute_from_a_direct_call() {
        // Even a fully confirmed, well-formed request must not reach logind
        // without the Gate.
        let response = api()
            .handle(request(
                "power.request_action",
                json!({"action": "poweroff", "confirmed": true}),
            ))
            .await;
        assert_eq!(response.error.unwrap().code, ErrorCode::Unsupported);
        assert!(!OPERATIONS.contains(&"power.request_action"));
    }

    #[tokio::test]
    async fn serialises_the_contract_shape() {
        let response = api().handle(request("power.get_status", json!({}))).await;
        let value = serde_json::to_value(response).unwrap();
        assert_eq!(value["result"]["actions"]["poweroff"], "available");
        assert_eq!(value["result"]["sources"]["logind"], true);
        assert!(value.get("error").is_none());

        let caps = api()
            .handle(request("system.capabilities", json!({})))
            .await;
        assert_eq!(caps.result.unwrap()["operations"], json!(OPERATIONS));
    }

    #[tokio::test]
    async fn unavailable_bus_fails_closed() {
        let api = SystemApi::new(Box::new(UnavailablePower));
        let response = api.handle(request("power.get_status", json!({}))).await;
        assert_eq!(
            response.error.unwrap().code,
            ErrorCode::CapabilityUnavailable
        );
    }
}
