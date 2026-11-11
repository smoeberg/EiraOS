//! JSON-RPC to the daemons: newline-framed, one request per connection,
//! the IPC token read from the root-owned /etc/eira/eira.conf (never from
//! the environment, R-5.1).

use serde_json::{Value, json};
use std::io::{BufRead, BufReader, Write};
use std::os::unix::net::UnixStream;
use std::path::Path;
use std::time::Duration;

pub const RUN_DIR: &str = "/run/eira";
pub const CONF: &str = "/etc/eira/eira.conf";

#[derive(Debug)]
pub enum RpcError {
    Io(String),
    Remote {
        code: i64,
        message: String,
        data: Value,
    },
    Protocol(String),
}

impl std::fmt::Display for RpcError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            RpcError::Io(e) => write!(f, "io: {e}"),
            RpcError::Remote {
                code,
                message,
                data,
            } => write!(f, "{code} {message} {data}"),
            RpcError::Protocol(e) => write!(f, "protocol: {e}"),
        }
    }
}

pub fn ipc_token(conf: &Path) -> String {
    std::fs::read_to_string(conf)
        .ok()
        .and_then(|text| {
            text.lines().find_map(|line| {
                line.strip_prefix("EIRA_IPC_TOKEN=")
                    .map(|v| v.trim().to_string())
            })
        })
        .unwrap_or_default()
}

pub fn call(
    socket: &Path,
    token: &str,
    method: &str,
    mut params: Value,
) -> Result<Value, RpcError> {
    if !token.is_empty() {
        params["_eira"] = json!({ "ipc_token": token });
    }
    let request = json!({"jsonrpc": "2.0", "id": 1, "method": method, "params": params});
    let mut stream = UnixStream::connect(socket).map_err(|e| RpcError::Io(e.to_string()))?;
    stream.set_read_timeout(Some(Duration::from_secs(30))).ok();
    let mut line =
        serde_json::to_string(&request).map_err(|e| RpcError::Protocol(e.to_string()))?;
    line.push('\n');
    stream
        .write_all(line.as_bytes())
        .map_err(|e| RpcError::Io(e.to_string()))?;
    let mut reply = String::new();
    BufReader::new(&stream)
        .read_line(&mut reply)
        .map_err(|e| RpcError::Io(e.to_string()))?;
    let reply: Value =
        serde_json::from_str(&reply).map_err(|e| RpcError::Protocol(e.to_string()))?;
    if let Some(error) = reply.get("error") {
        return Err(RpcError::Remote {
            code: error["code"].as_i64().unwrap_or(0),
            message: error["message"].as_str().unwrap_or("").to_string(),
            data: error.get("data").cloned().unwrap_or(Value::Null),
        });
    }
    reply
        .get("result")
        .cloned()
        .ok_or_else(|| RpcError::Protocol("no result".into()))
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::os::unix::net::UnixListener;

    #[test]
    fn the_token_comes_from_the_config_file() {
        let dir = std::env::temp_dir().join(format!("eira-agent-conf-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        let conf = dir.join("eira.conf");
        std::fs::write(&conf, "X=1\nEIRA_IPC_TOKEN=secret \n").unwrap();
        assert_eq!(ipc_token(&conf), "secret");
        assert_eq!(ipc_token(&dir.join("missing")), "");
    }

    #[test]
    fn a_call_sends_one_line_and_reads_the_result_or_error() {
        let dir = std::env::temp_dir().join(format!("eira-agent-rpc-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        let path = dir.join("d.sock");
        let _ = std::fs::remove_file(&path);
        let listener = UnixListener::bind(&path).unwrap();
        let server = std::thread::spawn(move || {
            for (i, conn) in listener.incoming().take(2).enumerate() {
                let mut conn = conn.unwrap();
                let mut line = String::new();
                BufReader::new(&conn).read_line(&mut line).unwrap();
                let request: Value = serde_json::from_str(&line).unwrap();
                assert_eq!(request["params"]["_eira"]["ipc_token"], "t");
                let reply = if i == 0 {
                    json!({"jsonrpc": "2.0", "id": 1, "result": {"echo": request["params"]["x"]}})
                } else {
                    json!({"jsonrpc": "2.0", "id": 1, "error": {"code": -32061, "message": "E_CONSENT_AGENT"}})
                };
                conn.write_all((reply.to_string() + "\n").as_bytes())
                    .unwrap();
            }
        });
        assert_eq!(call(&path, "t", "m", json!({"x": 5})).unwrap()["echo"], 5);
        match call(&path, "t", "m", json!({})) {
            Err(RpcError::Remote { code, .. }) => assert_eq!(code, -32061),
            other => panic!("{other:?}"),
        }
        server.join().unwrap();
    }
}
