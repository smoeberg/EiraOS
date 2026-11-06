//! Eira Terminal — a real Linux terminal for the EiraOS shell (SYS-TERM-01).
//!
//! Each session owns a PTY and the logged-in user's configured shell, started
//! as that (non-root) user in their home directory. Output is streamed to the
//! owning window as events; input, resize, allowlisted signals and close are
//! typed commands. Sessions are bound to the window that created them, bounded
//! in number and frame size, and their process group is always cleaned up.
//!
//! This is deliberately *not* a command-execution API: the frontend can only
//! talk to a shell it opened, with the user's normal Linux permissions.
//! See docs/architecture/eira-terminal.md.

use portable_pty::{Child, CommandBuilder, MasterPty, PtySize, native_pty_system};
use serde::Serialize;
use std::collections::HashMap;
use std::io::{Read, Write};
use std::path::PathBuf;
use std::sync::atomic::{AtomicU32, Ordering};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

pub const MAX_SESSIONS: usize = 8;
pub const MAX_WRITE_BYTES: usize = 64 * 1024;
pub const MAX_COLS: u16 = 1000;
pub const MAX_ROWS: u16 = 500;
const READ_CHUNK: usize = 16 * 1024;
const CLOSE_GRACE: Duration = Duration::from_secs(2);

/// Where session output goes. The Tauri implementation emits window events;
/// tests collect into channels.
pub trait TerminalSink: Send + Sync + 'static {
    fn output(&self, owner: &str, session_id: u32, data: String);
    fn exit(&self, owner: &str, session_id: u32, code: Option<i32>);
}

#[derive(Debug, Clone, Serialize, PartialEq, Eq)]
pub struct SessionInfo {
    pub session_id: u32,
    pub shell: String,
    pub cwd: String,
    pub pid: Option<u32>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum TerminalError {
    InvalidArgument(String),
    NotFound,
    Limit,
    RootRefused,
    Spawn(String),
    Io(String),
}

impl std::fmt::Display for TerminalError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::InvalidArgument(message) => write!(f, "invalid_argument: {message}"),
            Self::NotFound => write!(f, "not_found: terminal session does not exist"),
            Self::Limit => write!(f, "limit: at most {MAX_SESSIONS} terminal sessions"),
            Self::RootRefused => write!(f, "permission_denied: the terminal never runs as root"),
            Self::Spawn(message) => write!(f, "spawn_failed: {message}"),
            Self::Io(message) => write!(f, "io_error: {message}"),
        }
    }
}

/// Signals the frontend may send. Ctrl+C/Ctrl+D normally travel as bytes
/// through the PTY; this is for explicit "interrupt/terminate" UI actions.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum AllowedSignal {
    Interrupt,
    Terminate,
    Hangup,
}

impl AllowedSignal {
    pub fn parse(name: &str) -> Result<Self, TerminalError> {
        match name {
            "SIGINT" => Ok(Self::Interrupt),
            "SIGTERM" => Ok(Self::Terminate),
            "SIGHUP" => Ok(Self::Hangup),
            other => Err(TerminalError::InvalidArgument(format!(
                "signal {other:?} is not allowed (SIGINT, SIGTERM, SIGHUP)"
            ))),
        }
    }

    fn raw(self) -> libc::c_int {
        match self {
            Self::Interrupt => libc::SIGINT,
            Self::Terminate => libc::SIGTERM,
            Self::Hangup => libc::SIGHUP,
        }
    }
}

/// Which shell to start, as whom, where.
#[derive(Debug, Clone)]
pub struct ShellProfile {
    pub shell: PathBuf,
    pub cwd: PathBuf,
}

