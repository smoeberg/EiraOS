//! systemd socket activation with explicit FD ownership (Phase 0 §3.5).
//!
//! * `LISTEN_PID` must equal our PID, otherwise the descriptors are not ours.
//! * Descriptors start at fd 3 (`SD_LISTEN_FDS_START`); `LISTEN_FDNAMES`
//!   (if present) must name every descriptor.
//! * Every descriptor is owned by exactly one [`OwnedFd`] from parsing on.
//!   [`Activation::take_listener`] moves it out and validates it as a
//!   listening `AF_UNIX`/`SOCK_STREAM` socket. A name can be taken once.
//! * Descriptors that are never taken are closed when [`Activation`] drops.

use std::collections::HashSet;
use std::io;
use std::os::fd::{AsRawFd, FromRawFd, OwnedFd, RawFd};
use std::os::unix::net::UnixListener;

pub const SD_LISTEN_FDS_START: RawFd = 3;
/// Upper bound on accepted descriptors; protects against a bogus LISTEN_FDS.
pub const MAX_LISTEN_FDS: usize = 64;

#[derive(Debug)]
pub enum ActivationError {
    /// LISTEN_PID/LISTEN_FDS are malformed or inconsistent.
    InvalidEnvironment(&'static str),
    /// The descriptors were passed to another process.
    NotForThisProcess,
    NotFound(String),
    AlreadyTaken(String),
    /// Several descriptors share this name; use `take_listeners`.
    Ambiguous(String),
    /// Not a listening AF_UNIX stream socket.
    WrongSocketType(String),
    Io(io::Error),
}

impl std::fmt::Display for ActivationError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{self:?}")
    }
}

impl std::error::Error for ActivationError {}

#[derive(Debug)]
pub struct Activation {
    fds: Vec<(String, OwnedFd)>,
    taken: HashSet<String>,
}

fn sockopt(fd: RawFd, option: libc::c_int) -> io::Result<libc::c_int> {
    let mut value: libc::c_int = 0;
    let mut len = std::mem::size_of::<libc::c_int>() as libc::socklen_t;
    // SAFETY: value/len are valid for writes of the requested size.
    let rc = unsafe {
        libc::getsockopt(
            fd,
            libc::SOL_SOCKET,
            option,
            &mut value as *mut libc::c_int as *mut libc::c_void,
            &mut len,
        )
    };
    if rc < 0 {
        Err(io::Error::last_os_error())
    } else {
        Ok(value)
    }
}

fn is_listening_unix_stream(fd: RawFd) -> io::Result<bool> {
    // SAFETY: fstat writes into a zeroed stat struct we own.
    let mut st: libc::stat = unsafe { std::mem::zeroed() };
    if unsafe { libc::fstat(fd, &mut st) } < 0 {
        return Err(io::Error::last_os_error());
    }
    if st.st_mode & libc::S_IFMT != libc::S_IFSOCK {
        return Ok(false);
    }
    Ok(sockopt(fd, libc::SO_DOMAIN)? == libc::AF_UNIX
        && sockopt(fd, libc::SO_TYPE)? == libc::SOCK_STREAM
        && sockopt(fd, libc::SO_ACCEPTCONN)? == 1)
}

/// systemd's rule for `FileDescriptorName=` (`fdname_is_valid`): 1–255
/// ASCII characters that are not control characters, and no `:` (the list
/// separator). Space is allowed. Names need not be unique.
fn valid_fd_name(name: &str) -> bool {
    !name.is_empty()
        && name.len() <= 255
        && name.bytes().all(|b| (0x20..0x7f).contains(&b) && b != b':')
}

