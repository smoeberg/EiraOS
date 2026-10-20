#![deny(warnings)]
#![deny(unsafe_op_in_unsafe_fn)]

//! Bounded asynchronous JSON-RPC over Unix domain sockets.
//!
//! Inbound frames are parsed with zero-copy `serde_json::value::RawValue` borrows
//! into the frame buffer (no intermediate `Value` tree for params/id).
//! Serialization of requests and responses is hard-capped by
//! [`IpcConfig::max_frame_bytes`] via a fail-closed bounded writer (IPC-01/03).

pub mod shm;

use serde::{Deserialize, Serialize, de::DeserializeOwned};
use serde_json::{Value, value::RawValue};
use std::io::{self, Write};
use std::os::unix::fs::{FileTypeExt, PermissionsExt};
use std::path::{Path, PathBuf};
use std::sync::Arc;
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::Duration;
use thiserror::Error;
use tokio::io::{AsyncBufRead, AsyncBufReadExt, AsyncWriteExt, BufReader};
use tokio::net::{UnixListener, UnixStream};
use tokio::sync::{Semaphore, watch};
use tokio::time::timeout;

const JSON_RPC_VERSION: &str = "2.0";
const FORBIDDEN_MODE_MASK: u32 = 0o002;

#[derive(Debug, Clone)]
pub struct IpcConfig {
    pub max_frame_bytes: usize,
    pub read_buffer_bytes: usize,
    /// Client-side bound on connect + write + read of one RPC call.
    ///
    /// Expiry returns [`IpcError::Timeout`] and does **not** roll back work the
    /// server may already have started after accepting the request (IPC-05).
    pub request_timeout: Duration,
    /// Deadline for receiving one complete inbound frame on the server.
    pub connection_read_timeout: Duration,
    pub socket_mode: u32,
    /// Maximum concurrent accepted connections (IPC-02).
    pub max_connections: usize,
}

impl Default for IpcConfig {
    fn default() -> Self {
        Self {
            max_frame_bytes: 16 * 1024 * 1024,
            read_buffer_bytes: 64 * 1024,
            request_timeout: Duration::from_secs(10),
            connection_read_timeout: Duration::from_secs(10),
            socket_mode: 0o660,
            max_connections: 64,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct RpcErrorObject {
    pub code: i64,
    pub message: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub data: Option<Value>,
}

impl RpcErrorObject {
    pub fn new(code: i64, message: impl Into<String>) -> Self {
        Self {
            code,
            message: message.into(),
            data: None,
        }
    }
}

#[derive(Debug, Error)]
pub enum IpcError {
    #[error("I/O failure: {0}")]
    Io(#[from] io::Error),
    #[error("invalid JSON: {0}")]
    Json(#[from] serde_json::Error),
    #[error("frame exceeds {0} bytes")]
    FrameTooLarge(usize),
    #[error("peer closed the socket before completing a frame")]
    TruncatedFrame,
    #[error("JSON-RPC protocol error: {0}")]
    Protocol(String),
    #[error("JSON-RPC request timed out (server may still process the request; no cancellation)")]
    Timeout,
    #[error("remote JSON-RPC error {0:?}")]
    Remote(RpcErrorObject),
    #[error("refusing to replace non-socket path: {0}")]
    UnsafeSocketPath(PathBuf),
    #[error("socket mode 0o{0:o} is too permissive (other-writable)")]
    UnsafeSocketMode(u32),
    #[error("parent directory is world-writable: {0}")]
    UnsafeParentDirectory(PathBuf),
    #[error("connection limit reached ({0})")]
    ConnectionLimit(usize),
}

struct BoundedWriter<'a> {
    buf: &'a mut Vec<u8>,
    max: usize,
    overflowed: bool,
}

impl<'a> BoundedWriter<'a> {
    fn new(buf: &'a mut Vec<u8>, max: usize) -> Self {
        Self {
            buf,
            max,
            overflowed: false,
        }
    }

    fn finish(self) -> Result<(), IpcError> {
        if self.overflowed {
            Err(IpcError::FrameTooLarge(self.max))
        } else {
            Ok(())
        }
    }
}

impl Write for BoundedWriter<'_> {
    fn write(&mut self, data: &[u8]) -> io::Result<usize> {
        if self.overflowed {
            return Ok(data.len());
        }
        if self.buf.len().saturating_add(data.len()) > self.max {
            self.overflowed = true;
            self.buf.clear();
            return Ok(data.len());
        }
        self.buf.extend_from_slice(data);
        Ok(data.len())
    }

    fn flush(&mut self) -> io::Result<()> {
        Ok(())
    }
}

#[derive(Deserialize)]
struct BorrowedRequest<'a> {
    jsonrpc: &'a str,
    #[serde(borrow)]
    id: &'a RawValue,
    method: &'a str,
    #[serde(borrow)]
    params: Option<&'a RawValue>,
}

#[derive(Serialize)]
struct BorrowedSuccess<'a> {
    jsonrpc: &'static str,
    id: &'a RawValue,
    result: &'a RawValue,
}

#[derive(Serialize)]
struct BorrowedError<'a> {
    jsonrpc: &'static str,
    id: &'a RawValue,
    error: &'a RpcErrorObject,
}