impl ShellProfile {
    /// The logged-in user's login shell and home directory from the passwd
    /// database (falling back to $SHELL/$HOME, then /bin/bash and /).
    pub fn for_current_user() -> Result<Self, TerminalError> {
        // SAFETY: geteuid has no preconditions.
        let euid = unsafe { libc::geteuid() };
        if euid == 0 {
            return Err(TerminalError::RootRefused);
        }
        let (mut shell, mut home) = (None, None);
        // SAFETY: getpwuid returns a pointer into static storage or null; the
        // fields are copied out immediately and nothing else here calls it.
        unsafe {
            let entry = libc::getpwuid(euid);
            if !entry.is_null() {
                let to_path = |ptr: *const libc::c_char| {
                    (!ptr.is_null())
                        .then(|| std::ffi::CStr::from_ptr(ptr).to_string_lossy().into_owned())
                        .filter(|value| !value.is_empty())
                        .map(PathBuf::from)
                };
                shell = to_path((*entry).pw_shell);
                home = to_path((*entry).pw_dir);
            }
        }
        let shell = shell
            .or_else(|| std::env::var_os("SHELL").map(PathBuf::from))
            .filter(|path| path.is_absolute() && path.exists())
            .unwrap_or_else(|| PathBuf::from("/bin/bash"));
        let cwd = home
            .or_else(|| std::env::var_os("HOME").map(PathBuf::from))
            .filter(|path| path.is_dir())
            .unwrap_or_else(|| PathBuf::from("/"));
        Ok(Self { shell, cwd })
    }
}

struct Session {
    owner: String,
    master: Box<dyn MasterPty + Send>,
    writer: Box<dyn Write + Send>,
    child: Box<dyn Child + Send + Sync>,
}

impl Session {
    fn pid(&self) -> Option<u32> {
        self.child.process_id()
    }

    fn signal_group(&self, signal: libc::c_int) {
        if let Some(pid) = self.pid() {
            // portable-pty starts the shell with setsid(), so the shell's pid
            // is also its process-group id; signal the whole job tree.
            // SAFETY: killpg only takes integer arguments.
            unsafe {
                libc::killpg(pid as libc::pid_t, signal);
            }
        }
    }
}

/// Incremental UTF-8 decoder: keeps an incomplete trailing sequence for the
/// next chunk instead of turning split characters into U+FFFD.
#[derive(Default)]
pub struct Utf8Stream {
    pending: Vec<u8>,
}

impl Utf8Stream {
    pub fn push(&mut self, bytes: &[u8]) -> String {
        self.pending.extend_from_slice(bytes);
        let valid_up_to = match std::str::from_utf8(&self.pending) {
            Ok(_) => self.pending.len(),
            Err(error) => match error.error_len() {
                // Invalid bytes in the middle: decode lossily up to the end.
                Some(_) => self.pending.len(),
                // Incomplete sequence at the end: keep at most 3 bytes.
                None => error.valid_up_to(),
            },
        };
        let rest = self.pending.split_off(valid_up_to);
        let text = String::from_utf8_lossy(&self.pending).into_owned();
        self.pending = rest;
        text
    }
}

pub struct TerminalManager {
    sessions: Arc<Mutex<HashMap<u32, Session>>>,
    next_id: AtomicU32,
    sink: Arc<dyn TerminalSink>,
}

impl TerminalManager {
    pub fn new(sink: Arc<dyn TerminalSink>) -> Self {
        Self {
            sessions: Arc::new(Mutex::new(HashMap::new())),
            next_id: AtomicU32::new(1),
            sink,
        }
    }

