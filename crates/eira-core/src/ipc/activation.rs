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

impl Activation {
    /// Parse activation variables from `env`. Returns `Ok(None)` when the
    /// process was not socket-activated (no `LISTEN_FDS`).
    ///
    /// # Safety
    /// On success this takes ownership of fds `3..3+LISTEN_FDS`. The caller
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
        if names.len() != count {
            return Err(ActivationError::InvalidEnvironment(
                "LISTEN_FDNAMES does not match LISTEN_FDS",
            ));
        }
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
    /// Takes ownership of every fd in `fds`.
    pub unsafe fn from_raw_fds(
        fds: Vec<RawFd>,
        names: Vec<String>,
    ) -> Result<Option<Self>, ActivationError> {
        if fds.len() != names.len() {
            return Err(ActivationError::InvalidEnvironment("name count mismatch"));
        }
        let mut owned = Vec::with_capacity(fds.len());
        for (fd, name) in fds.into_iter().zip(names) {
            // SAFETY: ownership transferred by the caller.
            let fd = unsafe { OwnedFd::from_raw_fd(fd) };
            // systemd passes descriptors without FD_CLOEXEC; never leak them.
            // SAFETY: fd is valid and owned.
            if unsafe { libc::fcntl(fd.as_raw_fd(), libc::F_SETFD, libc::FD_CLOEXEC) } < 0 {
                return Err(ActivationError::Io(io::Error::last_os_error()));
            }
            owned.push((name, fd));
        }
        Ok(Some(Self {
            fds: owned,
            taken: HashSet::new(),
        }))
    }

    pub fn names(&self) -> impl Iterator<Item = &str> {
        self.fds.iter().map(|(n, _)| n.as_str())
    }

    /// Move the descriptor named `name` out as a validated listener.
    /// A descriptor that fails validation is closed, not handed back.
    pub fn take_listener(&mut self, name: &str) -> Result<UnixListener, ActivationError> {
        if self.taken.contains(name) {
            return Err(ActivationError::AlreadyTaken(name.to_owned()));
        }
        let index = self
            .fds
            .iter()
            .position(|(n, _)| n == name)
            .ok_or_else(|| ActivationError::NotFound(name.to_owned()))?;
        if self.fds.iter().filter(|(n, _)| n == name).count() > 1 {
            return Err(ActivationError::InvalidEnvironment("duplicate fd name"));
        }
        let (name, fd) = self.fds.remove(index);
        self.taken.insert(name.clone());
        match is_listening_unix_stream(fd.as_raw_fd()) {
            Ok(true) => Ok(UnixListener::from(fd)),
            Ok(false) => Err(ActivationError::WrongSocketType(name)),
            Err(error) => Err(ActivationError::Io(error)),
        }
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
            assert!(matches!(
                Activation::from_env(
                    env(&[
                        ("LISTEN_FDS", "2"),
                        ("LISTEN_PID", "42"),
                        ("LISTEN_FDNAMES", "a")
                    ]),
                    42
                ),
                Err(ActivationError::InvalidEnvironment(_))
            ));
        }
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