#[derive(Serialize)]
struct ClientRequest<'a, P: ?Sized> {
    jsonrpc: &'static str,
    id: u64,
    method: &'a str,
    params: &'a P,
}

#[derive(Deserialize)]
struct ClientResponse<T> {
    jsonrpc: String,
    id: u64,
    result: Option<T>,
    error: Option<RpcErrorObject>,
}

pub trait RpcHandler: Send + Sync + 'static {
    fn handle(
        &self,
        method: &str,
        params: Option<&RawValue>,
    ) -> Result<Box<RawValue>, RpcErrorObject>;
}

impl<F> RpcHandler for F
where
    F: Fn(&str, Option<&RawValue>) -> Result<Box<RawValue>, RpcErrorObject> + Send + Sync + 'static,
{
    fn handle(
        &self,
        method: &str,
        params: Option<&RawValue>,
    ) -> Result<Box<RawValue>, RpcErrorObject> {
        self(method, params)
    }
}

struct SocketCleanup {
    path: PathBuf,
    inode: u64,
    device: u64,
}

impl Drop for SocketCleanup {
    fn drop(&mut self) {
        if let Ok(metadata) = std::fs::symlink_metadata(&self.path) {
            use std::os::unix::fs::MetadataExt;
            if metadata.file_type().is_socket()
                && metadata.ino() == self.inode
                && metadata.dev() == self.device
            {
                let _ = std::fs::remove_file(&self.path);
            }
        }
    }
}

fn validate_socket_mode(mode: u32) -> Result<(), IpcError> {
    if mode & FORBIDDEN_MODE_MASK != 0 {
        return Err(IpcError::UnsafeSocketMode(mode));
    }
    Ok(())
}

fn validate_parent_directory(path: &Path) -> Result<(), IpcError> {
    let Some(parent) = path.parent() else {
        return Ok(());
    };
    if parent.as_os_str().is_empty() {
        return Ok(());
    }
    let metadata = match std::fs::metadata(parent) {
        Ok(metadata) => metadata,
        Err(error) if error.kind() == io::ErrorKind::NotFound => return Ok(()),
        Err(error) => return Err(error.into()),
    };
    if metadata.permissions().mode() & 0o002 != 0 {
        return Err(IpcError::UnsafeParentDirectory(parent.to_owned()));
    }
    Ok(())
}

fn prepare_socket_path(path: &Path) -> Result<(), IpcError> {
    match std::fs::symlink_metadata(path) {
        Ok(metadata) if metadata.file_type().is_socket() => {
            std::fs::remove_file(path)?;
            Ok(())
        }
        Ok(_) => Err(IpcError::UnsafeSocketPath(path.to_owned())),
        Err(error) if error.kind() == io::ErrorKind::NotFound => Ok(()),
        Err(error) => Err(error.into()),
    }
}

fn validate_request_id(id: &RawValue) -> Result<(), IpcError> {
    let raw = id.get().trim();
    if raw == "null" {
        return Ok(());
    }
    if raw.starts_with('"') {
        return Ok(());
    }
    let bytes = raw.as_bytes();
    if bytes.is_empty() {
        return Err(IpcError::Protocol(
            "JSON-RPC id must be string, number, or null".to_owned(),
        ));
    }
    let mut idx = 0;
    if bytes[0] == b'-' {
        idx = 1;
        if bytes.len() == 1 {
            return Err(IpcError::Protocol(
                "JSON-RPC id must be string, number, or null".to_owned(),
            ));
        }
    }
    let mut saw_digit = false;
    let mut saw_dot = false;
    for &byte in &bytes[idx..] {
        match byte {
            b'0'..=b'9' => saw_digit = true,
            b'.' if !saw_dot => saw_dot = true,
            _ => {
                return Err(IpcError::Protocol(
                    "JSON-RPC id must be string, number, or null".to_owned(),
                ));
            }
        }
    }
    if saw_digit {
        Ok(())
    } else {
        Err(IpcError::Protocol(
            "JSON-RPC id must be string, number, or null".to_owned(),
        ))
    }
}

