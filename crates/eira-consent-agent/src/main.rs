//! eira-consent-agent (EIRA-CONSENT-AGENT 0.2).
//!
//! Installed `root:eira-consent 2755`. The only process the gate takes
//! consent and confirmation from. It holds the session's consent key, shows
//! the gate's own text on the session's compositor, and signs only what the
//! user approved there. The app can ask it to show an action, nothing else.

use eira_consent_agent::{agent, hygiene, rpc, ui};

use serde_json::{Value, json};
use std::io::{BufRead, BufReader, Read, Write};
use std::os::unix::fs::PermissionsExt;
use std::os::unix::net::{UnixListener, UnixStream};
use std::path::{Path, PathBuf};
use std::process::ExitCode;

struct Daemons {
    run_dir: PathBuf,
    token: String,
}

impl agent::Daemons for Daemons {
    fn claim_key(&mut self) -> Result<Value, String> {
        rpc::call(
            &self.run_dir.join("identityd.sock"),
            &self.token,
            "identity.consent_key_claim",
            json!({}),
        )
        .map_err(|e| e.to_string())
    }
    fn gate(&mut self, method: &str, params: Value) -> Result<Value, String> {
        rpc::call(
            &self.run_dir.join("intentd.sock"),
            &self.token,
            method,
            params,
        )
        .map_err(|e| e.to_string())
    }
    fn delegation(&mut self, method: &str, params: Value) -> Result<Value, String> {
        rpc::call(
            &self.run_dir.join("delegationd.sock"),
            &self.token,
            method,
            params,
        )
        .map_err(|e| e.to_string())
    }
}

/// The compositor at the other end of the Wayland socket (SO_PEERCRED).
fn peer_pid(stream: &UnixStream) -> Option<i32> {
    use std::os::fd::AsRawFd;
    let mut cred = libc::ucred {
        pid: 0,
        uid: 0,
        gid: 0,
    };
    let mut len = std::mem::size_of::<libc::ucred>() as libc::socklen_t;
    // SAFETY: valid fd, buffer and length for SO_PEERCRED.
    let rc = unsafe {
        libc::getsockopt(
            stream.as_raw_fd(),
            libc::SOL_SOCKET,
            libc::SO_PEERCRED,
            (&mut cred as *mut libc::ucred).cast(),
            &mut len,
        )
    };
    (rc == 0 && cred.pid > 0).then_some(cred.pid)
}

fn listen(path: &Path) -> std::io::Result<UnixListener> {
    use std::os::unix::fs::FileTypeExt;
    if let Ok(meta) = std::fs::symlink_metadata(path) {
        if !meta.file_type().is_socket() {
            return Err(std::io::Error::other("agent socket path is not a socket"));
        }
        std::fs::remove_file(path)?;
    }
    let listener = UnixListener::bind(path)?;
    std::fs::set_permissions(path, std::fs::Permissions::from_mode(0o600))?;
    Ok(listener)
}

fn serve(conn: UnixStream, daemons: &mut Daemons, screen: &mut ui::WaylandScreen, uid: u32) {
    let mut line = String::new();
    if BufReader::new(&conn).take_line(&mut line).is_err() {
        return;
    }
    let request: Value = serde_json::from_str(&line).unwrap_or(Value::Null);
    let id = request.get("id").cloned().unwrap_or(Value::Null);
    let result = match request["method"].as_str() {
        Some("agent.status") => json!({"ok": true}),
        // Only an action id: the agent never takes text, hashes or proofs from the app.
        Some("agent.show") => match request["params"]["action_id"].as_str() {
            Some(action_id) => agent::show(action_id, uid, daemons, screen),
            None => json!({"status": "error", "error": "action_id is required"}),
        },
        Some("agent.show_delegation") => match request["params"]["proposal_id"].as_str() {
            Some(proposal_id) => agent::show_delegation(proposal_id, uid, daemons, screen),
            None => json!({"status": "error", "error": "proposal_id is required"}),
        },
        _ => json!({"status": "error", "error": "unknown method"}),
    };
    let reply = json!({"jsonrpc": "2.0", "id": id, "result": result});
    let _ = (&conn).write_all((reply.to_string() + "\n").as_bytes());
}

trait TakeLine {
    fn take_line(&mut self, buf: &mut String) -> std::io::Result<usize>;
}

impl<R: BufRead> TakeLine for R {
    /// At most 4 KiB: an action id is short.
    fn take_line(&mut self, buf: &mut String) -> std::io::Result<usize> {
        let mut limited = std::io::Read::by_ref(self).take(4096);
        limited.read_line(buf)
    }
}

fn main() -> ExitCode {
    hygiene::close_inherited_fds();
    hygiene::not_dumpable();
    match hygiene::check_args(std::env::args()) {
        Ok(true) => {
            println!("eira-consent-agent {}", env!("CARGO_PKG_VERSION"));
            return ExitCode::SUCCESS;
        }
        Ok(false) => {}
        Err(_) => {
            eprintln!("eira-consent-agent: takes no arguments");
            return ExitCode::from(64);
        }
    }
    if hygiene::require_setgid().is_err() {
        eprintln!(
            "eira-consent-agent: must run as installed (setgid {})",
            hygiene::CONSENT_GROUP
        );
        return ExitCode::from(77);
    }
    let uid = hygiene::real_uid();
    let env = match hygiene::read_environment(
        hygiene::env(c"XDG_RUNTIME_DIR").as_deref(),
        hygiene::env(c"WAYLAND_DISPLAY").as_deref(),
        uid,
    ) {
        Ok(env) => env,
        Err(error) => {
            eprintln!("eira-consent-agent: {error:?}");
            return ExitCode::from(78);
        }
    };
    if hygiene::check_runtime_dir(&env.runtime_dir, uid).is_err() {
        eprintln!("eira-consent-agent: runtime dir is not private");
        return ExitCode::from(78);
    }
    let Ok(stream) = UnixStream::connect(&env.wayland_socket) else {
        eprintln!("eira-consent-agent: no Wayland compositor");
        return ExitCode::from(69);
    };
    let Some(compositor) = peer_pid(&stream) else {
        return ExitCode::from(69);
    };
    let Ok(conn) = wayland_client::Connection::from_socket(stream) else {
        return ExitCode::from(69);
    };
    let mut daemons = Daemons {
        run_dir: PathBuf::from(rpc::RUN_DIR),
        token: rpc::ipc_token(Path::new(rpc::CONF)),
    };
    // §5.2: identityd decides whether this is the session's compositor.
    if let Err(error) = rpc::call(
        &daemons.run_dir.join("identityd.sock"),
        &daemons.token,
        "identity.consent_agent_register",
        json!({"compositor_pid": compositor}),
    ) {
        eprintln!("eira-consent-agent: not registered: {error}");
        return ExitCode::from(77);
    }
    let Ok(listener) = listen(&env.runtime_dir.join("eira-consent.sock")) else {
        return ExitCode::from(73);
    };
    let mut screen = ui::WaylandScreen::new(conn);
    // One request at a time: one dialog at a time.
    for conn in listener.incoming().flatten() {
        serve(conn, &mut daemons, &mut screen, uid);
    }
    ExitCode::SUCCESS
}
