//! eira-core — Native Rust IPC & Contract Bridge for EiraOS 2.0
//! Connects Tauri / eira-shell directly to the 6 Core Daemons over Unix Domain Sockets.

pub mod ipc;
pub mod models;
pub mod bridge;

pub use bridge::EiraCoreBridge;
