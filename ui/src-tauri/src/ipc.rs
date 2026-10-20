//! Tauri v2 Unix Domain Socket bridge to EiraOS daemons.
//!
//! Speaks newline-framed JSON-RPC 2.0 against `/run/eira/<daemon>.sock`
//! (or `$EIRA_SOCKET_DIR` / `$EIRA_RUN_DIR`). Fail-closed: unknown daemon,
//! missing socket, timeout, and JSON-RPC errors become structured `Err(String)`.

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

/// Canonical daemon names aligned with `app/ipc/paths.py` / `app/daemons/runner.py`.
fn canonical_daemon(daemon: &str) -> Option<&'static str> {
    match daemon.trim() {
        "state" | "stated" => Some("stated"),
        "identity" | "identityd" => Some("identityd"),
        "fleet" | "fleetd" => Some("fleetd"),
        "veritas" | "veritasd" => Some("veritasd"),
        "intent" | "intentd" => Some("intentd"),
        "graph" | "graphd" => Some("graphd"),
        "wallet" | "walletd" => Some("walletd"),
        "presence" | "presenced" => Some("presenced"),
        "context" | "contextd" => Some("contextd"),
        _ => None,
    }
}

/// Socket directory convention:
/// 1. `EIRA_SOCKET_DIR` (Task 7.1 contract)
/// 2. `EIRA_RUN_DIR` (Python daemons / `app/ipc/paths.py`)
/// 3. `/run/eira` (production default)
fn socket_root() -> PathBuf {
    if let Some(dir) = std::env::var_os("EIRA_SOCKET_DIR") {
        return PathBuf::from(dir);
    }
    if let Some(dir) = std::env::var_os("EIRA_RUN_DIR") {
        return PathBuf::from(dir);
    }
    PathBuf::from("/run/eira")
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

/// Send a JSON-RPC 2.0 request to an EiraOS daemon over a Unix domain socket.
///
/// Fail-closed: unknown daemon, missing socket, timeout, and daemon-side
/// JSON-RPC errors are returned as structured error strings (never panic).
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
    use super::{
        authenticated_params, bridge_error, canonical_daemon, socket_path, socket_root,
        MAX_REQUEST_BYTES,
    };
    use serde_json::{json, Value};

    #[test]
    fn daemon_names_are_allowlisted() {
        assert_eq!(canonical_daemon("graph"), Some("graphd"));
        assert_eq!(canonical_daemon("intentd"), Some("intentd"));
        assert_eq!(canonical_daemon("wallet"), Some("walletd"));
        assert_eq!(canonical_daemon("presenced"), Some("presenced"));
        assert_eq!(canonical_daemon("context"), Some("contextd"));
        assert_eq!(canonical_daemon("../../tmp/evil"), None);
        assert_eq!(canonical_daemon(""), None);
        assert_eq!(canonical_daemon("unknown"), None);
    }

    #[test]
    fn params_must_be_an_object() {
        assert!(authenticated_params(json!({"id": 1})).is_ok());
        assert!(authenticated_params(Value::Null).is_ok());
        assert!(authenticated_params(json!([1, 2])).is_err());
        assert!(authenticated_params(json!("string")).is_err());
    }

    #[test]
    fn bridge_error_is_structured_json() {
        let err = bridge_error("timeout", "took too long", "intentd", "intent.plan");
        let parsed: Value = serde_json::from_str(&err).expect("valid json");
        assert_eq!(parsed["kind"], "timeout");
        assert_eq!(parsed["daemon"], "intentd");
        assert_eq!(parsed["method"], "intent.plan");
        assert!(parsed["message"].as_str().unwrap().contains("too long"));
    }

    #[test]
    fn socket_root_prefers_eira_socket_dir() {
        unsafe { std::env::set_var("EIRA_SOCKET_DIR", "/tmp/eira-sock-test"); }
        unsafe { std::env::remove_var("EIRA_RUN_DIR"); }
        assert_eq!(socket_root(), std::path::PathBuf::from("/tmp/eira-sock-test"));
        unsafe { std::env::remove_var("EIRA_SOCKET_DIR"); }
        unsafe { std::env::set_var("EIRA_RUN_DIR", "/tmp/eira-run-test"); }
        assert_eq!(socket_root(), std::path::PathBuf::from("/tmp/eira-run-test"));
        unsafe { std::env::remove_var("EIRA_RUN_DIR"); }
        assert_eq!(socket_root(), std::path::PathBuf::from("/run/eira"));
    }

    #[test]
    fn socket_path_joins_daemon_sock() {
        unsafe { std::env::set_var("EIRA_SOCKET_DIR", "/tmp/eira-sp"); }
        assert_eq!(
            socket_path("intentd"),
            std::path::PathBuf::from("/tmp/eira-sp/intentd.sock")
        );
        unsafe { std::env::remove_var("EIRA_SOCKET_DIR"); }
    }

    #[test]
    fn max_request_bound_is_four_mib() {
        assert_eq!(MAX_REQUEST_BYTES, 4 * 1024 * 1024);
    }

    #[cfg(unix)]
    mod mock_socket {
        use super::super::{exchange, send_ipc_request, socket_path};
        use serde_json::{json, Value};
        use std::path::PathBuf;
        use std::time::Duration;
        use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader};
        use tokio::net::UnixListener;

        /// AF_UNIX sun_path is ~108 bytes; keep paths short under /tmp.
        fn short_temp_dir() -> PathBuf {
            let stamp = std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos();
            let dir = std::env::temp_dir().join(format!("e{:x}", stamp % 0xffff_ffff));
            let _ = std::fs::remove_dir_all(&dir);
            std::fs::create_dir_all(&dir).expect("create short temp dir");
            dir
        }

        async fn serve_one_response(listener: UnixListener, response_line: String) {
            let (mut stream, _) = listener.accept().await.expect("accept");
            let mut reader = BufReader::new(&mut stream);
            let mut line = String::new();
            reader.read_line(&mut line).await.expect("read request");
            assert!(line.contains("\"jsonrpc\":\"2.0\"") || line.contains("\"jsonrpc\": \"2.0\""));
            stream
                .write_all(response_line.as_bytes())
                .await
                .expect("write response");
            stream.flush().await.expect("flush");
        }

        #[tokio::test]
        async fn exchange_succeeds_against_mock_daemon() {
            let dir = short_temp_dir();
            let sock = dir.join("intentd.sock");
            let listener = UnixListener::bind(&sock).expect("bind mock socket");

            let server = tokio::spawn(async move {
                serve_one_response(
                    listener,
                    "{\"jsonrpc\":\"2.0\",\"id\":42,\"result\":{\"ok\":true,\"daemon\":\"intentd\"}}\n"
                        .to_owned(),
                )
                .await;
            });

            let request = b"{\"jsonrpc\":\"2.0\",\"id\":42,\"method\":\"health\",\"params\":{}}\n";
            let result = tokio::time::timeout(
                Duration::from_secs(2),
                exchange(&sock, "intentd", "health", 42, request),
            )
            .await
            .expect("no timeout")
            .expect("exchange ok");

            assert_eq!(result["ok"], true);
            assert_eq!(result["daemon"], "intentd");
            server.await.expect("server task");
            let _ = std::fs::remove_dir_all(&dir);
        }

        #[tokio::test]
        async fn exchange_maps_jsonrpc_error() {
            let dir = short_temp_dir();
            let sock = dir.join("graphd.sock");
            let listener = UnixListener::bind(&sock).expect("bind");

            let server = tokio::spawn(async move {
                serve_one_response(
                    listener,
                    "{\"jsonrpc\":\"2.0\",\"id\":7,\"error\":{\"code\":-32601,\"message\":\"Method not found\"}}\n"
                        .to_owned(),
                )
                .await;
            });

            let request = b"{\"jsonrpc\":\"2.0\",\"id\":7,\"method\":\"nope\",\"params\":{}}\n";
            let err = exchange(&sock, "graphd", "nope", 7, request)
                .await
                .expect_err("must fail-closed on JSON-RPC error");
            let parsed: Value = serde_json::from_str(&err).expect("structured error");
            assert_eq!(parsed["kind"], "daemon_error");
            assert_eq!(parsed["daemon"], "graphd");
            server.await.expect("server task");
            let _ = std::fs::remove_dir_all(&dir);
        }

        #[tokio::test]
        async fn exchange_fails_when_socket_missing() {
            let dir = short_temp_dir();
            let sock = dir.join("missing.sock");
            let err = exchange(
                &sock,
                "stated",
                "health",
                1,
                b"{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"health\",\"params\":{}}\n",
            )
            .await
            .expect_err("missing socket");
            let parsed: Value = serde_json::from_str(&err).expect("structured error");
            assert_eq!(parsed["kind"], "socket_unavailable");
            let _ = std::fs::remove_dir_all(&dir);
        }

        #[tokio::test]
        async fn send_ipc_request_roundtrip_via_env_socket_dir() {
            let _env_guard = ENV_LOCK.lock().unwrap();
            let dir = short_temp_dir();
            let sock_path = dir.join("walletd.sock");
            let listener = UnixListener::bind(&sock_path).expect("bind walletd");

            unsafe { std::env::set_var("EIRA_SOCKET_DIR", dir.as_os_str()); }
            unsafe { std::env::set_var("EIRA_UI_IPC_TIMEOUT_MS", "2000"); }

            let server = tokio::spawn(async move {
                let (mut stream, _) = listener.accept().await.expect("accept");
                let mut reader = BufReader::new(&mut stream);
                let mut line = String::new();
                reader.read_line(&mut line).await.expect("read");
                let req: Value = serde_json::from_str(line.trim()).expect("req json");
                let id = req["id"].clone();
                let body = json!({
                    "jsonrpc": "2.0",
                    "id": id,
                    "result": { "status": "ok", "rails": ["sepa_instant"] }
                });
                let mut out = serde_json::to_vec(&body).unwrap();
                out.push(b'\n');
                stream.write_all(&out).await.expect("write");
                stream.flush().await.expect("flush");
            });

            assert_eq!(socket_path("walletd"), sock_path);

            let result = send_ipc_request(
                "wallet".to_owned(),
                "wallet.list_credentials".to_owned(),
                json!({}),
            )
            .await
            .expect("send_ipc_request ok");

            assert_eq!(result["status"], "ok");
            assert_eq!(result["rails"][0], "sepa_instant");

            server.await.expect("server");
            unsafe { std::env::remove_var("EIRA_SOCKET_DIR"); }
            unsafe { std::env::remove_var("EIRA_UI_IPC_TIMEOUT_MS"); }
            let _ = std::fs::remove_dir_all(&dir);
        }

        #[tokio::test]
        async fn send_ipc_request_rejects_unknown_daemon() {
            let err = send_ipc_request(
                "evil-daemon".to_owned(),
                "hack".to_owned(),
                json!({}),
            )
            .await
            .expect_err("unknown daemon");
            let parsed: Value = serde_json::from_str(&err).expect("json");
            assert_eq!(parsed["kind"], "invalid_daemon");
        }

        #[tokio::test]
        async fn send_ipc_request_timeout_is_fail_closed() {
            let _env_guard = ENV_LOCK.lock().unwrap();
            let dir = short_temp_dir();
            let sock_path = dir.join("fleetd.sock");
            let listener = UnixListener::bind(&sock_path).expect("bind");
            unsafe { std::env::set_var("EIRA_SOCKET_DIR", dir.as_os_str()); }
            unsafe { std::env::set_var("EIRA_UI_IPC_TIMEOUT_MS", "150"); }

            let server = tokio::spawn(async move {
                let (_stream, _) = listener.accept().await.expect("accept");
                tokio::time::sleep(Duration::from_secs(5)).await;
            });

            let err = send_ipc_request(
                "fleetd".to_owned(),
                "fleet.heartbeat".to_owned(),
                json!({}),
            )
            .await
            .expect_err("timeout");
            let parsed: Value = serde_json::from_str(&err).expect("json");
            assert_eq!(parsed["kind"], "timeout");
            assert_eq!(parsed["daemon"], "fleetd");

            server.abort();
            unsafe { std::env::remove_var("EIRA_SOCKET_DIR"); }
            unsafe { std::env::remove_var("EIRA_UI_IPC_TIMEOUT_MS"); }
            let _ = std::fs::remove_dir_all(&dir);
        }
    }
}
