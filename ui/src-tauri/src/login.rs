//! Desktop login (GATE-KERNEL bilag A pkt. 1; RFC 8252 "OAuth 2.0 for Native Apps").
//!
//! 1. Bind an ephemeral port on 127.0.0.1 (the IPv4 loopback literal).
//! 2. identityd `identity.login_start` with that redirect: Entra URL with
//!    PKCE + nonce, state bound to this OS user (loginuid + SO_PEERCRED).
//! 3. Open the system browser on the URL.
//! 4. Wait for exactly one `GET /callback` carrying the expected `state`.
//!    Other requests (favicon, a local process probing the port) get a 404
//!    and are ignored; a wrong state is never forwarded.
//! 5. identityd `identity.login_complete` → the session the gate accepts.
//!
//! The code never touches the webview: it goes straight from the loopback
//! socket to identityd. Only the resulting session id is returned.
//!
//! Trusted path for consent: identityd also returns the session's consent
//! key. It stays here, in this process's memory, and is never handed to the
//! webview. `gate_consent` / `gate_confirm` sign each decision with it
//! (app/gate/consent_proof.py), so another program running as the same user,
//! even with the session id, cannot consent.

use hmac::{Hmac, Mac};
use serde::Serialize;
use serde_json::{Value, json};
use sha2::Sha256;
use std::sync::Mutex;
use std::time::Duration;
use tokio::io::{AsyncReadExt, AsyncWriteExt};
use tokio::net::TcpListener;

pub const LOGIN_TIMEOUT: Duration = Duration::from_secs(300);
const CONSENT_DOMAIN: &str = "EIRA-CONSENT-V1";

/// The logged-in session and, on a development machine, its consent key
/// (process memory only). On an installed system identityd never gives the
/// app the key: the consent agent holds it (EIRA-CONSENT-AGENT §5.3).
struct Held {
    session_id: String,
    consent_key: Option<Vec<u8>>,
}

static HELD: Mutex<Option<Held>> = Mutex::new(None);
const MAX_REQUEST_HEAD: usize = 8 * 1024;

#[derive(Debug, PartialEq, Eq)]
pub enum Callback {
    /// The expected callback with its authorization code.
    Code(String),
    /// Entra reported an error (user cancelled, consent denied, …).
    Denied(String),
    /// Not our callback: wrong path, wrong state or malformed. Ignore it.
    Ignore,
}

#[derive(Debug, Serialize)]
pub struct LoginResult {
    pub session_id: String,
    pub identity: String,
    pub expires_at: Option<String>,
}

pub fn redirect_uri(port: u16) -> String {
    format!("http://127.0.0.1:{port}/callback")
}

fn percent_decode(input: &str) -> Option<String> {
    let bytes = input.as_bytes();
    let mut out = Vec::with_capacity(bytes.len());
    let mut i = 0;
    while i < bytes.len() {
        match bytes[i] {
            b'%' => {
                let hex = input.get(i + 1..i + 3)?;
                out.push(u8::from_str_radix(hex, 16).ok()?);
                i += 3;
            }
            b'+' => {
                out.push(b' ');
                i += 1;
            }
            byte => {
                out.push(byte);
                i += 1;
            }
        }
    }
    String::from_utf8(out).ok()
}

/// Judge one HTTP request head against the expected state. Pure, so the
/// rules are unit-tested without sockets.
pub fn parse_callback(head: &str, expected_state: &str) -> Callback {
    let Some(line) = head.lines().next() else {
        return Callback::Ignore;
    };
    let mut parts = line.split(' ');
    let (Some("GET"), Some(target)) = (parts.next(), parts.next()) else {
        return Callback::Ignore;
    };
    let Some(query) = target.strip_prefix("/callback?") else {
        return Callback::Ignore;
    };
    let (mut code, mut state, mut error) = (None, None, None);
    for pair in query.split('&') {
        let (key, value) = pair.split_once('=').unwrap_or((pair, ""));
        let Some(value) = percent_decode(value) else {
            return Callback::Ignore;
        };
        match key {
            "code" if code.is_none() => code = Some(value),
            "state" if state.is_none() => state = Some(value),
            "error" if error.is_none() => error = Some(value),
            "code" | "state" | "error" => return Callback::Ignore, // duplicated parameter
            _ => {}
        }
    }
    // Constant-time enough for a 128-bit random state compared once per request.
    if state.as_deref() != Some(expected_state) {
        return Callback::Ignore;
    }
    match (code, error) {
        (_, Some(error)) => Callback::Denied(error),
        (Some(code), None) if !code.is_empty() && code.len() <= 4096 => Callback::Code(code),
        _ => Callback::Ignore,
    }
}

