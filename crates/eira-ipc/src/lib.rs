#![deny(warnings)]
#![deny(unsafe_op_in_unsafe_fn)]

pub mod shm;

use serde::{Deserialize, Serialize, de::DeserializeOwned};
use serde_json::{Value, value::RawValue};
use std::io;
use std::os::unix::fs::{FileTypeExt, PermissionsExt};
use std::path::{Path, PathBuf};
use std::sync::Arc;
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::Duration;
use thiserror::Error;
use tokio::io::{AsyncBufRead, AsyncBufReadExt, AsyncWriteExt, BufReader};
use tokio::net::{UnixListener, UnixStream};
use tokio::sync::watch;
use tokio::time::timeout;

const JSON_RPC_VERSION: &str = "2.0";

#[derive(Debug, Clone)]
pub struct IpcConfig {
    pub max_frame_bytes: usize,
    pub read_buffer_bytes: usize,
    pub request_timeout: Duration,
    pub socket_mode: u32,
}

impl Default for IpcConfig {
    fn default() -> Self {
        Self {
            max_frame_bytes: 16 * 1024 * 1024,
            read_buffer_bytes: 64 * 1024,
            request_timeout: Duration::from_secs(10),
            socket_mode: 0o660,
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
    #[error("JSON-RPC request timed out")]
    Timeout,
    #[error("remote JSON-RPC error {0:?}")]
    Remote(RpcErrorObject),
    #[error("refusing to replace non-socket path: {0}")]
    UnsafeSocketPath(PathBuf),
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
    F: Fn(&str, Option<&RawValue>) -> Result<Box<RawValue>, RpcErrorObject>
        + Send
        + Sync
        + 'static,
{
    fn handle(
        &self,
        method: &str,
        params: Option<&RawValue>,
    ) -> Result<Box<RawValue>, RpcErrorObject> {
        self(method, params)
    }
}

struct SocketCleanup(PathBuf);

impl Drop for SocketCleanup {
    fn drop(&mut self) {
        let _ = std::fs::remove_file(&self.0);
    }
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
) -> Result<(), IpcError> {
    output.clear();
    let request: BorrowedRequest<'_> = serde_json::from_slice(frame)?;
    if request.jsonrpc != JSON_RPC_VERSION || request.method.is_empty() {
        return Err(IpcError::Protocol(
            "request must use JSON-RPC 2.0 and a non-empty method".to_owned(),
        ));
    }
    match handler.handle(request.method, request.params) {
        Ok(result) => serde_json::to_writer(
            &mut *output,
            &BorrowedSuccess {
                jsonrpc: JSON_RPC_VERSION,
                id: request.id,
                result: &result,
            },
        )?,
        Err(error) => serde_json::to_writer(
            &mut *output,
            &BorrowedError {
                jsonrpc: JSON_RPC_VERSION,
                id: request.id,
                error: &error,
            },
        )?,
    }
    output.push(b'\n');
    Ok(())
}

async fn serve_connection<H: RpcHandler>(
    stream: UnixStream,
    handler: Arc<H>,
    config: IpcConfig,
) -> Result<(), IpcError> {
    let (read_half, mut write_half) = stream.into_split();
    let mut reader = BufReader::with_capacity(config.read_buffer_bytes, read_half);
    let mut frame = Vec::with_capacity(config.read_buffer_bytes);
    let mut response = Vec::with_capacity(config.read_buffer_bytes);
    while read_frame(&mut reader, &mut frame, config.max_frame_bytes).await? {
        encode_response(handler.as_ref(), &frame, &mut response)?;
        if response.len() > config.max_frame_bytes {
            return Err(IpcError::FrameTooLarge(config.max_frame_bytes));
        }
        write_half.write_all(&response).await?;
    }
    Ok(())
}

pub async fn serve<H: RpcHandler>(
    path: impl AsRef<Path>,
    handler: Arc<H>,
    config: IpcConfig,
    mut shutdown: watch::Receiver<bool>,
) -> Result<(), IpcError> {
    let path = path.as_ref().to_owned();
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent)?;
    }
    prepare_socket_path(&path)?;
    let listener = UnixListener::bind(&path)?;
    std::fs::set_permissions(&path, std::fs::Permissions::from_mode(config.socket_mode))?;
    let _cleanup = SocketCleanup(path);

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
                let connection_handler = Arc::clone(&handler);
                let connection_config = config.clone();
                tokio::spawn(async move {
                    let _ = serve_connection(stream, connection_handler, connection_config).await;
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
            let mut request = Vec::with_capacity(1024);
            serde_json::to_writer(
                &mut request,
                &ClientRequest {
                    jsonrpc: JSON_RPC_VERSION,
                    id: request_id,
                    method,
                    params,
                },
            )?;
            request.push(b'\n');
            if request.len() > self.config.max_frame_bytes {
                return Err(IpcError::FrameTooLarge(self.config.max_frame_bytes));
            }
            stream.write_all(&request).await?;
            stream.flush().await?;

            let mut reader = BufReader::with_capacity(self.config.read_buffer_bytes, stream);
            let mut frame = Vec::with_capacity(self.config.read_buffer_bytes);
            if !read_frame(&mut reader, &mut frame, self.config.max_frame_bytes).await? {
                return Err(IpcError::TruncatedFrame);
            }
            let response: ClientResponse<T> = serde_json::from_slice(&frame)?;
            if response.jsonrpc != JSON_RPC_VERSION || response.id != request_id {
                return Err(IpcError::Protocol("response id/version mismatch".to_owned()));
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
    use super::{IpcConfig, RpcErrorObject, UnixRpcClient, serve};
    use serde_json::{Value, value::RawValue};
    use std::sync::Arc;
    use tempfile::tempdir;
    use tokio::sync::watch;

    #[tokio::test]
    async fn client_and_server_exchange_borrowed_json() {
        let directory = tempdir().unwrap();
        let path = directory.path().join("rpc.sock");
        let handler = Arc::new(
            |method: &str,
             params: Option<&RawValue>|
             -> Result<Box<RawValue>, RpcErrorObject> {
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
            tokio::time::sleep(std::time::Duration::from_millis(5)).await;
        }

        let result: Value = UnixRpcClient::new(path)
            .call("echo", &serde_json::json!({"value": 42}))
            .await
            .unwrap();
        assert_eq!(result, serde_json::json!({"value": 42}));
        shutdown_tx.send(true).unwrap();
        task.await.unwrap().unwrap();
    }
}
