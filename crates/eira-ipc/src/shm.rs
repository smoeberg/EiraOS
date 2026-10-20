//! POSIX shared-memory transport for zero-copy payloads.
//!
//! Layout (little-endian, 64-byte header):
//! ```text
//!  0..8   magic        b"EIRASHM\0"
//!  8..10  version      u16  (SHM_FORMAT_VERSION)
//! 10..12  flags        u16  (reserved)
//! 12..16  generation   u32  (publish counter; odd = writing, even = stable)
//! 16..24  payload_len  u64
//! 24..56  sha3_256     [u8; 32]
//! 56..60  ready        u32  Atomic (0 = not ready, 1 = READY)
//! 60..64  reserved     u32
//! 64..    payload bytes
//! ```
//!
//! Concurrency contract (single-slot ring of depth 1):
//! - Writer clears `ready`, bumps generation to odd, writes payload+digest+len,
//!   bumps generation to even, then stores `ready=1` with `Release`.
//! - Reader loads `ready` with `Acquire`, snapshots generation (must be even),
//!   copies/validates digest, then re-checks generation — reject on mismatch
//!   (publisher raced a second publish).
//! - Crash cleanup: writer always `shm_unlink`s on `Drop`; `create` recovers
//!   from orphaned segments left by a previous crash.

use memmap2::{Mmap, MmapMut, MmapOptions};
use serde::{Deserialize, Serialize};
use sha3::{Digest, Sha3_256};
use std::ffi::CString;
use std::fs::File;
use std::io;
use std::os::fd::{AsRawFd, FromRawFd};
use std::sync::atomic::{AtomicU32, Ordering, fence};
use thiserror::Error;

/// On-disk / in-memory format version. Bump when the header layout changes.
pub const SHM_FORMAT_VERSION: u16 = 2;

const MAGIC: &[u8; 8] = b"EIRASHM\0";
const HEADER_LEN: usize = 64;
const VERSION_OFFSET: usize = 8;
const FLAGS_OFFSET: usize = 10;
const GENERATION_OFFSET: usize = 12;
const LENGTH_OFFSET: usize = 16;
const DIGEST_OFFSET: usize = 24;
const READY_OFFSET: usize = 56;
const READY: u32 = 1;

/// POSIX shm object mode: owner read/write only (no group/other).
const SHM_MODE: libc::mode_t = 0o600;

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct SharedMemoryDescriptor {
    pub name: String,
    pub payload_len: usize,
    pub sha3_256: String,
    /// Format version the writer published under (must match [`SHM_FORMAT_VERSION`]).
    #[serde(default = "default_descriptor_version")]
    pub format_version: u16,
    /// Generation observed at publish time (even). Readers may use this as a hint.
    #[serde(default)]
    pub generation: u32,
}

fn default_descriptor_version() -> u16 {
    SHM_FORMAT_VERSION
}

#[derive(Debug, Error)]
pub enum SharedMemoryError {
    #[error("invalid POSIX shared-memory name")]
    InvalidName,
    #[error("payload size {actual} exceeds capacity {capacity}")]
    Capacity { actual: usize, capacity: usize },
    #[error("shared-memory segment is not ready")]
    NotReady,
    #[error("shared-memory header is invalid")]
    InvalidHeader,
    #[error("shared-memory format version mismatch: found {found}, expected {expected}")]
    VersionMismatch { found: u16, expected: u16 },
    #[error("shared-memory payload digest mismatch")]
    DigestMismatch,
    #[error("shared-memory generation race detected (publisher rewrote segment)")]
    GenerationRace,
    #[error("shared-memory I/O failure: {0}")]
    Io(#[from] io::Error),
}

fn validate_name(name: &str) -> Result<CString, SharedMemoryError> {
    let valid = name.starts_with('/')
        && name.len() > 1
        && name.len() <= 200
        && name[1..]
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'_' | b'-'));
    if !valid {
        return Err(SharedMemoryError::InvalidName);
    }
    CString::new(name).map_err(|_| SharedMemoryError::InvalidName)
}

fn digest(payload: &[u8]) -> [u8; 32] {
    Sha3_256::digest(payload).into()
}

fn digest_hex(value: &[u8; 32]) -> String {
    value.iter().map(|byte| format!("{byte:02x}")).collect()
}