impl Activation {
    /// Parse activation variables from `env`. Returns `Ok(None)` when the
    /// process was not socket-activated (no `LISTEN_FDS`).
    ///
    /// # Safety
    /// Ownership begins once `LISTEN_PID` matches and `LISTEN_FDS` parses to
    /// a count of at most [`MAX_LISTEN_FDS`]. From then on this owns fds
    /// `3..3+LISTEN_FDS` — on success and on every later error, which closes
    /// them. Before that point nothing is touched: the variables are not for
    /// us, malformed, or claim more descriptors than EiraOS accepts. In that
    /// last case we deliberately do not close an unbounded range of fd
    /// numbers we cannot verify; the service must treat the error as fatal
    /// and exit, which releases whatever it inherited.
    /// The caller
    /// must ensure nothing else in the process owns or closes them, which
    /// holds at the start of `main` in a systemd-activated service.
    pub unsafe fn from_env(
        env: impl Fn(&str) -> Option<String>,
        our_pid: u32,
    ) -> Result<Option<Self>, ActivationError> {
        let Some(count) = env("LISTEN_FDS") else {
            return Ok(None);
        };
        let pid: u32 = env("LISTEN_PID")
            .ok_or(ActivationError::InvalidEnvironment("LISTEN_PID missing"))?
            .parse()
            .map_err(|_| ActivationError::InvalidEnvironment("LISTEN_PID not a number"))?;
        if pid != our_pid {
            return Err(ActivationError::NotForThisProcess);
        }
        let count: usize = count
            .parse()
            .map_err(|_| ActivationError::InvalidEnvironment("LISTEN_FDS not a number"))?;
        if count > MAX_LISTEN_FDS {
            return Err(ActivationError::InvalidEnvironment("LISTEN_FDS too large"));
        }
        let names: Vec<String> = match env("LISTEN_FDNAMES") {
            Some(list) => list.split(':').map(str::to_owned).collect(),
            None => vec!["unknown".to_owned(); count],
        };
        // From here on the fds are ours: a name/count mismatch is detected
        // inside from_raw_fds, after they have been wrapped (and closed).
        let fds = (0..count as RawFd)
            .map(|i| SD_LISTEN_FDS_START + i)
            .collect();
        // SAFETY: forwarded from the caller's contract.
        unsafe { Self::from_raw_fds(fds, names) }
    }

    /// Like [`from_env`](Self::from_env) for the real process environment,
    /// and clears the variables afterwards so child processes cannot reuse
    /// them (as `sd_listen_fds(unset_environment=1)` does).
    ///
    /// # Safety
    /// As for `from_env`; additionally modifies the process environment, so
    /// it must run before any other thread is started.
    pub unsafe fn from_process_env() -> Result<Option<Self>, ActivationError> {
        let result = unsafe { Self::from_env(|k| std::env::var(k).ok(), std::process::id()) };
        for key in ["LISTEN_PID", "LISTEN_FDS", "LISTEN_FDNAMES"] {
            // SAFETY: single-threaded per this function's contract.
            unsafe { std::env::remove_var(key) };
        }
        result
    }

    /// # Safety
    /// Takes ownership of every fd in `fds` — on success *and* on every
    /// error path: each fd is wrapped in an [`OwnedFd`] before anything is
    /// validated, so a failure closes all of them instead of leaking them.
    pub unsafe fn from_raw_fds(
        fds: Vec<RawFd>,
        names: Vec<String>,
    ) -> Result<Option<Self>, ActivationError> {
        // SAFETY: ownership transferred by the caller.
        let owned: Vec<OwnedFd> = fds
            .into_iter()
            .map(|fd| unsafe { OwnedFd::from_raw_fd(fd) })
            .collect();
        if owned.len() != names.len() {
            return Err(ActivationError::InvalidEnvironment("name count mismatch"));
        }
        if !names.iter().all(|name| valid_fd_name(name)) {
            return Err(ActivationError::InvalidEnvironment("invalid fd name"));
        }
        for fd in &owned {
            // systemd passes descriptors without FD_CLOEXEC; never leak them.
            // SAFETY: fd is valid and owned.
            if unsafe { libc::fcntl(fd.as_raw_fd(), libc::F_SETFD, libc::FD_CLOEXEC) } < 0 {
                return Err(ActivationError::Io(io::Error::last_os_error()));
            }
        }
        Ok(Some(Self {
            fds: names.into_iter().zip(owned).collect(),
            taken: HashSet::new(),
        }))
    }