async fn read_frame<R: AsyncBufRead + Unpin>(
    reader: &mut R,
    frame: &mut Vec<u8>,
    max_frame_bytes: usize,
) -> Result<bool, IpcError> {
    frame.clear();
    loop {
        let (consumed, complete) = {
            let available = reader.fill_buf().await?;
            if available.is_empty() {
                if frame.is_empty() {
                    return Ok(false);
                }
                return Err(IpcError::TruncatedFrame);
            }
            if let Some(position) = available.iter().position(|byte| *byte == b'\n') {
                let consumed = position + 1;
                if frame.len() + position > max_frame_bytes {
                    return Err(IpcError::FrameTooLarge(max_frame_bytes));
                }
                frame.extend_from_slice(&available[..position]);
                (consumed, true)
            } else {
                if frame.len() + available.len() > max_frame_bytes {
                    return Err(IpcError::FrameTooLarge(max_frame_bytes));
                }
                frame.extend_from_slice(available);
                (available.len(), false)
            }
        };
        reader.consume(consumed);
        if complete {
            return Ok(true);
        }
    }
}

fn encode_response<H: RpcHandler>(
    handler: &H,
    frame: &[u8],
    output: &mut Vec<u8>,
    max_frame_bytes: usize,
) -> Result<(), IpcError> {
    output.clear();
    let request: BorrowedRequest<'_> = serde_json::from_slice(frame)?;
    if request.jsonrpc != JSON_RPC_VERSION || request.method.is_empty() {
        return Err(IpcError::Protocol(
            "request must use JSON-RPC 2.0 and a non-empty method".to_owned(),
        ));
    }
    validate_request_id(request.id)?;

    let mut writer = BoundedWriter::new(output, max_frame_bytes);
    match handler.handle(request.method, request.params) {
        Ok(result) => {
            serde_json::to_writer(
                &mut writer,
                &BorrowedSuccess {
                    jsonrpc: JSON_RPC_VERSION,
                    id: request.id,
                    result: &result,
                },
            )?;
        }
        Err(error) => {
            serde_json::to_writer(
                &mut writer,
                &BorrowedError {
                    jsonrpc: JSON_RPC_VERSION,
                    id: request.id,
                    error: &error,
                },
            )?;
        }
    }
    writer.write_all(b"\n")?;
    writer.finish()?;
    Ok(())
}

async fn serve_connection<H: RpcHandler>(
    stream: UnixStream,
    handler: Arc<H>,
    config: IpcConfig,
    _permit: tokio::sync::OwnedSemaphorePermit,
) -> Result<(), IpcError> {
    let (read_half, mut write_half) = stream.into_split();
    let mut reader = BufReader::with_capacity(config.read_buffer_bytes, read_half);
    let mut frame = Vec::with_capacity(config.read_buffer_bytes.min(config.max_frame_bytes));
    let mut response = Vec::with_capacity(config.read_buffer_bytes.min(config.max_frame_bytes));
    loop {
        let has_frame = timeout(
            config.connection_read_timeout,
            read_frame(&mut reader, &mut frame, config.max_frame_bytes),
        )
        .await
        .map_err(|_| IpcError::Timeout)??;
        if !has_frame {
            return Ok(());
        }
        encode_response(
            handler.as_ref(),
            &frame,
            &mut response,
            config.max_frame_bytes,
        )?;
        write_half.write_all(&response).await?;
    }
}

pub async fn serve<H: RpcHandler>(
    path: impl AsRef<Path>,
    handler: Arc<H>,
    config: IpcConfig,
    mut shutdown: watch::Receiver<bool>,
) -> Result<(), IpcError> {
    validate_socket_mode(config.socket_mode)?;
    let path = path.as_ref().to_owned();
    if let Some(parent) = path.parent() {
        if !parent.as_os_str().is_empty() {
            std::fs::create_dir_all(parent)?;
        }
    }
    validate_parent_directory(&path)?;
    prepare_socket_path(&path)?;
    let listener = UnixListener::bind(&path)?;
    std::fs::set_permissions(&path, std::fs::Permissions::from_mode(config.socket_mode))?;

    use std::os::unix::fs::MetadataExt;
    let metadata = std::fs::symlink_metadata(&path)?;
    let cleanup = SocketCleanup {
        path: path.clone(),
        inode: metadata.ino(),
        device: metadata.dev(),
    };

    let permits = Arc::new(Semaphore::new(config.max_connections.max(1)));
    let max_connections = config.max_connections.max(1);

    let _cleanup = cleanup;
    loop {
        if *shutdown.borrow() {
            return Ok(());
        }
        tokio::select! {
            changed = shutdown.changed() => {
                if changed.is_err() || *shutdown.borrow() {
                    return Ok(());
                }
            }
            accepted = listener.accept() => {
                let (stream, _) = accepted?;
                let permit = match Arc::clone(&permits).try_acquire_owned() {
                    Ok(permit) => permit,
                    Err(_) => {
                        drop(stream);
                        let _ = max_connections;
                        continue;
                    }
                };
                let connection_handler = Arc::clone(&handler);
                let connection_config = config.clone();
                tokio::spawn(async move {
                    let _ = serve_connection(
                        stream,
                        connection_handler,
                        connection_config,
                        permit,
                    )
                    .await;
                });
            }
        }
    }
}