fn write_u16(target: &mut [u8], value: u16) {
    target.copy_from_slice(&value.to_le_bytes());
}

fn write_u64(target: &mut [u8], value: u64) {
    target.copy_from_slice(&value.to_le_bytes());
}

fn read_u16(source: &[u8]) -> u16 {
    u16::from_le_bytes(source.try_into().expect("two-byte header field"))
}

fn read_u64(source: &[u8]) -> u64 {
    u64::from_le_bytes(source.try_into().expect("eight-byte header field"))
}

fn ready_atomic(bytes: &[u8]) -> &AtomicU32 {
    let pointer = bytes.as_ptr();
    // SAFETY: mmap is page-aligned; READY_OFFSET is 4-byte aligned; the segment
    // remains mapped for the lifetime of the returned reference.
    unsafe { &*pointer.add(READY_OFFSET).cast::<AtomicU32>() }
}

fn generation_atomic(bytes: &[u8]) -> &AtomicU32 {
    let pointer = bytes.as_ptr();
    // SAFETY: same alignment guarantees as ready_atomic.
    unsafe { &*pointer.add(GENERATION_OFFSET).cast::<AtomicU32>() }
}

/// Unlink a POSIX shm object by name. Idempotent — ignores ENOENT.
pub fn unlink_segment(name: &str) -> Result<(), SharedMemoryError> {
    let c_name = validate_name(name)?;
    // SAFETY: c_name is a valid NUL-terminated POSIX shm identifier.
    let rc = unsafe { libc::shm_unlink(c_name.as_ptr()) };
    if rc == 0 {
        return Ok(());
    }
    let err = io::Error::last_os_error();
    if err.raw_os_error() == Some(libc::ENOENT) {
        Ok(())
    } else {
        Err(err.into())
    }
}

/// Apply owner-only permissions on an open shm fd (defense in depth vs umask).
fn enforce_owner_mode(fd: libc::c_int) -> io::Result<()> {
    // SAFETY: fd is a live descriptor we own; fchmod is safe for any open fd.
    let rc = unsafe { libc::fchmod(fd, SHM_MODE) };
    if rc == 0 {
        Ok(())
    } else {
        Err(io::Error::last_os_error())
    }
}

pub struct SharedMemoryWriter {
    name: String,
    map: MmapMut,
    payload_capacity: usize,
    /// True once create succeeded — Drop must unlink for crash-cleanup contract.
    owns_segment: bool,
}

impl SharedMemoryWriter {
    /// Create a new exclusive POSIX shm segment with owner-only mode (0600).
    ///
    /// If a leftover segment from a crashed process exists, it is unlinked once
    /// and creation is retried (crash cleanup).
    pub fn create(
        name: impl Into<String>,
        payload_capacity: usize,
    ) -> Result<Self, SharedMemoryError> {
        let name = name.into();
        let c_name = validate_name(&name)?;
        let total_len =
            HEADER_LEN
                .checked_add(payload_capacity)
                .ok_or(SharedMemoryError::Capacity {
                    actual: payload_capacity,
                    capacity: usize::MAX - HEADER_LEN,
                })?;

        let file = match open_exclusive(&c_name) {
            Ok(file) => file,
            Err(err) if err.raw_os_error() == Some(libc::EEXIST) => {
                // Crash cleanup: previous writer may have died without Drop.
                unlink_segment(&name)?;
                open_exclusive(&c_name)?
            }
            Err(err) => return Err(err.into()),
        };

        if let Err(error) = enforce_owner_mode(file.as_raw_fd()) {
            let _ = unlink_segment(&name);
            return Err(error.into());
        }
        if let Err(error) = file.set_len(total_len as u64) {
            let _ = unlink_segment(&name);
            return Err(error.into());
        }

        // SAFETY: we own the shm object, fixed its size, and will unlink on Drop.
        let mut map = match unsafe { MmapOptions::new().len(total_len).map_mut(&file) } {
            Ok(map) => map,
            Err(error) => {
                let _ = unlink_segment(&name);
                return Err(error.into());
            }
        };

        // Explicit PROT_READ|PROT_WRITE mapping for the writer only.
        map[..HEADER_LEN].fill(0);
        map[..MAGIC.len()].copy_from_slice(MAGIC);
        write_u16(
            &mut map[VERSION_OFFSET..VERSION_OFFSET + 2],
            SHM_FORMAT_VERSION,
        );
        write_u16(&mut map[FLAGS_OFFSET..FLAGS_OFFSET + 2], 0);
        generation_atomic(&map).store(0, Ordering::Relaxed);
        ready_atomic(&map).store(0, Ordering::Relaxed);

        Ok(Self {
            name,
            map,
            payload_capacity,
            owns_segment: true,
        })
    }