async fn respond(stream: &mut tokio::net::TcpStream, status: &str, body: &str) {
    let response = format!(
        "HTTP/1.1 {status}\r\nContent-Type: text/html; charset=utf-8\r\nContent-Length: {}\r\n\
         Cache-Control: no-store\r\nConnection: close\r\n\r\n{body}",
        body.len()
    );
    let _ = stream.write_all(response.as_bytes()).await;
    let _ = stream.shutdown().await;
}

/// Wait for the callback with the expected state on an already bound listener.
pub async fn await_callback(
    listener: &TcpListener,
    expected_state: &str,
) -> Result<String, String> {
    loop {
        let (mut stream, _) = listener
            .accept()
            .await
            .map_err(|e| format!("loopback accept: {e}"))?;
        let mut buffer = vec![0u8; MAX_REQUEST_HEAD];
        let mut read = 0;
        while read < buffer.len() {
            let n = match tokio::time::timeout(
                Duration::from_secs(5),
                stream.read(&mut buffer[read..]),
            )
            .await
            {
                Ok(Ok(n)) => n,
                _ => 0,
            };
            if n == 0 {
                break;
            }
            read += n;
            if buffer[..read].windows(4).any(|w| w == b"\r\n\r\n") {
                break;
            }
        }
        let head = String::from_utf8_lossy(&buffer[..read]);
        match parse_callback(&head, expected_state) {
            Callback::Code(code) => {
                respond(
                    &mut stream,
                    "200 OK",
                    "<!doctype html><title>EIRA</title>\
                    <p>Du er logget ind. Du kan lukke dette vindue.</p>",
                )
                .await;
                return Ok(code);
            }
            Callback::Denied(error) => {
                respond(
                    &mut stream,
                    "200 OK",
                    "<!doctype html><title>EIRA</title>\
                    <p>Login blev afbrudt. Du kan lukke dette vindue.</p>",
                )
                .await;
                return Err(format!("login_denied: {error}"));
            }
            Callback::Ignore => respond(&mut stream, "404 Not Found", "").await,
        }
    }
}

fn open_browser(url: &str) -> bool {
    std::process::Command::new("xdg-open")
        .arg(url)
        .stdin(std::process::Stdio::null())
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::null())
        .spawn()
        .is_ok()
}

fn field<'a>(value: &'a Value, name: &str) -> Result<&'a str, String> {
    value
        .get(name)
        .and_then(Value::as_str)
        .ok_or_else(|| format!("identityd answer lacks {name}"))
}

/// The whole desktop login, as a Tauri command.
#[tauri::command]
pub async fn desktop_login() -> Result<LoginResult, String> {
    let listener = TcpListener::bind(("127.0.0.1", 0))
        .await
        .map_err(|e| format!("loopback bind: {e}"))?;
    let port = listener.local_addr().map_err(|e| e.to_string())?.port();
    let start = crate::ipc::send_ipc_request(
        "identityd".into(),
        "identity.login_start".into(),
        json!({ "redirect_uri": redirect_uri(port) }),
    )
    .await?;
    let url = field(&start, "authorize_url")?;
    let state = field(&start, "state")?.to_owned();
    if !url.starts_with("https://") {
        return Err("identityd returned a non-https authorize URL".into());
    }
    if !open_browser(url) {
        return Err(format!(
            "could not open the browser; open this address yourself: {url}"
        ));
    }
    let code = tokio::time::timeout(LOGIN_TIMEOUT, await_callback(&listener, &state))
        .await
        .map_err(|_| "login_timed_out".to_string())??;
    drop(listener);
    let done = crate::ipc::send_ipc_request(
        "identityd".into(),
        "identity.login_complete".into(),
        json!({ "state": state, "code": code }),
    )
    .await?;
    let session_id = field(&done, "session_id")?.to_owned();
    let consent_key = match done.get("consent_key").and_then(Value::as_str) {
        None => None, // installed system: decisions go through the consent agent
        Some(hex) => Some(
            decode_hex(hex)
                .filter(|key| key.len() == 32)
                .ok_or("identityd returned a malformed consent key")?,
        ),
    };
    *HELD.lock().map_err(|_| "consent key store poisoned")? = Some(Held {
        session_id: session_id.clone(),
        consent_key,
    });
    Ok(LoginResult {
        session_id,
        identity: field(&done, "identity")?.to_owned(),
        expires_at: done
            .get("expires_at")
            .and_then(Value::as_str)
            .map(str::to_owned),
    })
}

