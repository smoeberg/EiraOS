use memmap2::{Mmap, MmapMut, MmapOptions};
use serde::{Deserialize, Serialize};
use sha3::{Digest, Sha3_256};
use std::ffi::CString;
use std::fs::File;
use std::io;
use std::os::fd::FromRawFd;
use std::sync::atomic::{AtomicU32, Ordering, fence};
use thiserror::Error;

const MAGIC: &[u8; 8] = b"EIRASHM\0";
const VERSION: u16 = 1;
const HEADER_LEN: usize = 64;
const LENGTH_OFFSET: usize = 16;
const DIGEST_OFFSET: usize = 24;
const READY_OFFSET: usize = 56;
const READY: u32 = 1;

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct SharedMemoryDescriptor {
    pub name: String,
    pub payload_len: usize,
    pub sha3_256: String,
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
    #[error("shared-memory payload digest mismatch")]
    DigestMismatch,
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
    // SAFETY: every mmap starts at page alignment, READY_OFFSET is aligned to
    // four bytes, and the segment remains mapped for the returned reference.
    unsafe { &*pointer.add(READY_OFFSET).cast::<AtomicU32>() }
}

pub struct SharedMemoryWriter {
    name: String,
    map: MmapMut,
    payload_capacity: usize,
}

impl SharedMemoryWriter {
    pub fn create(name: impl Into<String>, payload_capacity: usize) -> Result<Self, SharedMemoryError> {
        let name = name.into();
        let c_name = validate_name(&name)?;
        let total_len = HEADER_LEN
            .checked_add(payload_capacity)
            .ok_or(SharedMemoryError::Capacity {
                actual: payload_capacity,
                capacity: usize::MAX - HEADER_LEN,
            })?;
        // SAFETY: c_name is NUL-terminated and mode/flags are valid for shm_open.
        let descriptor = unsafe {
            libc::shm_open(
                c_name.as_ptr(),
                libc::O_CREAT | libc::O_EXCL | libc::O_RDWR | libc::O_CLOEXEC,
                0o600,
            )
        };
        if descriptor < 0 {
            return Err(io::Error::last_os_error().into());
        }
        // SAFETY: shm_open returned an owned file descriptor.
        let file = unsafe { File::from_raw_fd(descriptor) };
        if let Err(error) = file.set_len(total_len as u64) {
            // SAFETY: c_name remains valid and names the segment just created.
            unsafe { libc::shm_unlink(c_name.as_ptr()) };
            return Err(error.into());
        }
        // SAFETY: the writer owns the shared-memory object, fixes its size for
        // the lifetime of this mapping, and unlinks only when the writer drops.
        let mut map = unsafe { MmapOptions::new().len(total_len).map_mut(&file)? };
        map[..HEADER_LEN].fill(0);
        map[..MAGIC.len()].copy_from_slice(MAGIC);
        write_u16(&mut map[8..10], VERSION);
        ready_atomic(&map).store(0, Ordering::Relaxed);
        Ok(Self {
            name,
            map,
            payload_capacity,
        })
    }

    pub fn payload_capacity(&self) -> usize {
        self.payload_capacity
    }

    pub fn publish(
        &mut self,
        payload: &[u8],
    ) -> Result<SharedMemoryDescriptor, SharedMemoryError> {
        if payload.len() > self.payload_capacity {
            return Err(SharedMemoryError::Capacity {
                actual: payload.len(),
                capacity: self.payload_capacity,
            });
        }
        ready_atomic(&self.map).store(0, Ordering::Relaxed);
        self.map[HEADER_LEN..HEADER_LEN + payload.len()].copy_from_slice(payload);
        let payload_digest = digest(payload);
        write_u64(
            &mut self.map[LENGTH_OFFSET..LENGTH_OFFSET + 8],
            payload.len() as u64,
        );
        self.map[DIGEST_OFFSET..DIGEST_OFFSET + 32].copy_from_slice(&payload_digest);
        fence(Ordering::Release);
        ready_atomic(&self.map).store(READY, Ordering::Release);
        Ok(SharedMemoryDescriptor {
            name: self.name.clone(),
            payload_len: payload.len(),
            sha3_256: digest_hex(&payload_digest),
        })
    }

    pub fn payload(&self) -> &[u8] {
        let length = read_u64(&self.map[LENGTH_OFFSET..LENGTH_OFFSET + 8]) as usize;
        &self.map[HEADER_LEN..HEADER_LEN + length.min(self.payload_capacity)]
    }
}

impl Drop for SharedMemoryWriter {
    fn drop(&mut self) {
        if let Ok(name) = validate_name(&self.name) {
            // SAFETY: name is a valid NUL-terminated POSIX shm identifier.
            unsafe { libc::shm_unlink(name.as_ptr()) };
        }
    }
}

pub struct SharedMemoryReader {
    map: Mmap,
    payload_len: usize,
}

impl SharedMemoryReader {
    pub fn open(descriptor: &SharedMemoryDescriptor) -> Result<Self, SharedMemoryError> {
        let c_name = validate_name(&descriptor.name)?;
        // SAFETY: c_name is NUL-terminated and flags are valid for shm_open.
        let raw_descriptor = unsafe { libc::shm_open(c_name.as_ptr(), libc::O_RDONLY | libc::O_CLOEXEC, 0) };
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
        // SAFETY: the writer's protocol fixes the segment size before publish;
        // readers never mutate the mapped bytes.
        let map = unsafe { MmapOptions::new().len(total_len).map(&file)? };
        if &map[..MAGIC.len()] != MAGIC || read_u16(&map[8..10]) != VERSION {
            return Err(SharedMemoryError::InvalidHeader);
        }
        if ready_atomic(&map).load(Ordering::Acquire) != READY {
            return Err(SharedMemoryError::NotReady);
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
        Ok(Self { map, payload_len })
    }

    pub fn payload(&self) -> &[u8] {
        &self.map[HEADER_LEN..HEADER_LEN + self.payload_len]
    }
}

#[cfg(test)]
mod tests {
    use super::{SharedMemoryReader, SharedMemoryWriter};

    #[test]
    fn transfers_payload_without_reader_copy() {
        let name = format!(
            "/eira_test_{}_{}",
            std::process::id(),
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        );
        let mut writer = SharedMemoryWriter::create(name, 4096).unwrap();
        let descriptor = writer.publish(b"large immutable payload").unwrap();
        let reader = SharedMemoryReader::open(&descriptor).unwrap();
        assert_eq!(reader.payload(), b"large immutable payload");
    }
}