    pub fn payload_capacity(&self) -> usize {
        self.payload_capacity
    }

    pub fn name(&self) -> &str {
        &self.name
    }

    /// Publish a payload into the single-slot ring.
    ///
    /// Protocol (ringbuffer-race safe):
    /// 1. `ready = 0` (Relaxed) — readers must fail `NotReady`.
    /// 2. generation++ to odd — marks "write in progress".
    /// 3. write payload, length, digest.
    /// 4. generation++ to even — marks "stable snapshot".
    /// 5. `fence(Release)` + `ready = 1` (Release).
    pub fn publish(&mut self, payload: &[u8]) -> Result<SharedMemoryDescriptor, SharedMemoryError> {
        if payload.len() > self.payload_capacity {
            return Err(SharedMemoryError::Capacity {
                actual: payload.len(),
                capacity: self.payload_capacity,
            });
        }

        // Step 1: withdraw the slot from readers.
        ready_atomic(&self.map).store(0, Ordering::Relaxed);
        fence(Ordering::SeqCst);

        // Step 2: odd generation = write in progress.
        let previous_generation = generation_atomic(&self.map).fetch_add(1, Ordering::AcqRel);
        let writing_gen = previous_generation.wrapping_add(1);
        debug_assert!(writing_gen % 2 == 1);

        // Step 3: payload + metadata.
        self.map[HEADER_LEN..HEADER_LEN + payload.len()].copy_from_slice(payload);
        // Clear any previous tail so capacity leftovers cannot leak.
        if payload.len() < self.payload_capacity {
            self.map[HEADER_LEN + payload.len()..HEADER_LEN + self.payload_capacity].fill(0);
        }
        let payload_digest = digest(payload);
        write_u64(
            &mut self.map[LENGTH_OFFSET..LENGTH_OFFSET + 8],
            payload.len() as u64,
        );
        self.map[DIGEST_OFFSET..DIGEST_OFFSET + 32].copy_from_slice(&payload_digest);
        write_u16(
            &mut self.map[VERSION_OFFSET..VERSION_OFFSET + 2],
            SHM_FORMAT_VERSION,
        );

        // Step 4: even generation = stable.
        let stable_gen = generation_atomic(&self.map).fetch_add(1, Ordering::AcqRel);
        let published_gen = stable_gen.wrapping_add(1);
        debug_assert!(published_gen % 2 == 0);

        // Step 5: publish.
        fence(Ordering::Release);
        ready_atomic(&self.map).store(READY, Ordering::Release);

        Ok(SharedMemoryDescriptor {
            name: self.name.clone(),
            payload_len: payload.len(),
            sha3_256: digest_hex(&payload_digest),
            format_version: SHM_FORMAT_VERSION,
            generation: published_gen,
        })
    }

    pub fn payload(&self) -> &[u8] {
        let length = read_u64(&self.map[LENGTH_OFFSET..LENGTH_OFFSET + 8]) as usize;
        &self.map[HEADER_LEN..HEADER_LEN + length.min(self.payload_capacity)]
    }
}

fn open_exclusive(c_name: &CString) -> io::Result<File> {
    // SAFETY: c_name is NUL-terminated; flags/mode are valid for shm_open.
    let descriptor = unsafe {
        libc::shm_open(
            c_name.as_ptr(),
            libc::O_CREAT | libc::O_EXCL | libc::O_RDWR | libc::O_CLOEXEC,
            SHM_MODE,
        )
    };
    if descriptor < 0 {
        return Err(io::Error::last_os_error());
    }
    // SAFETY: shm_open returned an owned file descriptor.
    Ok(unsafe { File::from_raw_fd(descriptor) })
}