#[derive(Clone)]
pub struct UnixRpcClient {
    path: PathBuf,
    config: IpcConfig,
    next_id: Arc<AtomicU64>,
}

impl UnixRpcClient {
    pub fn new(path: impl Into<PathBuf>) -> Self {
        Self::with_config(path, IpcConfig::default())
    }

    pub fn with_config(path: impl Into<PathBuf>, config: IpcConfig) -> Self {
        Self {
            path: path.into(),
            config,
            next_id: Arc::new(AtomicU64::new(1)),
        }
    }

    pub async fn call<P, T>(&self, method: &str, params: &P) -> Result<T, IpcError>
    where
        P: Serialize + ?Sized,
        T: DeserializeOwned,
    {
        let request_id = self.next_id.fetch_add(1, Ordering::Relaxed);
        let operation = async {
            let mut stream = UnixStream::connect(&self.path).await?;
            let mut request = Vec::with_capacity(1024.min(self.config.max_frame_bytes));
            {
                let max_body = self.config.max_frame_bytes.saturating_sub(1);
                let mut writer = BoundedWriter::new(&mut request, max_body);
                serde_json::to_writer(
                    &mut writer,
                    &ClientRequest {
                        jsonrpc: JSON_RPC_VERSION,
                        id: request_id,
                        method,
                        params,
                    },
                )?;
                writer.finish()?;
            }
            request.push(b'\n');
            stream.write_all(&request).await?;
            stream.flush().await?;

            let mut reader = BufReader::with_capacity(self.config.read_buffer_bytes, stream);
            let mut frame = Vec::with_capacity(self.config.read_buffer_bytes);
            if !read_frame(&mut reader, &mut frame, self.config.max_frame_bytes).await? {
                return Err(IpcError::TruncatedFrame);
            }
            let response: ClientResponse<T> = serde_json::from_slice(&frame)?;
            if response.jsonrpc != JSON_RPC_VERSION || response.id != request_id {
                return Err(IpcError::Protocol(
                    "response id/version mismatch".to_owned(),
                ));
            }
            if let Some(error) = response.error {
                return Err(IpcError::Remote(error));
            }
            response.result.ok_or_else(|| {
                IpcError::Protocol("response contains neither result nor error".to_owned())
            })
        };
        timeout(self.config.request_timeout, operation)
            .await
            .map_err(|_| IpcError::Timeout)?
    }
}

#[cfg(test)]
mod tests {
    use super::{
        BoundedWriter, IpcConfig, IpcError, RpcErrorObject, UnixRpcClient, encode_response,
        read_frame, serve, validate_request_id, validate_socket_mode,
    };
    use serde_json::{Value, value::RawValue};
    use std::io::Write;
    use std::sync::Arc;
    use std::time::Duration;
    use tempfile::tempdir;
    use tokio::io::BufReader;
    use tokio::sync::watch;

    #[tokio::test]
    async fn client_and_server_exchange_borrowed_json() {
        let directory = tempdir().unwrap();
        let path = directory.path().join("rpc.sock");
        let handler = Arc::new(
            |method: &str, params: Option<&RawValue>| -> Result<Box<RawValue>, RpcErrorObject> {
                if method != "echo" {
                    return Err(RpcErrorObject::new(-32601, "unknown method"));
                }
                RawValue::from_string(
                    params.map_or_else(|| "null".to_owned(), |value| value.get().to_owned()),
                )
                .map_err(|error| RpcErrorObject::new(-32602, error.to_string()))
            },
        );
        let (shutdown_tx, shutdown_rx) = watch::channel(false);
        let server_path = path.clone();
        let task = tokio::spawn(async move {
            serve(server_path, handler, IpcConfig::default(), shutdown_rx).await
        });
        while !path.exists() {
            tokio::time::sleep(Duration::from_millis(5)).await;
        }

        let result: Value = UnixRpcClient::new(path)
            .call("echo", &serde_json::json!({"value": 42}))
            .await
            .unwrap();
        assert_eq!(result, serde_json::json!({"value": 42}));
        shutdown_tx.send(true).unwrap();
        let _ = task.await;
    }