fn decode_hex(text: &str) -> Option<Vec<u8>> {
    if text.len() % 2 != 0 {
        return None;
    }
    (0..text.len())
        .step_by(2)
        .map(|i| u8::from_str_radix(text.get(i..i + 2)?, 16).ok())
        .collect()
}

/// HMAC-SHA256 over the same message as app/gate/consent_proof.py.
pub fn consent_proof(
    key: &[u8],
    verb: &str,
    uid: u32,
    session_id: &str,
    action_id: &str,
    content_hash: &str,
    rendering_hash: &str,
) -> Result<String, String> {
    if verb != "consent" && verb != "confirm" && verb != "delegate" {
        return Err(format!("unknown verb {verb}"));
    }
    let uid = uid.to_string();
    let parts = [
        CONSENT_DOMAIN,
        verb,
        &uid,
        session_id,
        action_id,
        content_hash,
        rendering_hash,
    ];
    if parts.iter().any(|part| part.contains('\0')) {
        return Err("NUL in consent proof field".into());
    }
    let mut mac = Hmac::<Sha256>::new_from_slice(key).map_err(|e| e.to_string())?;
    mac.update(parts.join("\0").as_bytes());
    Ok(mac
        .finalize()
        .into_bytes()
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect())
}

/// The held session id and a proof for one decision, made with the held key.
fn sign(
    verb: &str,
    action_id: &str,
    content_hash: &str,
    rendering_hash: &str,
) -> Result<(String, String), String> {
    let held = HELD.lock().map_err(|_| "consent key store poisoned")?;
    let held = held.as_ref().ok_or("not logged in")?;
    let key = held
        .consent_key
        .as_ref()
        .ok_or("decisions go through the consent agent")?;
    #[cfg(unix)]
    // SAFETY: getuid has no preconditions and cannot fail.
    let uid = unsafe { libc::getuid() };
    #[cfg(not(unix))]
    let uid: u32 = return Err("the trusted consent path needs a Unix user id".into());
    let proof = consent_proof(
        key,
        verb,
        uid,
        &held.session_id,
        action_id,
        content_hash,
        rendering_hash,
    )?;
    Ok((held.session_id.clone(), proof))
}

/// Whether this app holds the key (development machine) or the consent
/// agent decides (installed system).
fn agent_decides() -> Result<bool, String> {
    let held = HELD.lock().map_err(|_| "consent key store poisoned")?;
    Ok(held.as_ref().ok_or("not logged in")?.consent_key.is_none())
}

/// Asks the consent agent to show a decision. The app passes only the id:
/// the agent reads the text from the gate or delegationd, shows it on its
/// own window and signs only what the user approves there.
#[cfg(unix)]
async fn ask_agent(method: &str, params: Value) -> Result<Value, String> {
    use tokio::io::AsyncBufReadExt;
    let dir = std::env::var("XDG_RUNTIME_DIR").map_err(|_| "XDG_RUNTIME_DIR is not set")?;
    let path = std::path::Path::new(&dir).join("eira-consent.sock");
    let mut stream = tokio::net::UnixStream::connect(&path)
        .await
        .map_err(|_| "E_CONSENT_AGENT_UNAVAILABLE: samtykkevinduet kører ikke")?;
    let request = json!({"jsonrpc": "2.0", "id": 1, "method": method, "params": params});
    stream
        .write_all(format!("{request}\n").as_bytes())
        .await
        .map_err(|e| e.to_string())?;
    let mut line = String::new();
    // The user decides in the agent's window; give them time.
    tokio::time::timeout(
        Duration::from_secs(600),
        tokio::io::BufReader::new(stream).read_line(&mut line),
    )
    .await
    .map_err(|_| "the consent agent did not answer")?
    .map_err(|e| e.to_string())?;
    let reply: Value = serde_json::from_str(&line).map_err(|e| e.to_string())?;
    reply
        .get("result")
        .cloned()
        .ok_or_else(|| "no result from the consent agent".into())
}

