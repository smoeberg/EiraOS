//! What the agent trusts from its start (EIRA-CONSENT-AGENT R-5.1–R-5.4).
//!
//! The agent is setgid: its argv, environment, stdin and inherited file
//! descriptors come from whoever started it, which may be a program running
//! as the user. It takes nothing from them but two environment variables,
//! and checks those.

use std::ffi::CStr;
use std::path::{Path, PathBuf};

pub const CONSENT_GROUP: &str = "eira-consent";

#[derive(Debug, PartialEq, Eq)]
pub enum Refusal {
    Arguments,
    NotSetgid,
    Environment(&'static str),
}

/// R-5.4: no arguments except `--version`. Returns true for `--version`.
pub fn check_args<I: IntoIterator<Item = String>>(args: I) -> Result<bool, Refusal> {
    let rest: Vec<String> = args.into_iter().skip(1).collect();
    match rest.as_slice() {
        [] => Ok(false),
        [only] if only == "--version" => Ok(true),
        _ => Err(Refusal::Arguments),
    }
}

/// R-5.3: close every inherited descriptor above 2, so a connection opened
/// with the agent's GID cannot be lent out, and nothing it did not open
/// itself is used.
pub fn close_inherited_fds() {
    // SAFETY: close_range has no memory-safety preconditions; on failure we
    // fall back to closing one by one.
    let done = unsafe { libc::syscall(libc::SYS_close_range, 3u32, u32::MAX, 0u32) } == 0;
    if !done {
        for fd in 3..1024 {
            // SAFETY: closing an fd we do not use is harmless.
            unsafe {
                libc::close(fd);
            }
        }
    }
}

/// Not dumpable: no core file, no ptrace from processes of the same user.
/// The kernel already does this for setgid programs; this keeps it so.
pub fn not_dumpable() {
    // SAFETY: prctl with these arguments has no memory-safety preconditions.
    unsafe {
        libc::prctl(libc::PR_SET_DUMPABLE, 0, 0, 0, 0);
    }
}

pub fn group_id(name: &str) -> Option<u32> {
    let cname = std::ffi::CString::new(name).ok()?;
    // SAFETY: getgrnam returns a pointer to static storage or null.
    let entry = unsafe { libc::getgrnam(cname.as_ptr()) };
    if entry.is_null() {
        return None;
    }
    // SAFETY: entry is non-null and points to a valid struct group.
    Some(unsafe { (*entry).gr_gid })
}

/// The agent only makes sense as the setgid binary: otherwise it has no
/// identity the gate and identityd would accept.
pub fn require_setgid() -> Result<u32, Refusal> {
    // SAFETY: plain syscalls without arguments.
    let (real, effective) = unsafe { (libc::getgid(), libc::getegid()) };
    match group_id(CONSENT_GROUP) {
        Some(gid) if effective == gid && real != gid => Ok(gid),
        _ => Err(Refusal::NotSetgid),
    }
}

#[derive(Debug, PartialEq, Eq)]
pub struct Environment {
    pub runtime_dir: PathBuf,
    pub wayland_socket: PathBuf,
}

/// R-5.1: only `WAYLAND_DISPLAY` and `XDG_RUNTIME_DIR`, checked.
pub fn read_environment(
    runtime_dir: Option<&str>,
    display: Option<&str>,
    real_uid: u32,
) -> Result<Environment, Refusal> {
    let expected = format!("/run/user/{real_uid}");
    let runtime_dir = runtime_dir.ok_or(Refusal::Environment("XDG_RUNTIME_DIR missing"))?;
    if runtime_dir.trim_end_matches('/') != expected {
        return Err(Refusal::Environment(
            "XDG_RUNTIME_DIR is not /run/user/<uid>",
        ));
    }
    let display = display.unwrap_or("wayland-0");
    if display.is_empty()
        || display.contains('/')
        || display.contains('\0')
        || display == "."
        || display == ".."
    {
        return Err(Refusal::Environment(
            "WAYLAND_DISPLAY must be a name inside XDG_RUNTIME_DIR",
        ));
    }
    let runtime_dir = PathBuf::from(expected);
    Ok(Environment {
        wayland_socket: runtime_dir.join(display),
        runtime_dir,
    })
}

/// The runtime directory must be the user's own and private.
pub fn check_runtime_dir(path: &Path, real_uid: u32) -> Result<(), Refusal> {
    use std::os::unix::fs::MetadataExt;
    let meta =
        std::fs::symlink_metadata(path).map_err(|_| Refusal::Environment("no runtime dir"))?;
    if !meta.is_dir() || meta.uid() != real_uid || meta.mode() & 0o077 != 0 {
        return Err(Refusal::Environment(
            "runtime dir is not the user's private directory",
        ));
    }
    Ok(())
}

pub fn real_uid() -> u32 {
    // SAFETY: plain syscall.
    unsafe { libc::getuid() }
}

/// Reads a variable without trusting the rest of the environment.
pub fn env(name: &CStr) -> Option<String> {
    // SAFETY: getenv returns a pointer into the environment or null; we copy
    // it before anything can change the environment.
    let value = unsafe { libc::getenv(name.as_ptr()) };
    if value.is_null() {
        return None;
    }
    // SAFETY: non-null, NUL-terminated.
    unsafe { CStr::from_ptr(value) }
        .to_str()
        .ok()
        .map(str::to_owned)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn only_version_is_an_accepted_argument() {
        let args = |v: &[&str]| v.iter().map(|s| s.to_string()).collect::<Vec<_>>();
        assert_eq!(check_args(args(&["agent"])), Ok(false));
        assert_eq!(check_args(args(&["agent", "--version"])), Ok(true));
        for bad in [
            &["agent", "--help"][..],
            &["agent", "--version", "x"],
            &["agent", "-c", "x"],
        ] {
            assert_eq!(check_args(args(bad)), Err(Refusal::Arguments));
        }
    }

    #[test]
    fn the_runtime_dir_must_be_the_users_own() {
        assert!(read_environment(Some("/run/user/1000"), None, 1000).is_ok());
        assert!(read_environment(Some("/run/user/1000/"), Some("wayland-1"), 1000).is_ok());
        for dir in [
            None,
            Some("/tmp"),
            Some("/run/user/1001"),
            Some("/run/user/1000/x"),
        ] {
            assert!(read_environment(dir, None, 1000).is_err(), "{dir:?}");
        }
    }

    #[test]
    fn the_display_cannot_point_elsewhere() {
        for display in ["../1001/wayland-0", "/tmp/wayland", "", "..", "a\0b"] {
            assert!(
                read_environment(Some("/run/user/1000"), Some(display), 1000).is_err(),
                "{display:?}"
            );
        }
        let env = read_environment(Some("/run/user/1000"), Some("wayland-1"), 1000).unwrap();
        assert_eq!(
            env.wayland_socket,
            PathBuf::from("/run/user/1000/wayland-1")
        );
    }

    #[test]
    fn not_setgid_is_refused() {
        // Tests do not run setgid eira-consent.
        assert_eq!(require_setgid(), Err(Refusal::NotSetgid));
    }
}