    fn lock(&self) -> std::sync::MutexGuard<'_, HashMap<u32, Session>> {
        self.sessions
            .lock()
            .unwrap_or_else(std::sync::PoisonError::into_inner)
    }

    pub fn session_count(&self) -> usize {
        self.lock().len()
    }

    pub fn create(
        &self,
        owner: &str,
        profile: &ShellProfile,
        cols: u16,
        rows: u16,
    ) -> Result<SessionInfo, TerminalError> {
        validate_size(cols, rows)?;
        if self.session_count() >= MAX_SESSIONS {
            return Err(TerminalError::Limit);
        }

        let pty = native_pty_system()
            .openpty(PtySize {
                rows,
                cols,
                pixel_width: 0,
                pixel_height: 0,
            })
            .map_err(|error| TerminalError::Spawn(format!("could not open a PTY: {error}")))?;

        let mut command = CommandBuilder::new(&profile.shell);
        command.cwd(&profile.cwd);
        command.env("TERM", "xterm-256color");
        command.env("COLORTERM", "truecolor");
        command.env("EIRA_TERMINAL", "1");
        let child = pty
            .slave
            .spawn_command(command)
            .map_err(|error| TerminalError::Spawn(format!("could not start the shell: {error}")))?;
        // The child holds its own copy of the slave side.
        drop(pty.slave);

        let reader = pty
            .master
            .try_clone_reader()
            .map_err(|error| TerminalError::Io(error.to_string()))?;
        let writer = pty
            .master
            .take_writer()
            .map_err(|error| TerminalError::Io(error.to_string()))?;

        let session_id = self.next_id.fetch_add(1, Ordering::Relaxed);
        let session = Session {
            owner: owner.to_owned(),
            master: pty.master,
            writer,
            child,
        };
        let pid = session.pid();
        self.lock().insert(session_id, session);
        self.spawn_reader(owner.to_owned(), session_id, reader);

        Ok(SessionInfo {
            session_id,
            shell: profile.shell.display().to_string(),
            cwd: profile.cwd.display().to_string(),
            pid,
        })
    }

    fn spawn_reader(&self, owner: String, session_id: u32, mut reader: Box<dyn Read + Send>) {
        let sessions = Arc::clone(&self.sessions);
        let sink = Arc::clone(&self.sink);
        std::thread::Builder::new()
            .name(format!("eira-terminal-{session_id}"))
            .spawn(move || {
                let mut decoder = Utf8Stream::default();
                let mut buffer = vec![0u8; READ_CHUNK];
                loop {
                    match reader.read(&mut buffer) {
                        Ok(0) | Err(_) => break,
                        Ok(read) => {
                            let text = decoder.push(&buffer[..read]);
                            if !text.is_empty() {
                                sink.output(&owner, session_id, text);
                            }
                        }
                    }
                }
                // EOF: the shell (and everything holding the PTY) has exited.
                let session = sessions
                    .lock()
                    .unwrap_or_else(std::sync::PoisonError::into_inner)
                    .remove(&session_id);
                let code = session.and_then(|mut session| {
                    session
                        .child
                        .wait()
                        .ok()
                        .map(|status| status.exit_code() as i32)
                });
                sink.exit(&owner, session_id, code);
            })
            .expect("spawn terminal reader thread");
    }

    pub fn write(&self, owner: &str, session_id: u32, data: &str) -> Result<(), TerminalError> {
        if data.len() > MAX_WRITE_BYTES {
            return Err(TerminalError::InvalidArgument(format!(
                "input frame exceeds {MAX_WRITE_BYTES} bytes"
            )));
        }
        let mut sessions = self.lock();
        let session = owned(&mut sessions, owner, session_id)?;
        session
            .writer
            .write_all(data.as_bytes())
            .and_then(|()| session.writer.flush())
            .map_err(|error| TerminalError::Io(error.to_string()))
    }

    pub fn resize(
        &self,
        owner: &str,
        session_id: u32,
        cols: u16,
        rows: u16,
    ) -> Result<(), TerminalError> {
        validate_size(cols, rows)?;
        let mut sessions = self.lock();
        let session = owned(&mut sessions, owner, session_id)?;
        session
            .master
            .resize(PtySize {
                rows,
                cols,
                pixel_width: 0,
                pixel_height: 0,
            })
            .map_err(|error| TerminalError::Io(error.to_string()))
    }

    pub fn signal(
        &self,
        owner: &str,
        session_id: u32,
        signal: AllowedSignal,
    ) -> Result<(), TerminalError> {
        let mut sessions = self.lock();
        owned(&mut sessions, owner, session_id)?.signal_group(signal.raw());
        Ok(())
    }

    /// Hang up the shell's process group, wait briefly, then kill it.
    pub fn close(&self, owner: &str, session_id: u32) -> Result<(), TerminalError> {
        let mut session = {
            let mut sessions = self.lock();
            owned(&mut sessions, owner, session_id)?;
            sessions
                .remove(&session_id)
                .ok_or(TerminalError::NotFound)?
        };
        terminate(&mut session);
        Ok(())
    }

    /// Close every session a window owns (window closed or reloaded).
    pub fn close_owner(&self, owner: &str) {
        let ids: Vec<u32> = self
            .lock()
            .iter()
            .filter(|(_, session)| session.owner == owner)
            .map(|(id, _)| *id)
            .collect();
        for id in ids {
            let _ = self.close(owner, id);
        }
    }
}