    #[test]
    fn ipc01_oversized_response_is_bounded() {
        let large = "x".repeat(64);
        let handler =
            |_method: &str, _params: Option<&RawValue>| -> Result<Box<RawValue>, RpcErrorObject> {
                RawValue::from_string(format!("\"{large}\""))
                    .map_err(|e| RpcErrorObject::new(-32603, e.to_string()))
            };
        let request = br#"{"jsonrpc":"2.0","id":1,"method":"x","params":null}"#;
        let mut output = Vec::new();
        let max = 32;
        let err = encode_response(&handler, request, &mut output, max).unwrap_err();
        assert!(matches!(err, IpcError::FrameTooLarge(32)));
        assert!(output.len() <= max, "output grew to {}", output.len());
    }

    #[test]
    fn ipc03_bounded_writer_caps_allocation() {
        let mut buf = Vec::new();
        let mut writer = BoundedWriter::new(&mut buf, 8);
        writer.write_all(b"1234567890").unwrap();
        let err = writer.finish().unwrap_err();
        assert!(matches!(err, IpcError::FrameTooLarge(8)));
        assert!(buf.is_empty() || buf.len() <= 8);
    }

    #[tokio::test]
    async fn ipc02_incomplete_frame_times_out() {
        let mut reader = BufReader::new(&b"{\"jsonrpc\":\"2.0\""[..]);
        let mut frame = Vec::new();
        let result = tokio::time::timeout(
            Duration::from_millis(50),
            read_frame(&mut reader, &mut frame, 1024),
        )
        .await;
        match result {
            Err(_) => {}
            Ok(Err(IpcError::TruncatedFrame)) => {}
            Ok(other) => panic!("unexpected {other:?}"),
        }
    }

    #[test]
    fn ipc04_rejects_world_writable_mode() {
        assert!(matches!(
            validate_socket_mode(0o666),
            Err(IpcError::UnsafeSocketMode(0o666))
        ));
        assert!(validate_socket_mode(0o660).is_ok());
        assert!(validate_socket_mode(0o600).is_ok());
    }

    #[tokio::test]
    async fn ipc04_refuses_non_socket_path() {
        let directory = tempdir().unwrap();
        let path = directory.path().join("not-a-socket");
        std::fs::write(&path, b"file").unwrap();
        let handler = Arc::new(
            |_m: &str, _p: Option<&RawValue>| -> Result<Box<RawValue>, RpcErrorObject> {
                Err(RpcErrorObject::new(-32601, "nope"))
            },
        );
        let (_tx, rx) = watch::channel(false);
        let err = serve(path, handler, IpcConfig::default(), rx)
            .await
            .unwrap_err();
        assert!(matches!(err, IpcError::UnsafeSocketPath(_)), "{err:?}");
    }

    #[test]
    fn ipc06_request_id_shape() {
        let string_id = RawValue::from_string("\"abc\"".into()).unwrap();
        let number_id = RawValue::from_string("7".into()).unwrap();
        let null_id = RawValue::from_string("null".into()).unwrap();
        let object_id = RawValue::from_string("{\"x\":1}".into()).unwrap();
        let array_id = RawValue::from_string("[1]".into()).unwrap();
        assert!(validate_request_id(&string_id).is_ok());
        assert!(validate_request_id(&number_id).is_ok());
        assert!(validate_request_id(&null_id).is_ok());
        assert!(matches!(
            validate_request_id(&object_id),
            Err(IpcError::Protocol(_))
        ));
        assert!(matches!(
            validate_request_id(&array_id),
            Err(IpcError::Protocol(_))
        ));
    }

    #[test]
    fn ipc05_timeout_message_documents_semantics() {
        let message = IpcError::Timeout.to_string();
        assert!(message.contains("cancellation") || message.contains("may still"));
    }

    #[tokio::test]
    async fn inbound_frame_too_large() {
        let mut data = vec![b'a'; 64];
        data.push(b'\n');
        let mut reader = BufReader::new(data.as_slice());
        let mut frame = Vec::new();
        let err = read_frame(&mut reader, &mut frame, 16).await.unwrap_err();
        assert!(matches!(err, IpcError::FrameTooLarge(16)));
    }
}
