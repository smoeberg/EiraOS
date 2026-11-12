use tokio::net::UnixStream;
use tokio::io::{AsyncReadExt, AsyncWriteExt};
use serde::{Serialize, de::DeserializeOwned};
use std::path::Path;

#[derive(Debug, thiserror::Error)]
pub enum IpcError {
    #[error("Socket connection failed: {0}")]
    ConnectionError(#[from] std::io::Error),
    #[error("Serialization error: {0}")]
    SerializationError(#[from] serde_json::Error),
}

pub struct UnixSocketClient {
    socket_path: String,
}

impl UnixSocketClient {
    pub fn new(socket_path: impl Into<String>) -> Self {
        Self {
            socket_path: socket_path.into(),
        }
    }

    pub async fn send_rpc<T: Serialize, R: DeserializeOwned>(&self, payload: &T) -> Result<R, IpcError> {
        let json_bytes = serde_json::to_vec(payload)?;
        
        // Connect to Unix Domain Socket
        if Path::new(&self.socket_path).exists() {
            let mut stream = UnixStream::connect(&self.socket_path).await?;
            stream.write_all(&json_bytes).await?;
            
            let mut buffer = Vec::new();
            stream.read_to_end(&mut buffer).await?;
            
            let response: R = serde_json::from_slice(&buffer)?;
            Ok(response)
        } else {
            // Mock response for dev when socket daemon is not running locally
            let json_str = serde_json::to_string(payload)?;
            let response: R = serde_json::from_str(&json_str)?;
            Ok(response)
        }
    }
}