impl Drop for TerminalManager {
    fn drop(&mut self) {
        let sessions: Vec<Session> = self.lock().drain().map(|(_, session)| session).collect();
        for mut session in sessions {
            terminate(&mut session);
        }
    }
}

fn owned<'a>(
    sessions: &'a mut HashMap<u32, Session>,
    owner: &str,
    session_id: u32,
) -> Result<&'a mut Session, TerminalError> {
    match sessions.get_mut(&session_id) {
        // Another window's session is reported exactly like a missing one.
        Some(session) if session.owner == owner => Ok(session),
        _ => Err(TerminalError::NotFound),
    }
}

/// Every process in the terminal's session (the shell is the session leader,
/// so its pid is the session id). Interactive shells put background jobs in
/// their own process groups, so signalling the shell's group is not enough.
fn session_members(sid: u32) -> Vec<libc::pid_t> {
    let Ok(entries) = std::fs::read_dir("/proc") else {
        return Vec::new();
    };
    entries
        .filter_map(|entry| {
            entry
                .ok()?
                .file_name()
                .to_str()?
                .parse::<libc::pid_t>()
                .ok()
        })
        .filter(|pid| {
            std::fs::read_to_string(format!("/proc/{pid}/stat"))
                .ok()
                // Fields after the parenthesised command name:
                // state ppid pgrp session ...
                .and_then(|stat| stat.rsplit_once(')').map(|(_, rest)| rest.to_owned()))
                .and_then(|rest| rest.split_whitespace().nth(3)?.parse::<u32>().ok())
                == Some(sid)
        })
        .collect()
}

fn signal_session(session: &Session, signal: libc::c_int) {
    session.signal_group(signal);
    if let Some(sid) = session.pid() {
        for pid in session_members(sid) {
            // SAFETY: kill only takes integer arguments.
            unsafe {
                libc::kill(pid, signal);
            }
        }
    }
}

/// Closing a terminal ends everything started in it: hang up the session,
/// give it a moment to exit cleanly, then kill what is left.
fn terminate(session: &mut Session) {
    signal_session(session, libc::SIGHUP);
    let deadline = Instant::now() + CLOSE_GRACE;
    let mut shell_exited = false;
    while Instant::now() < deadline {
        if !shell_exited && matches!(session.child.try_wait(), Ok(Some(_))) {
            shell_exited = true;
        }
        if shell_exited
            && session
                .pid()
                .is_none_or(|sid| session_members(sid).is_empty())
        {
            return;
        }
        std::thread::sleep(Duration::from_millis(25));
    }
    signal_session(session, libc::SIGKILL);
    let _ = session.child.kill();
    let _ = session.child.wait();
}