impl Drop for SharedMemoryWriter {
    fn drop(&mut self) {
        if !self.owns_segment {
            return;
        }
        // Best-effort: mark not-ready before unlink so concurrent readers fail closed.
        ready_atomic(&self.map).store(0, Ordering::Release);
        let _ = unlink_segment(&self.name);
        self.owns_segment = false;
    }
}

pub struct SharedMemoryReader {
    map: Mmap,
    payload_len: usize,
    generation: u32,
}

impl SharedMemoryReader {
    /// Open a published segment read-only (`PROT_READ` only via `Mmap`).
    pub fn open(descriptor: &SharedMemoryDescriptor) -> Result<Self, SharedMemoryError> {
        if descriptor.format_version != SHM_FORMAT_VERSION {
            return Err(SharedMemoryError::VersionMismatch {
                found: descriptor.format_version,
                expected: SHM_FORMAT_VERSION,
            });
        }

        let c_name = validate_name(&descriptor.name)?;
        // SAFETY: c_name is NUL-terminated; O_RDONLY mapping is intentional.
        let raw_descriptor =
            unsafe { libc::shm_open(c_name.as_ptr(), libc::O_RDONLY | libc::O_CLOEXEC, 0) };
        if raw_descriptor < 0 {
            return Err(io::Error::last_os_error().into());
        }
        // SAFETY: shm_open returned an owned file descriptor.
        let file = unsafe { File::from_raw_fd(raw_descriptor) };
        let total_len = usize::try_from(file.metadata()?.len())
            .map_err(|_| SharedMemoryError::InvalidHeader)?;
        if total_len < HEADER_LEN {
            return Err(SharedMemoryError::InvalidHeader);
        }

        // SAFETY: segment size was fixed by the writer; we map read-only.
        let map = unsafe { MmapOptions::new().len(total_len).map(&file)? };

        // Magic
        if &map[..MAGIC.len()] != MAGIC {
            return Err(SharedMemoryError::InvalidHeader);
        }

        // Versioning — reject unknown formats fail-closed.
        let found_version = read_u16(&map[VERSION_OFFSET..VERSION_OFFSET + 2]);
        if found_version != SHM_FORMAT_VERSION {
            return Err(SharedMemoryError::VersionMismatch {
                found: found_version,
                expected: SHM_FORMAT_VERSION,
            });
        }

        // Ready flag (Acquire pairs with writer's Release).
        if ready_atomic(&map).load(Ordering::Acquire) != READY {
            return Err(SharedMemoryError::NotReady);
        }

        // Snapshot generation — must be even (stable).
        let generation = generation_atomic(&map).load(Ordering::Acquire);
        if generation % 2 != 0 {
            return Err(SharedMemoryError::GenerationRace);
        }
        if descriptor.generation != 0 && descriptor.generation != generation {
            // Descriptor from a different publish epoch.
            return Err(SharedMemoryError::GenerationRace);
        }

        let payload_len = usize::try_from(read_u64(&map[LENGTH_OFFSET..LENGTH_OFFSET + 8]))
            .map_err(|_| SharedMemoryError::InvalidHeader)?;
        if payload_len > total_len - HEADER_LEN || payload_len != descriptor.payload_len {
            return Err(SharedMemoryError::InvalidHeader);
        }

        let header_digest: [u8; 32] = map[DIGEST_OFFSET..DIGEST_OFFSET + 32]
            .try_into()
            .expect("fixed-size digest field");
        let actual_digest = digest(&map[HEADER_LEN..HEADER_LEN + payload_len]);
        if actual_digest != header_digest || digest_hex(&actual_digest) != descriptor.sha3_256 {
            return Err(SharedMemoryError::DigestMismatch);
        }

        // Re-check generation + ready after digest (ABA / ringbuffer race).
        fence(Ordering::Acquire);
        let generation_after = generation_atomic(&map).load(Ordering::Acquire);
        if generation_after != generation || ready_atomic(&map).load(Ordering::Acquire) != READY {
            return Err(SharedMemoryError::GenerationRace);
        }

        Ok(Self {
            map,
            payload_len,
            generation,
        })
    }

    pub fn payload(&self) -> &[u8] {
        &self.map[HEADER_LEN..HEADER_LEN + self.payload_len]
    }

