//! Scoped, TOCTOU-safe file access (Phase 0 §3.4).
//!
//! Authorization and resolution are one kernel operation. There is no
//! "check the path, then open it" step that an attacker could race:
//!
//! 1. [`RelPath`] validates the requested path component by component
//!    (no absolute paths, no `.`/`..`, no empty components, no NUL).
//! 2. [`PathScope::permits`] is a component-based policy pre-check.
//!    `Under("Documents")` never matches `Documents-secret`.
//! 3. [`SecureRoot::open`] opens the scope directory and then the target with
//!    `openat2(2)` and `RESOLVE_BENEATH | RESOLVE_NO_MAGICLINKS | RESOLVE_NO_XDEV`
//!    (+ `RESOLVE_NO_SYMLINKS` unless the scope allows symlinks inside it).
//!    The kernel refuses any resolution that leaves the scope, including a
//!    symlink swapped in after the pre-check.
//!
//! There is no fallback. If `openat2` is unavailable or resolution fails,
//! the operation is refused.

use std::ffi::CString;
use std::fs::File;
use std::io;
use std::os::fd::{AsRawFd, FromRawFd, OwnedFd};
use std::os::unix::ffi::OsStrExt;
use std::path::Path;

pub const MAX_PATH_LEN: usize = 4096;

#[derive(Debug)]
pub enum PathError {
    Invalid(&'static str),
    OutOfScope,
    /// The kernel refused to resolve the path inside the scope
    /// (escape attempt, symlink, magic link or mount crossing).
    EscapeBlocked,
    NotFound,
    PermissionDenied,
    AlreadyExists,
    /// `openat2` is not available; secure access is impossible.
    Unsupported,
    Io(io::Error),
}

impl PartialEq for PathError {
    fn eq(&self, other: &Self) -> bool {
        use PathError::*;
        match (self, other) {
            (Invalid(a), Invalid(b)) => a == b,
            (Io(a), Io(b)) => a.kind() == b.kind(),
            _ => std::mem::discriminant(self) == std::mem::discriminant(other),
        }
    }
}

impl std::fmt::Display for PathError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{self:?}")
    }
}

impl std::error::Error for PathError {}

/// A validated path relative to a [`SecureRoot`].
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RelPath {
    components: Vec<String>,
}

impl RelPath {
    pub fn parse(path: &str) -> Result<Self, PathError> {
        if path.is_empty() {
            return Err(PathError::Invalid("empty"));
        }
        if path.len() > MAX_PATH_LEN {
            return Err(PathError::Invalid("too long"));
        }
        if path.contains('\0') {
            return Err(PathError::Invalid("NUL byte"));
        }
        if path.starts_with('/') {
            return Err(PathError::Invalid("absolute"));
        }
        let mut components = Vec::new();
        for part in path.split('/') {
            match part {
                "" => return Err(PathError::Invalid("empty component")),
                "." | ".." => return Err(PathError::Invalid("dot component")),
                other => components.push(other.to_owned()),
            }
        }
        Ok(Self { components })
    }

    pub fn components(&self) -> &[String] {
        &self.components
    }

    fn joined(&self) -> String {
        self.components.join("/")
    }