    pub fn names(&self) -> impl Iterator<Item = &str> {
        self.fds.iter().map(|(n, _)| n.as_str())
    }

    /// Move the single descriptor named `name` out as a validated listener.
    /// A descriptor that fails validation is closed, not handed back.
    /// If several descriptors carry the name (systemd allows that), nothing
    /// is moved and `Ambiguous` is returned; use [`take_listeners`](Self::take_listeners).
    pub fn take_listener(&mut self, name: &str) -> Result<UnixListener, ActivationError> {
        if self.fds.iter().filter(|(n, _)| n == name).count() > 1 {
            return Err(ActivationError::Ambiguous(name.to_owned()));
        }
        let mut listeners = self.take_listeners(name)?;
        Ok(listeners.remove(0))
    }

    /// Move out every descriptor named `name`, in `LISTEN_FDS` order.
    /// All of them are validated; if any one is not a listening AF_UNIX
    /// stream socket, all of them are closed and an error is returned.
    pub fn take_listeners(&mut self, name: &str) -> Result<Vec<UnixListener>, ActivationError> {
        if self.taken.contains(name) {
            return Err(ActivationError::AlreadyTaken(name.to_owned()));
        }
        let mut moved = Vec::new();
        let mut rest = Vec::with_capacity(self.fds.len());
        for (n, fd) in self.fds.drain(..) {
            if n == name {
                moved.push(fd);
            } else {
                rest.push((n, fd));
            }
        }
        self.fds = rest;
        if moved.is_empty() {
            return Err(ActivationError::NotFound(name.to_owned()));
        }
        self.taken.insert(name.to_owned());
        for fd in &moved {
            match is_listening_unix_stream(fd.as_raw_fd()) {
                Ok(true) => {}
                Ok(false) => return Err(ActivationError::WrongSocketType(name.to_owned())),
                Err(error) => return Err(ActivationError::Io(error)),
            }
        }
        Ok(moved.into_iter().map(UnixListener::from).collect())
    }

