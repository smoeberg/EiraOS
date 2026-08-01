use serde::Serialize;
use serde_json::{Map, Value, json};
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::Duration;

#[cfg(unix)]
use std::os::unix::fs::FileTypeExt;
#[cfg(unix)]
use tokio::io::{AsyncBufReadExt, AsyncReadExt, AsyncWriteExt, BufReader};
#[cfg(unix)]
use tokio::net::UnixStream;

const MAX_REQUEST_BYTES: usize = 4 * 1024 * 1024;
const MAX_RESPONSE_BYTES: usize = 16 * 1024 * 1024;
const DEFAULT_TIMEOUT_MS: u64 = 5_000;
static NEXT_REQUEST_ID: AtomicU64 = AtomicU64::new(1);

#[derive(Serialize)]
struct BridgeError<'a> {
    kind: &'a str,
    message: String,
    daemon: &'a str,
    method: &'a str,
}

fn bridge_error(kind: &str, message: impl Into<String>, daemon: &str, method: &str) -> String {
    serde_json::to_string(&BridgeError {
        kind,
        message: message.into(),
        daemon,
        method,
    })
    .unwrap_or_else(|_| format!("{{\"kind\":\"{kind}\",\"message\":\"IPC failure\"}}"))
}

fn canonical_daemon(daemon: &str) -> Option<&'static str> {
    match daemon.trim() {
        "state" | "stated" => Some("stated"),
        "identity" | "identityd" => Some("identityd"),
        "fleet" | "fleetd" => Some("fleetd"),
        "veritas" | "veritasd" => Some("veritasd"),
        "intent" | "intentd" => Some("intentd"),
        "graph" | "graphd" => Some("graphd"),
        _ => None,
    }
}

fn socket_root() -> PathBuf {
    std::env::var_os("EIRA_RUN_DIR")
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from("/run/eira"))
}

fn socket_path(daemon: &str) -> PathBuf {
    socket_root().join(format!("{daemon}.sock"))
}

fn request_timeout() -> Duration {
    let milliseconds = std::env::var("EIRA_UI_IPC_TIMEOUT_MS")
        .ok()
        .and_then(|value| value.parse::<u64>().ok())
        .unwrap_or(DEFAULT_TIMEOUT_MS)
        .clamp(100, 30_000);
    Duration::from_millis(milliseconds)
}

fn authenticated_params(mut params: Value) -> Result<Value, &'static str> {
    if params.is_null() {
        params = Value::Object(Map::new());
    }
    let object = params
        .as_object_mut()
        .ok_or("JSON-RPC params must be an object or null")?;
    if let Ok(token) = std::env::var("EIRA_IPC_TOKEN") {
        let token = token.trim();
        if !token.is_empty() {
            object.insert("_eira".to_owned(), json!({ "ipc_token": token }));
        }
    }
    Ok(params)
}

