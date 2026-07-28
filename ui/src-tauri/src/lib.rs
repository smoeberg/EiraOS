use serde_json::{json, Value};
use std::io::{Read, Write};
use std::path::PathBuf;

#[cfg(unix)]
use std::os::unix::net::UnixStream;

#[cfg(windows)]
use uds_windows::UnixStream;

fn run_dir() -> PathBuf {
    if let Ok(dir) = std::env::var("EIRA_RUN_DIR") {
        return PathBuf::from(dir);
    }
    let mut path = std::env::current_exe().unwrap_or_default();
    path.pop();
    path.pop();
    path.pop();
    path.push("data");
    path.push("run");
    path
}

fn socket_path(daemon: &str) -> PathBuf {
    let file = match daemon {
        "intent" => "intent.sock",
        "identity" => "identity.sock",
        "graph" => "graph.sock",
        _ => panic!("unknown daemon"),
    };
    run_dir().join(file)
}

pub fn ipc_call(daemon: &str, method: &str, params: Value) -> Result<Value, String> {
    let path = socket_path(daemon);
    if !path.exists() {
        return Err(format!(
            "Socket not found: {}. Start: python -m app.daemons.runner",
            path.display()
        ));
    }

    let request = json!({
        "jsonrpc": "2.0",
        "id": 1,
        "method": method,
        "params": params,
    });

    let mut stream = UnixStream::connect(&path).map_err(|e| e.to_string())?;
    let payload = format!("{}\n", request);
    stream
        .write_all(payload.as_bytes())
        .map_err(|e| e.to_string())?;

    let mut buffer = Vec::new();
    let mut chunk = [0u8; 4096];
    loop {
        let n = stream.read(&mut chunk).map_err(|e| e.to_string())?;
        if n == 0 {
            break;
        }
        buffer.extend_from_slice(&chunk[..n]);
        if buffer.contains(&b'\n') {
            break;
        }
    }

    let line = String::from_utf8(buffer)
        .map_err(|e| e.to_string())?
        .lines()
        .next()
        .unwrap_or("")
        .to_string();
    let response: Value = serde_json::from_str(&line).map_err(|e| e.to_string())?;

    if let Some(err) = response.get("error") {
        return Err(err.to_string());
    }
    Ok(response.get("result").cloned().unwrap_or(Value::Null))
}

#[tauri::command]
fn dashboard_get(actor_id: Option<String>) -> Result<Value, String> {
    ipc_call(
        "intent",
        "dashboard.get",
        json!({ "actor_id": actor_id.unwrap_or_else(|| "mette@kommune.dk".into()) }),
    )
}

#[tauri::command]
fn intent_plan(raw_input: String, focus: Option<String>) -> Result<Value, String> {
    ipc_call(
        "intent",
        "intent.plan",
        json!({
            "raw_input": raw_input,
            "focus": focus.unwrap_or_else(|| "Kommunepilot".into()),
            "use_mistral": true,
        }),
    )
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![dashboard_get, intent_plan])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