    pub fn generation(&self) -> u32 {
        self.generation
    }
}

#[cfg(test)]
mod tests {
    use super::{
        SHM_FORMAT_VERSION, SharedMemoryDescriptor, SharedMemoryError, SharedMemoryReader,
        SharedMemoryWriter, unlink_segment,
    };

    fn unique_name(tag: &str) -> String {
        format!(
            "/eira_test_{}_{}_{}",
            tag,
            std::process::id(),
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        )
    }

    #[test]
    fn transfers_payload_without_reader_copy() {
        let name = unique_name("xfer");
        let mut writer = SharedMemoryWriter::create(&name, 4096).unwrap();
        let descriptor = writer.publish(b"large immutable payload").unwrap();
        assert_eq!(descriptor.format_version, SHM_FORMAT_VERSION);
        assert_eq!(descriptor.generation % 2, 0);
        let reader = SharedMemoryReader::open(&descriptor).unwrap();
        assert_eq!(reader.payload(), b"large immutable payload");
        assert_eq!(reader.generation(), descriptor.generation);
    }

    #[test]
    fn rejects_version_mismatch_on_descriptor() {
        let name = unique_name("ver");
        let mut writer = SharedMemoryWriter::create(&name, 64).unwrap();
        let mut descriptor = writer.publish(b"hi").unwrap();
        descriptor.format_version = SHM_FORMAT_VERSION.wrapping_add(1);
        let err = SharedMemoryReader::open(&descriptor)
            .err()
            .expect("invalid descriptor must be rejected");
        assert!(matches!(err, SharedMemoryError::VersionMismatch { .. }));
    }

    #[test]
    fn rejects_digest_mismatch() {
        let name = unique_name("dig");
        let mut writer = SharedMemoryWriter::create(&name, 64).unwrap();
        let mut descriptor = writer.publish(b"hi").unwrap();
        descriptor.sha3_256 = "00".repeat(32);
        let err = SharedMemoryReader::open(&descriptor).unwrap_err();
        assert!(matches!(err, SharedMemoryError::DigestMismatch));
    }

    #[test]
    fn crash_cleanup_recovers_orphaned_segment() {
        let name = unique_name("crash");
        let writer = SharedMemoryWriter::create(&name, 32).unwrap();
        // Simulate crash: forget Drop (leak the writer) then force unlink path via create.
        std::mem::forget(writer);
        // Second create must succeed by unlinking the orphan first.
        let mut writer2 = SharedMemoryWriter::create(&name, 32).unwrap();
        let descriptor = writer2.publish(b"after-crash").unwrap();
        let reader = SharedMemoryReader::open(&descriptor).unwrap();
        assert_eq!(reader.payload(), b"after-crash");
    }

    #[test]
    fn republish_bumps_generation_and_invalidates_stale_descriptor() {
        let name = unique_name("race");
        let mut writer = SharedMemoryWriter::create(&name, 128).unwrap();
        let first = writer.publish(b"first").unwrap();
        let second = writer.publish(b"second-payload").unwrap();
        assert_ne!(first.generation, second.generation);
        // Stale descriptor must fail closed on generation race.
        let err = SharedMemoryReader::open(&first)
            .err()
            .expect("stale descriptor must be rejected");
        assert!(matches!(
            err,
            SharedMemoryError::GenerationRace | SharedMemoryError::DigestMismatch
        ));
        let reader = SharedMemoryReader::open(&second).unwrap();
        assert_eq!(reader.payload(), b"second-payload");
    }

    #[test]
    fn not_ready_before_publish() {
        let name = unique_name("ready");
        let writer = SharedMemoryWriter::create(&name, 16).unwrap();
        let descriptor = SharedMemoryDescriptor {
            name: writer.name().to_owned(),
            payload_len: 0,
            sha3_256: "00".repeat(32),
            format_version: SHM_FORMAT_VERSION,
            generation: 0,
        };
        let err = SharedMemoryReader::open(&descriptor).unwrap_err();
        assert!(matches!(err, SharedMemoryError::NotReady));
    }

    #[test]
    fn unlink_segment_is_idempotent() {
        let name = unique_name("unlink");
        unlink_segment(&name).unwrap();
        unlink_segment(&name).unwrap();
    }
}