#[cfg(unix)]
async fn exchange(
    path: &Path,
    daemon: &str,
    method: &str,
    request_id: u64,
    request: &[u8],
) -> Result<Value, String> {
    let metadata = std::fs::symlink_metadata(path).map_err(|error| {
        bridge_error(
            "socket_unavailable",
            format!("{}: {error}", path.display()),
            daemon,
            method,
        )
    })?;
    if !metadata.file_type().is_socket() {
        return Err(bridge_error(
            "invalid_endpoint",
            "IPC endpoint is not a Unix domain socket",
            daemon,
            method,
        ));
    }

    let mut stream = UnixStream::connect(path).await.map_err(|error| {
        bridge_error("connect_failed", error.to_string(), daemon, method)
    })?;
    stream
        .write_all(request)
        .await
        .map_err(|error| bridge_error("write_failed", error.to_string(), daemon, method))?;
    stream
        .flush()
        .await
        .map_err(|error| bridge_error("write_failed", error.to_string(), daemon, method))?;

    let limited = stream.take((MAX_RESPONSE_BYTES + 1) as u64);
    let mut reader = BufReader::new(limited);
    let mut response_bytes = Vec::with_capacity(8 * 1024);
    let read = reader
        .read_until(b'\n', &mut response_bytes)
        .await
        .map_err(|error| bridge_error("read_failed", error.to_string(), daemon, method))?;
    if read == 0 {
        return Err(bridge_error(
            "empty_response",
            "daemon closed the socket without a response",
            daemon,
            method,
        ));
    }
    if response_bytes.len() > MAX_RESPONSE_BYTES || !response_bytes.ends_with(b"\n") {
        return Err(bridge_error(
            "response_too_large",
            format!("response exceeds {MAX_RESPONSE_BYTES} bytes"),
            daemon,
            method,
        ));
    }
    response_bytes.pop();

    let envelope: Value = serde_json::from_slice(&response_bytes).map_err(|error| {
        bridge_error("invalid_response", error.to_string(), daemon, method)
    })?;
    if envelope.get("id") != Some(&Value::from(request_id)) {
        return Err(bridge_error(
            "response_mismatch",
            "JSON-RPC response id does not match the request",
            daemon,
            method,
        ));
    }
    if let Some(error) = envelope.get("error") {
        return Err(bridge_error(
            "daemon_error",
            error.to_string(),
            daemon,
            method,
        ));
    }
    Ok(envelope.get("result").cloned().unwrap_or(Value::Null))
}

#[tauri::command]
pub async fn send_ipc_request(
    daemon: String,
    method: String,
    params: Value,
) -> Result<Value, String> {
    let canonical = canonical_daemon(&daemon).ok_or_else(|| {
        bridge_error(
            "invalid_daemon",
            "daemon is not in the EiraOS allowlist",
            &daemon,
            &method,
        )
    })?;
    if method.trim().is_empty() || method.len() > 256 {
        return Err(bridge_error(
            "invalid_method",
            "method must contain between 1 and 256 characters",
            canonical,
            &method,
        ));
    }
    let params = authenticated_params(params).map_err(|message| {
        bridge_error("invalid_params", message, canonical, &method)
    })?;
    let request_id = NEXT_REQUEST_ID.fetch_add(1, Ordering::Relaxed);
    let mut request = serde_json::to_vec(&json!({
        "jsonrpc": "2.0",
        "id": request_id,
        "method": method,
        "params": params,
    }))
    .map_err(|error| bridge_error("encode_failed", error.to_string(), canonical, &method))?;
    request.push(b'\n');
    if request.len() > MAX_REQUEST_BYTES {
        return Err(bridge_error(
            "request_too_large",
            format!("request exceeds {MAX_REQUEST_BYTES} bytes"),
            canonical,
            &method,
        ));
    }

    #[cfg(unix)]
    {
        let path = socket_path(canonical);
        return tokio::time::timeout(
            request_timeout(),
            exchange(&path, canonical, &method, request_id, &request),
        )
        .await
        .map_err(|_| {
            bridge_error(
                "timeout",
                format!("request exceeded {} ms", request_timeout().as_millis()),
                canonical,
                &method,
            )
        })?;
    }

    #[cfg(not(unix))]
    {
        let _ = (request_id, request);
        Err(bridge_error(
            "unsupported_platform",
            "native Unix socket IPC requires Linux or another Unix platform",
            canonical,
            &method,
        ))
    }
}

#[cfg(test)]
mod tests {
    use super::{authenticated_params, canonical_daemon};
    use serde_json::json;

    #[test]
    fn daemon_names_are_allowlisted() {
        assert_eq!(canonical_daemon("graph"), Some("graphd"));
        assert_eq!(canonical_daemon("../../tmp/evil"), None);
    }

    #[test]
    fn params_must_be_an_object() {
        assert!(authenticated_params(json!({"id": 1})).is_ok());
        assert!(authenticated_params(json!([1, 2])).is_err());
    }
}