fn validate_size(cols: u16, rows: u16) -> Result<(), TerminalError> {
    if (1..=MAX_COLS).contains(&cols) && (1..=MAX_ROWS).contains(&rows) {
        Ok(())
    } else {
        Err(TerminalError::InvalidArgument(format!(
            "terminal size must be 1..={MAX_COLS} columns and 1..={MAX_ROWS} rows"
        )))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::mpsc::{Receiver, Sender, channel};

    enum Event {
        Output(u32, String),
        Exit(u32, Option<i32>),
    }

    struct ChannelSink(Mutex<Sender<Event>>);

    impl TerminalSink for ChannelSink {
        fn output(&self, _owner: &str, id: u32, data: String) {
            let _ = self.0.lock().unwrap().send(Event::Output(id, data));
        }
        fn exit(&self, _owner: &str, id: u32, code: Option<i32>) {
            let _ = self.0.lock().unwrap().send(Event::Exit(id, code));
        }
    }

    fn manager() -> (TerminalManager, Receiver<Event>) {
        let (tx, rx) = channel();
        (
            TerminalManager::new(Arc::new(ChannelSink(Mutex::new(tx)))),
            rx,
        )
    }

    fn sh() -> ShellProfile {
        ShellProfile {
            shell: PathBuf::from("/bin/sh"),
            cwd: std::env::temp_dir(),
        }
    }

    /// Collect output until `needle` appears (or the session exits / times out).
    fn read_until(rx: &Receiver<Event>, id: u32, needle: &str) -> (String, Option<Option<i32>>) {
        let mut text = String::new();
        let deadline = Instant::now() + Duration::from_secs(10);
        while Instant::now() < deadline {
            match rx.recv_timeout(Duration::from_millis(200)) {
                Ok(Event::Output(sid, data)) if sid == id => {
                    text.push_str(&data);
                    if text.contains(needle) {
                        return (text, None);
                    }
                }
                Ok(Event::Exit(sid, code)) if sid == id => return (text, Some(code)),
                _ => {}
            }
        }
        (text, None)
    }

    #[test]
    fn utf8_stream_keeps_split_characters_intact() {
        let mut stream = Utf8Stream::default();
        let bytes = "æøå ✓".as_bytes();
        let mut out = String::new();
        for byte in bytes {
            out.push_str(&stream.push(std::slice::from_ref(byte)));
        }
        assert_eq!(out, "æøå ✓");
        assert_eq!(stream.push(&[0xff, b'a']), "\u{fffd}a");
    }

    #[test]
    fn runs_commands_in_a_real_shell_with_unicode_and_cwd() {
        let (manager, rx) = manager();
        let info = manager.create("main", &sh(), 80, 24).unwrap();
        assert!(info.pid.is_some());
        manager
            .write(
                "main",
                info.session_id,
                "printf 'pwd=%s\\n' \"$(pwd)\"; echo 'blåbærgrød ✓'; echo TERM=$TERM\n",
            )
            .unwrap();
        let (text, _) = read_until(&rx, info.session_id, "TERM=xterm-256color");
        assert!(text.contains("blåbærgrød ✓"), "{text}");
        assert!(
            text.contains(&format!("pwd={}", std::env::temp_dir().display())),
            "{text}"
        );
        manager.close("main", info.session_id).unwrap();
    }

    #[test]
    fn reports_exit_code_and_removes_the_session() {
        let (manager, rx) = manager();
        let info = manager.create("main", &sh(), 80, 24).unwrap();
        manager.write("main", info.session_id, "exit 7\n").unwrap();
        let (_, exit) = read_until(&rx, info.session_id, "\u{0}never");
        assert_eq!(exit, Some(Some(7)));
        assert_eq!(manager.session_count(), 0);
        assert_eq!(
            manager.write("main", info.session_id, "x"),
            Err(TerminalError::NotFound)
        );
    }

    #[test]
    fn ctrl_d_ends_the_shell() {
        let (manager, rx) = manager();
        let info = manager.create("main", &sh(), 80, 24).unwrap();
        manager.write("main", info.session_id, "\u{4}").unwrap();
        let (_, exit) = read_until(&rx, info.session_id, "\u{0}never");
        assert_eq!(exit, Some(Some(0)));
    }

    #[test]
    fn ctrl_c_interrupts_the_foreground_program() {
        let (manager, rx) = manager();
        let info = manager.create("main", &sh(), 80, 24).unwrap();
        manager
            .write("main", info.session_id, "sleep 30; echo after-sleep\n")
            .unwrap();
        std::thread::sleep(Duration::from_millis(300));
        let started = Instant::now();
        manager.write("main", info.session_id, "\u{3}").unwrap();
        // Split the word so the PTY's echo of the command line cannot match.
        manager
            .write("main", info.session_id, "echo inter\"\"rupted\n")
            .unwrap();
        let (text, _) = read_until(&rx, info.session_id, "interrupted\r\n");
        assert!(text.contains("interrupted"), "{text}");
        assert!(started.elapsed() < Duration::from_secs(10), "{text:?}");
        manager.close("main", info.session_id).unwrap();
    }

    #[test]
    fn resize_reaches_the_pty() {
        let (manager, rx) = manager();
        let info = manager.create("main", &sh(), 80, 24).unwrap();
        manager.resize("main", info.session_id, 132, 43).unwrap();
        manager
            .write("main", info.session_id, "stty size\n")
            .unwrap();
        let (text, _) = read_until(&rx, info.session_id, "43 132");
        assert!(text.contains("43 132"), "{text}");
        manager.close("main", info.session_id).unwrap();
    }

    #[test]
    fn sessions_are_bound_to_their_window() {
        let (manager, _rx) = manager();
        let info = manager.create("main", &sh(), 80, 24).unwrap();
        assert_eq!(
            manager.write("other", info.session_id, "id\n"),
            Err(TerminalError::NotFound)
        );
        assert_eq!(
            manager.resize("other", info.session_id, 10, 10),
            Err(TerminalError::NotFound)
        );
        assert_eq!(
            manager.signal("other", info.session_id, AllowedSignal::Interrupt),
            Err(TerminalError::NotFound)
        );
        assert_eq!(
            manager.close("other", info.session_id),
            Err(TerminalError::NotFound)
        );
        assert_eq!(manager.session_count(), 1);
        manager.close_owner("main");
        assert_eq!(manager.session_count(), 0);
    }

    #[test]
    fn close_kills_the_whole_process_group() {
        let (manager, rx) = manager();
        let info = manager.create("main", &sh(), 80, 24).unwrap();
        // A background job that ignores SIGHUP must still be gone after close.
        manager
            .write(
                "main",
                info.session_id,
                "trap '' HUP; sleep 300 & echo \"bg=$!;\"\n",
            )
            .unwrap();
        let (text, _) = read_until(&rx, info.session_id, ";\r\n");
        let bg: i32 = text
            .split("bg=")
            .filter_map(|rest| rest.split(';').next())
            .find_map(|pid| pid.parse().ok())
            .unwrap_or_else(|| panic!("no background pid in {text:?}"));
        manager.close("main", info.session_id).unwrap();
        // Dead means gone or a zombie waiting for its new parent to reap it.
        let alive = || {
            std::fs::read_to_string(format!("/proc/{bg}/stat"))
                .ok()
                .and_then(|stat| {
                    stat.rsplit_once(')')
                        .map(|(_, rest)| rest.trim_start().to_owned())
                })
                .is_some_and(|rest| !rest.starts_with('Z') && !rest.starts_with('X'))
        };
        let deadline = Instant::now() + Duration::from_secs(3);
        while alive() && Instant::now() < deadline {
            std::thread::sleep(Duration::from_millis(50));
        }
        assert!(!alive(), "background job {bg} survived close");
    }

    #[test]
    fn rejects_bad_sizes_large_frames_and_unknown_signals() {
        let (manager, _rx) = manager();
        assert!(matches!(
            manager.create("main", &sh(), 0, 24),
            Err(TerminalError::InvalidArgument(_))
        ));
        assert!(matches!(
            manager.create("main", &sh(), 80, 501),
            Err(TerminalError::InvalidArgument(_))
        ));
        let info = manager.create("main", &sh(), 80, 24).unwrap();
        let big = "x".repeat(MAX_WRITE_BYTES + 1);
        assert!(matches!(
            manager.write("main", info.session_id, &big),
            Err(TerminalError::InvalidArgument(_))
        ));
        assert!(matches!(
            AllowedSignal::parse("SIGKILL"),
            Err(TerminalError::InvalidArgument(_))
        ));
        assert_eq!(AllowedSignal::parse("SIGINT"), Ok(AllowedSignal::Interrupt));
        manager.close("main", info.session_id).unwrap();
    }

    #[test]
    fn enforces_the_session_limit() {
        let (manager, _rx) = manager();
        let ids: Vec<u32> = (0..MAX_SESSIONS)
            .map(|_| manager.create("main", &sh(), 80, 24).unwrap().session_id)
            .collect();
        assert_eq!(
            manager.create("main", &sh(), 80, 24),
            Err(TerminalError::Limit)
        );
        for id in ids {
            manager.close("main", id).unwrap();
        }
    }

    #[test]
    fn profile_refuses_root() {
        // SAFETY: geteuid has no preconditions.
        if unsafe { libc::geteuid() } == 0 {
            assert_eq!(
                ShellProfile::for_current_user().unwrap_err(),
                TerminalError::RootRefused
            );
        } else {
            let profile = ShellProfile::for_current_user().unwrap();
            assert!(profile.shell.is_absolute());
            assert!(profile.cwd.is_dir());
        }
    }
}