#[cfg(not(unix))]
async fn ask_agent(_method: &str, _params: Value) -> Result<Value, String> {
    Err("the consent agent needs Unix".into())
}

/// One decision from the user, signed with the held key and sent to the gate.
async fn decide(
    verb: &str,
    action_id: String,
    content_hash: String,
    rendering_hash: String,
) -> Result<Value, String> {
    if agent_decides()? {
        // The agent shows the gate's own text and decides consent and the
        // confirmation together, so both commands go to the same place.
        let _ = (content_hash, rendering_hash);
        return ask_agent("agent.show", json!({ "action_id": action_id })).await;
    }
    let (session_id, proof) = sign(verb, &action_id, &content_hash, &rendering_hash)?;
    crate::ipc::send_ipc_request(
        "intentd".into(),
        format!("gate.{verb}"),
        json!({
            "action_id": action_id,
            "content_hash": content_hash,
            "rendering_hash": rendering_hash,
            "session_id": session_id,
            "proof": proof,
        }),
    )
    .await
}

/// The user lets the model prepare actions on their behalf, exactly as the
/// shown text says (EIRA-DELEGATION-1.0). Same trusted path as consent: only
/// this process holds the key, so no other program can delegate.
#[tauri::command]
pub async fn delegation_create(
    proposal_id: String,
    content_hash: String,
    rendering_hash: String,
) -> Result<Value, String> {
    if agent_decides()? {
        return ask_agent(
            "agent.show_delegation",
            json!({ "proposal_id": proposal_id }),
        )
        .await;
    }
    let (session_id, proof) = sign("delegate", &proposal_id, &content_hash, &rendering_hash)?;
    crate::ipc::send_ipc_request(
        "delegationd".into(),
        "delegation.create".into(),
        json!({
            "proposal_id": proposal_id,
            "content_hash": content_hash,
            "rendering_hash": rendering_hash,
            "session_id": session_id,
            "proof": proof,
        }),
    )
    .await
}

/// The user consents to exactly this action and this rendering.
#[tauri::command]
pub async fn gate_consent(
    action_id: String,
    content_hash: String,
    rendering_hash: String,
) -> Result<Value, String> {
    decide("consent", action_id, content_hash, rendering_hash).await
}

/// The user confirms the consented action; the gate executes it.
#[tauri::command]
pub async fn gate_confirm(
    action_id: String,
    content_hash: String,
    rendering_hash: String,
) -> Result<Value, String> {
    decide("confirm", action_id, content_hash, rendering_hash).await
}