    fn starts_with(&self, prefix: &RelPath) -> bool {
        self.components.len() >= prefix.components.len()
            && self.components[..prefix.components.len()] == prefix.components[..]
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SymlinkPolicy {
    /// No symlink anywhere in the path (default).
    Deny,
    /// Symlinks below the scope directory are followed, but never out of it.
    WithinScope,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum PathScope {
    Exact(RelPath),
    Under(RelPath, SymlinkPolicy),
}

impl PathScope {
    /// Component-based policy pre-check. Not the security boundary on its
    /// own; [`SecureRoot::open`] enforces the scope in the kernel.
    pub fn permits(&self, path: &RelPath) -> bool {
        match self {
            PathScope::Exact(exact) => path == exact,
            PathScope::Under(dir, _) => path.starts_with(dir) && path != dir,
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum OpenMode {
    Read,
    /// Create a new file (fails if it exists), mode 0600, write-only.
    CreateNew,
}

/// A directory opened once as `O_PATH`; every access is resolved beneath it.
#[derive(Debug)]
pub struct SecureRoot {
    fd: OwnedFd,
}

const BASE_RESOLVE: u64 =
    libc::RESOLVE_BENEATH | libc::RESOLVE_NO_MAGICLINKS | libc::RESOLVE_NO_XDEV;

fn openat2(
    dirfd: i32,
    path: &str,
    flags: i32,
    mode: u32,
    resolve: u64,
) -> Result<OwnedFd, PathError> {
    let c_path = CString::new(path).map_err(|_| PathError::Invalid("NUL byte"))?;
    // SAFETY: open_how is plain old data; all-zero is a valid value.
    let mut how: libc::open_how = unsafe { std::mem::zeroed() };
    how.flags = (flags | libc::O_CLOEXEC) as u64;
    how.mode = mode as u64;
    how.resolve = resolve;
    // SAFETY: c_path and how outlive the call; size matches the struct.
    let fd = unsafe {
        libc::syscall(
            libc::SYS_openat2,
            dirfd,
            c_path.as_ptr(),
            &how as *const libc::open_how,
            std::mem::size_of::<libc::open_how>(),
        )
    };
    if fd < 0 {
        let error = io::Error::last_os_error();
        return Err(match error.raw_os_error() {
            Some(libc::ENOSYS) => PathError::Unsupported,
            Some(libc::EXDEV) | Some(libc::ELOOP) => PathError::EscapeBlocked,
            Some(libc::ENOENT) => PathError::NotFound,
            Some(libc::EACCES) | Some(libc::EPERM) => PathError::PermissionDenied,
            Some(libc::EEXIST) => PathError::AlreadyExists,
            _ => PathError::Io(error),
        });
    }
    // SAFETY: the kernel returned a fresh descriptor that we now own.
    Ok(unsafe { OwnedFd::from_raw_fd(fd as i32) })
}

impl SecureRoot {
    /// Open `dir` as the trust anchor. The root path itself is trusted
    /// configuration (e.g. the user's home), not user input.
    pub fn open(dir: &Path) -> Result<Self, PathError> {
        let c_path =
            CString::new(dir.as_os_str().as_bytes()).map_err(|_| PathError::Invalid("NUL byte"))?;
        // SAFETY: valid C string; flags request a new descriptor.
        let fd = unsafe {
            libc::open(
                c_path.as_ptr(),
                libc::O_PATH | libc::O_DIRECTORY | libc::O_CLOEXEC,
            )
        };
        if fd < 0 {
            return Err(PathError::Io(io::Error::last_os_error()));
        }
        // SAFETY: fresh descriptor owned from here on.
        Ok(Self {
            fd: unsafe { OwnedFd::from_raw_fd(fd) },
        })
    }

    /// Authorize and open `path` in one step.
    pub fn open_file(
        &self,
        scope: &PathScope,
        path: &RelPath,
        mode: OpenMode,
    ) -> Result<File, PathError> {
        if !scope.permits(path) {
            return Err(PathError::OutOfScope);
        }
        let (flags, perm) = match mode {
            // Symlink handling is decided by the resolve flags, not O_NOFOLLOW.
            OpenMode::Read => (libc::O_RDONLY, 0),
            // O_CREAT|O_EXCL never follows a symlink in the final component.
            OpenMode::CreateNew => (libc::O_WRONLY | libc::O_CREAT | libc::O_EXCL, 0o600),
        };
        let fd = match scope {
            PathScope::Exact(_) => openat2(
                self.fd.as_raw_fd(),
                &path.joined(),
                flags,
                perm,
                BASE_RESOLVE | libc::RESOLVE_NO_SYMLINKS,
            )?,
            PathScope::Under(dir, symlinks) => {
                // The scope directory itself is reached without symlinks, so
                // the lexical scope check and the kernel's view agree.
                let scope_fd = openat2(
                    self.fd.as_raw_fd(),
                    &dir.joined(),
                    libc::O_PATH | libc::O_DIRECTORY,
                    0,
                    BASE_RESOLVE | libc::RESOLVE_NO_SYMLINKS,
                )?;
                let rest = RelPath {
                    components: path.components[dir.components.len()..].to_vec(),
                };
                let resolve = match symlinks {
                    SymlinkPolicy::Deny => BASE_RESOLVE | libc::RESOLVE_NO_SYMLINKS,
                    SymlinkPolicy::WithinScope => BASE_RESOLVE,
                };
                openat2(scope_fd.as_raw_fd(), &rest.joined(), flags, perm, resolve)?
            }
        };
        Ok(File::from(fd))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::{Read, Write};
    use std::os::unix::fs::symlink;
    use std::sync::Arc;
    use std::sync::atomic::{AtomicBool, AtomicU32, Ordering};

    struct TempDir(std::path::PathBuf);

    impl TempDir {
        fn new() -> Self {
            static N: AtomicU32 = AtomicU32::new(0);
            let dir = std::env::temp_dir().join(format!(
                "eira-path-{}-{}",
                std::process::id(),
                N.fetch_add(1, Ordering::Relaxed)
            ));
            std::fs::create_dir_all(&dir).unwrap();
            TempDir(dir)
        }
    }

    impl Drop for TempDir {
        fn drop(&mut self) {
            let _ = std::fs::remove_dir_all(&self.0);
        }
    }

    /// root/home/Documents/note.txt, root/home/Documents-secret/key.txt,
    /// root/outside.txt
    fn layout() -> (TempDir, SecureRoot) {
        let tmp = TempDir::new();
        let docs = tmp.0.join("home/Documents");
        std::fs::create_dir_all(&docs).unwrap();
        std::fs::create_dir_all(tmp.0.join("home/Documents-secret")).unwrap();
        std::fs::write(docs.join("note.txt"), "note").unwrap();
        std::fs::write(tmp.0.join("home/Documents-secret/key.txt"), "SECRET").unwrap();
        std::fs::write(tmp.0.join("outside.txt"), "SECRET").unwrap();
        let root = SecureRoot::open(&tmp.0.join("home")).unwrap();
        (tmp, root)
    }

    fn docs(policy: SymlinkPolicy) -> PathScope {
        PathScope::Under(RelPath::parse("Documents").unwrap(), policy)
    }

    fn read(root: &SecureRoot, scope: &PathScope, path: &str) -> Result<String, PathError> {
        let mut s = String::new();
        root.open_file(scope, &RelPath::parse(path)?, OpenMode::Read)?
            .read_to_string(&mut s)
            .unwrap();
        Ok(s)
    }

    #[test]
    fn relative_paths_are_validated_per_component() {
        for (bad, why) in [
            ("", "empty"),
            ("/etc/passwd", "absolute"),
            ("Documents/../x", "dot component"),
            ("./Documents", "dot component"),
            ("Documents//x", "empty component"),
            ("Documents/", "empty component"),
            ("a\0b", "NUL byte"),
        ] {
            assert_eq!(RelPath::parse(bad), Err(PathError::Invalid(why)), "{bad:?}");
        }
        assert_eq!(
            RelPath::parse(&"a/".repeat(2049)),
            Err(PathError::Invalid("too long"))
        );
    }

    #[test]
    fn scope_is_component_based_not_a_string_prefix() {
        let scope = docs(SymlinkPolicy::Deny);
        assert!(scope.permits(&RelPath::parse("Documents/note.txt").unwrap()));
        assert!(!scope.permits(&RelPath::parse("Documents-secret/key.txt").unwrap()));
        assert!(!scope.permits(&RelPath::parse("Documents").unwrap()));
        let exact = PathScope::Exact(RelPath::parse("Documents/note.txt").unwrap());
        assert!(!exact.permits(&RelPath::parse("Documents/note.txt.bak").unwrap()));
    }

    #[test]
    fn reads_inside_scope_and_refuses_neighbours() {
        let (_tmp, root) = layout();
        let scope = docs(SymlinkPolicy::Deny);
        assert_eq!(read(&root, &scope, "Documents/note.txt").unwrap(), "note");
        assert_eq!(
            read(&root, &scope, "Documents-secret/key.txt"),
            Err(PathError::OutOfScope)
        );
        assert_eq!(
            read(&root, &scope, "Documents/missing.txt"),
            Err(PathError::NotFound)
        );
    }

    #[test]
    fn symlink_escape_is_blocked_by_the_kernel() {
        let (tmp, root) = layout();
        let docs_dir = tmp.0.join("home/Documents");
        symlink(tmp.0.join("outside.txt"), docs_dir.join("abs-link")).unwrap();
        symlink("../Documents-secret/key.txt", docs_dir.join("rel-link")).unwrap();
        symlink("note.txt", docs_dir.join("inner-link")).unwrap();
        symlink("/proc/self/root/etc/hostname", docs_dir.join("magic")).unwrap();

        for policy in [SymlinkPolicy::Deny, SymlinkPolicy::WithinScope] {
            let scope = docs(policy);
            for link in ["abs-link", "rel-link", "magic"] {
                assert_eq!(
                    read(&root, &scope, &format!("Documents/{link}")),
                    Err(PathError::EscapeBlocked),
                    "{link} with {policy:?}"
                );
            }
        }
        assert_eq!(
            read(&root, &docs(SymlinkPolicy::Deny), "Documents/inner-link"),
            Err(PathError::EscapeBlocked)
        );
        assert_eq!(
            read(
                &root,
                &docs(SymlinkPolicy::WithinScope),
                "Documents/inner-link"
            )
            .unwrap(),
            "note"
        );
    }

    #[test]
    fn a_symlinked_scope_directory_is_refused() {
        let (tmp, root) = layout();
        symlink(tmp.0.join("home/Documents-secret"), tmp.0.join("home/Docs")).unwrap();
        let scope = PathScope::Under(RelPath::parse("Docs").unwrap(), SymlinkPolicy::WithinScope);
        assert_eq!(
            read(&root, &scope, "Docs/key.txt"),
            Err(PathError::EscapeBlocked)
        );
    }

    #[test]
    fn create_new_never_overwrites_or_follows_links() {
        let (tmp, root) = layout();
        let scope = docs(SymlinkPolicy::WithinScope);
        let mut f = root
            .open_file(
                &scope,
                &RelPath::parse("Documents/new.txt").unwrap(),
                OpenMode::CreateNew,
            )
            .unwrap();
        f.write_all(b"hej").unwrap();
        assert_eq!(
            root.open_file(
                &scope,
                &RelPath::parse("Documents/note.txt").unwrap(),
                OpenMode::CreateNew
            )
            .unwrap_err(),
            PathError::AlreadyExists
        );
        symlink(tmp.0.join("planted.txt"), tmp.0.join("home/Documents/trap")).unwrap();
        assert!(
            root.open_file(
                &scope,
                &RelPath::parse("Documents/trap").unwrap(),
                OpenMode::CreateNew
            )
            .is_err()
        );
        assert!(!tmp.0.join("planted.txt").exists());
    }

    #[test]
    fn toctou_swap_never_yields_the_secret() {
        // An attacker flips Documents/target between a real file and a
        // symlink to the secret while we keep opening it.
        let (tmp, root) = layout();
        let target = tmp.0.join("home/Documents/target");
        let staging = tmp.0.join("home/Documents/staging");
        std::fs::write(&target, "ok").unwrap();
        let stop = Arc::new(AtomicBool::new(false));
        let attacker = {
            let stop = Arc::clone(&stop);
            let (target, staging, secret) =
                (target.clone(), staging.clone(), tmp.0.join("outside.txt"));
            std::thread::spawn(move || {
                while !stop.load(Ordering::Relaxed) {
                    let _ = std::fs::remove_file(&staging);
                    let _ = symlink(&secret, &staging);
                    let _ = std::fs::rename(&staging, &target);
                    let _ = std::fs::write(&staging, "ok");
                    let _ = std::fs::rename(&staging, &target);
                }
            })
        };
        let scope = docs(SymlinkPolicy::WithinScope);
        let mut opened = 0;
        for _ in 0..5000 {
            match read(&root, &scope, "Documents/target") {
                Ok(content) => {
                    assert_ne!(content, "SECRET");
                    opened += 1;
                }
                Err(PathError::EscapeBlocked) | Err(PathError::NotFound) => {}
                Err(other) => panic!("unexpected {other:?}"),
            }
        }
        stop.store(true, Ordering::Relaxed);
        attacker.join().unwrap();
        assert!(opened > 0, "the race test never opened the legitimate file");
    }
}