    /// Same ownership contract, converted for Tokio (must run inside a runtime).
    #[cfg(feature = "ipc-tokio")]
    pub fn take_tokio_listener(
        &mut self,
        name: &str,
    ) -> Result<tokio::net::UnixListener, ActivationError> {
        let listener = self.take_listener(name)?;
        listener
            .set_nonblocking(true)
            .map_err(ActivationError::Io)?;
        tokio::net::UnixListener::from_std(listener).map_err(ActivationError::Io)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::os::fd::IntoRawFd;
    use std::os::unix::net::UnixStream;
    use std::sync::atomic::{AtomicU32, Ordering};

    fn sock_path() -> std::path::PathBuf {
        static N: AtomicU32 = AtomicU32::new(0);
        std::env::temp_dir().join(format!(
            "eira-act-{}-{}.sock",
            std::process::id(),
            N.fetch_add(1, Ordering::Relaxed)
        ))
    }

    fn listener_fd() -> (RawFd, std::path::PathBuf) {
        let path = sock_path();
        let _ = std::fs::remove_file(&path);
        let listener = UnixListener::bind(&path).unwrap();
        (listener.into_raw_fd(), path)
    }

    fn is_open(fd: RawFd) -> bool {
        unsafe { libc::fcntl(fd, libc::F_GETFD) >= 0 }
    }

    fn env(vars: &'static [(&'static str, &'static str)]) -> impl Fn(&str) -> Option<String> {
        move |k| {
            vars.iter()
                .find(|(n, _)| *n == k)
                .map(|(_, v)| v.to_string())
        }
    }

    #[test]
    fn environment_is_validated() {
        unsafe {
            assert!(Activation::from_env(env(&[]), 42).unwrap().is_none());
            assert!(matches!(
                Activation::from_env(env(&[("LISTEN_FDS", "1"), ("LISTEN_PID", "41")]), 42),
                Err(ActivationError::NotForThisProcess)
            ));
            assert!(matches!(
                Activation::from_env(env(&[("LISTEN_FDS", "1")]), 42),
                Err(ActivationError::InvalidEnvironment(_))
            ));
            assert!(matches!(
                Activation::from_env(env(&[("LISTEN_FDS", "x"), ("LISTEN_PID", "42")]), 42),
                Err(ActivationError::InvalidEnvironment(_))
            ));
            assert!(matches!(
                Activation::from_env(env(&[("LISTEN_FDS", "999"), ("LISTEN_PID", "42")]), 42),
                Err(ActivationError::InvalidEnvironment(_))
            ));
        }
    }

    // A LISTEN_FDNAMES/LISTEN_FDS mismatch is checked inside from_raw_fds
    // (after taking ownership); it is tested there with our own sockets,
    // because going through from_env here would take over fds 3.. of the
    // test process.

    /// Regression (review of #134): every error path in `from_raw_fds` must
    /// close the descriptors it was given, not leak them.
    #[test]
    fn rejected_activation_closes_every_descriptor() {
        use std::io::Read;
        let long = "x".repeat(256);
        let cases: [(&str, Vec<&str>); 5] = [
            ("count mismatch", vec!["a"]),
            ("colon", vec!["a", "has:colon"]),
            ("empty name", vec!["a", ""]),
            ("control character", vec!["a", "tab\there"]),
            ("too long", vec!["a", long.as_str()]),
        ];
        for (why, names) in cases {
            let (a, mut peer_a) = UnixStream::pair().unwrap();
            let (b, mut peer_b) = UnixStream::pair().unwrap();
            let result = unsafe {
                Activation::from_raw_fds(
                    vec![a.into_raw_fd(), b.into_raw_fd()],
                    names.into_iter().map(String::from).collect(),
                )
            };
            assert!(
                matches!(result, Err(ActivationError::InvalidEnvironment(_))),
                "{why}"
            );
            let mut buf = [0u8; 1];
            assert_eq!(peer_a.read(&mut buf).unwrap(), 0, "{why}: first fd leaked");
            assert_eq!(peer_b.read(&mut buf).unwrap(), 0, "{why}: second fd leaked");
        }
    }

    /// systemd allows spaces and allows several fds with the same name.
    #[test]
    fn names_follow_systemd_spaces_and_duplicates_are_allowed() {
        let (a, path_a) = listener_fd();
        let (b, path_b) = listener_fd();
        let (c, path_c) = listener_fd();
        let mut act = unsafe {
            Activation::from_raw_fds(
                vec![a, b, c],
                vec!["event bus".into(), "eventd".into(), "eventd".into()],
            )
        }
        .unwrap()
        .unwrap();
        // Ambiguous names are refused by take_listener and nothing moves.
        assert!(matches!(
            act.take_listener("eventd"),
            Err(ActivationError::Ambiguous(_))
        ));
        assert_eq!(act.names().filter(|n| *n == "eventd").count(), 2);
        let both = act.take_listeners("eventd").unwrap();
        assert_eq!(both.len(), 2);
        assert!(matches!(
            act.take_listeners("eventd"),
            Err(ActivationError::AlreadyTaken(_))
        ));
        let spaced = act.take_listener("event bus").unwrap();
        // All three work, in LISTEN_FDS order.
        for (listener, path) in [(&spaced, &path_a), (&both[0], &path_b), (&both[1], &path_c)] {
            let _client = UnixStream::connect(path).unwrap();
            listener.accept().unwrap();
        }
        for path in [path_a, path_b, path_c] {
            let _ = std::fs::remove_file(path);
        }
    }

    #[test]
    fn one_invalid_descriptor_under_a_name_closes_them_all() {
        use std::io::Read;
        let (listener, path) = listener_fd();
        let (stream, mut peer) = UnixStream::pair().unwrap();
        let mut act = unsafe {
            Activation::from_raw_fds(
                vec![listener, stream.into_raw_fd()],
                vec!["eventd".into(), "eventd".into()],
            )
        }
        .unwrap()
        .unwrap();
        assert!(matches!(
            act.take_listeners("eventd"),
            Err(ActivationError::WrongSocketType(_))
        ));
        let mut buf = [0u8; 1];
        assert_eq!(peer.read(&mut buf).unwrap(), 0);
        assert!(UnixStream::connect(&path).is_err());
        let _ = std::fs::remove_file(path);
    }

    #[test]
    fn a_named_listener_is_handed_over_exactly_once_and_works() {
        let (fd, path) = listener_fd();
        let mut act = unsafe { Activation::from_raw_fds(vec![fd], vec!["eventd".into()]) }
            .unwrap()
            .unwrap();
        assert_eq!(act.names().collect::<Vec<_>>(), vec!["eventd"]);
        let listener = act.take_listener("eventd").unwrap();
        assert!(matches!(
            act.take_listener("eventd"),
            Err(ActivationError::AlreadyTaken(_))
        ));
        assert!(matches!(
            act.take_listener("filesd"),
            Err(ActivationError::NotFound(_))
        ));
        drop(act);
        // Ownership moved to the listener: dropping Activation did not close it.
        assert!(is_open(listener.as_raw_fd()));
        let _client = UnixStream::connect(&path).unwrap();
        listener.accept().unwrap();
        let _ = std::fs::remove_file(path);
    }

    #[test]
    fn wrong_descriptor_types_are_rejected_and_closed() {
        let file = std::fs::File::open("/dev/null").unwrap().into_raw_fd();
        let (a, mut peer) = UnixStream::pair().unwrap();
        let stream = a.into_raw_fd();
        let udp = std::net::UdpSocket::bind("127.0.0.1:0")
            .unwrap()
            .into_raw_fd();
        // Bound but not listening.
        let unbound = unsafe { libc::socket(libc::AF_UNIX, libc::SOCK_STREAM, 0) };
        let mut act = unsafe {
            Activation::from_raw_fds(
                vec![file, stream, udp, unbound],
                vec!["file".into(), "stream".into(), "udp".into(), "idle".into()],
            )
        }
        .unwrap()
        .unwrap();
        for name in ["file", "stream", "udp", "idle"] {
            assert!(
                matches!(
                    act.take_listener(name),
                    Err(ActivationError::WrongSocketType(_))
                ),
                "{name}"
            );
        }
        // The rejected stream was closed: its peer sees end-of-file.
        // (Checked through the peer, because fd numbers are reused by
        // concurrently running tests.)
        use std::io::Read;
        let mut buf = [0u8; 1];
        assert_eq!(peer.read(&mut buf).unwrap(), 0);
    }

    #[test]
    fn untaken_descriptors_are_closed_on_drop() {
        let (fd, path) = listener_fd();
        let act = unsafe { Activation::from_raw_fds(vec![fd], vec!["spare".into()]) }
            .unwrap()
            .unwrap();
        assert!(is_open(fd));
        // Descriptors are marked close-on-exec.
        assert_eq!(
            unsafe { libc::fcntl(fd, libc::F_GETFD) } & libc::FD_CLOEXEC,
            libc::FD_CLOEXEC
        );
        UnixStream::connect(&path).unwrap();
        drop(act);
        // Closed: nobody listens on the socket any more.
        assert!(UnixStream::connect(&path).is_err());
        let _ = std::fs::remove_file(path);
    }

    #[cfg(feature = "ipc-tokio")]
    #[tokio::test]
    async fn tokio_conversion_follows_the_same_ownership() {
        let (fd, path) = listener_fd();
        let mut act = unsafe { Activation::from_raw_fds(vec![fd], vec!["eventd".into()]) }
            .unwrap()
            .unwrap();
        let listener = act.take_tokio_listener("eventd").unwrap();
        assert!(matches!(
            act.take_tokio_listener("eventd"),
            Err(ActivationError::AlreadyTaken(_))
        ));
        let client = tokio::net::UnixStream::connect(&path).await.unwrap();
        let (_server, _) = listener.accept().await.unwrap();
        drop(client);
        let _ = std::fs::remove_file(path);
    }
}