/// Logging out forgets the key: nothing more can be signed.
#[tauri::command]
pub fn desktop_logout() {
    if let Ok(mut held) = HELD.lock() {
        *held = None;
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use tokio::io::AsyncReadExt;
    use tokio::net::TcpStream;

    const STATE: &str = "s-0123456789abcdef";

    #[test]
    fn accepts_only_the_expected_callback() {
        let ok = format!("GET /callback?code=abc%2Fdef&state={STATE} HTTP/1.1\r\nHost: x\r\n\r\n");
        assert_eq!(parse_callback(&ok, STATE), Callback::Code("abc/def".into()));
        let wrong_state = "GET /callback?code=abc&state=other HTTP/1.1\r\n\r\n";
        assert_eq!(parse_callback(wrong_state, STATE), Callback::Ignore);
        let no_state = "GET /callback?code=abc HTTP/1.1\r\n\r\n";
        assert_eq!(parse_callback(no_state, STATE), Callback::Ignore);
        let favicon = "GET /favicon.ico HTTP/1.1\r\n\r\n";
        assert_eq!(parse_callback(favicon, STATE), Callback::Ignore);
        let post = format!("POST /callback?code=abc&state={STATE} HTTP/1.1\r\n\r\n");
        assert_eq!(parse_callback(&post, STATE), Callback::Ignore);
        let twice = format!("GET /callback?code=a&code=b&state={STATE} HTTP/1.1\r\n\r\n");
        assert_eq!(parse_callback(&twice, STATE), Callback::Ignore);
        let bad_escape = format!("GET /callback?code=%zz&state={STATE} HTTP/1.1\r\n\r\n");
        assert_eq!(parse_callback(&bad_escape, STATE), Callback::Ignore);
    }

    #[test]
    fn reports_a_denied_login_only_with_the_right_state() {
        let denied = format!("GET /callback?error=access_denied&state={STATE} HTTP/1.1\r\n\r\n");
        assert_eq!(
            parse_callback(&denied, STATE),
            Callback::Denied("access_denied".into())
        );
        let foreign = "GET /callback?error=access_denied&state=nope HTTP/1.1\r\n\r\n";
        assert_eq!(parse_callback(foreign, STATE), Callback::Ignore);
    }

    #[test]
    fn consent_proof_matches_the_python_gate() {
        let raw = include_str!("../../../tests/vectors/consent-proof.json");
        let vectors: Value = serde_json::from_str(raw).unwrap();
        for case in vectors["cases"].as_array().unwrap() {
            let key = decode_hex(case["key"].as_str().unwrap()).unwrap();
            let proof = consent_proof(
                &key,
                case["verb"].as_str().unwrap(),
                case["uid"].as_u64().unwrap() as u32,
                case["session_id"].as_str().unwrap(),
                case["action_id"].as_str().unwrap(),
                case["content_hash"].as_str().unwrap(),
                case["rendering_hash"].as_str().unwrap(),
            )
            .unwrap();
            assert_eq!(proof, case["proof"].as_str().unwrap());
        }
    }

    #[test]
    fn consent_proof_refuses_other_verbs_and_nul() {
        let key = [0x11u8; 32];
        assert!(consent_proof(&key, "delete", 1, "s", "a", "c", "r").is_err());
        assert!(consent_proof(&key, "consent", 1, "s\0x", "a", "c", "r").is_err());
        assert_eq!(decode_hex("0g"), None);
        assert_eq!(decode_hex("abc"), None);
    }

    #[test]
    fn redirect_is_the_ipv4_loopback_callback() {
        assert_eq!(redirect_uri(49152), "http://127.0.0.1:49152/callback");
    }

    async fn get(port: u16, path: &str) -> String {
        let mut stream = TcpStream::connect(("127.0.0.1", port)).await.unwrap();
        stream
            .write_all(format!("GET {path} HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n").as_bytes())
            .await
            .unwrap();
        let mut out = String::new();
        stream.read_to_string(&mut out).await.unwrap();
        out
    }

    #[tokio::test]
    async fn waits_past_probes_and_returns_the_code() {
        let listener = TcpListener::bind(("127.0.0.1", 0)).await.unwrap();
        let port = listener.local_addr().unwrap().port();
        let waiter = tokio::spawn(async move { await_callback(&listener, STATE).await });
        assert!(get(port, "/favicon.ico").await.starts_with("HTTP/1.1 404"));
        assert!(
            get(port, "/callback?code=stolen&state=guess")
                .await
                .starts_with("HTTP/1.1 404")
        );
        let page = get(port, &format!("/callback?code=the-code&state={STATE}")).await;
        assert!(page.starts_with("HTTP/1.1 200") && page.contains("logget ind"));
        assert_eq!(waiter.await.unwrap(), Ok("the-code".to_string()));
    }

    #[tokio::test]
    async fn a_denied_login_ends_the_wait() {
        let listener = TcpListener::bind(("127.0.0.1", 0)).await.unwrap();
        let port = listener.local_addr().unwrap().port();
        let waiter = tokio::spawn(async move { await_callback(&listener, STATE).await });
        get(
            port,
            &format!("/callback?error=access_denied&state={STATE}"),
        )
        .await;
        assert_eq!(
            waiter.await.unwrap(),
            Err("login_denied: access_denied".to_string())
        );
    }
}
