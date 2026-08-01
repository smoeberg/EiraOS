# 🚀 Sprint 8: Detaljeret Eksekveringsplan & AI Prompts (v1.0)

**Fokus for Sprint 8 (Uge 15–16):**  
**Rust IPC Crate Cutover** og **Zero-Copy Unix Socket Performance**, der migrerer den kritiske tilstandsevaluering fra Python til køreklare Rust crates for ultra-lav latency (<1 ms).

## 📋 Sprint 8 To-Do Oversigt

- [ ] **Task 8.1:** Rust `eira-ipc` Crate Optimization (`crates/eira-ipc/src/lib.rs`).
- [ ] **Task 8.2:** Rust `eira-stated` & SQLite Performance Engine (`crates/eira-stated/src/lib.rs`).
- [ ] **Task 8.3:** C-FFI / Python Bridge bindings for Rust `stated` (`crates/eira-stated/src/ffi.rs`).
- [ ] **Task 8.4:** Zero-Copy Shared Memory IPC Protocol (`crates/eira-ipc/src/shm.rs`).
- [ ] **Task 8.5:** Rust Cutover Benchmark & Regression Test Suite (`tests/test_rust_cutover_performance.py`).

## 🛠️ Detaljerede Prompts for Hver Opgave i Sprint 8

### 🔹 Task 8.1: Rust `eira-ipc` Crate Optimization

**Filer:** `crates/eira-ipc/src/lib.rs`

```text
Implementer en højydelses asynkron JSON-RPC server/klient over Unix Domain
Sockets med tokio og direkte, allokeringsfri parsing af lånte JSON-felter via
serde_json.
```

### 🔹 Task 8.2: Rust `eira-stated` & SQLite Performance Engine

**Filer:** `crates/eira-stated/src/lib.rs`

```text
Implementer uforanderlig SHA3-256 hashkædning i Rust med direkte rusqlite
connection pooling og state-appends med latency under 1 ms.
```

### 🔹 Task 8.3: C-FFI / Python Bridge bindings for Rust `stated`

**Filer:** `crates/eira-stated/src/ffi.rs`, `app/core_rust.py`

```text
Opret C-kompatible eksportfunktioner og ctypes-binding, så Python IPC-kontrolplanet
kan kalde den hurtige Rust-backend.
```

### 🔹 Task 8.4: Zero-Copy Shared Memory IPC Protocol

**Filer:** `crates/eira-ipc/src/shm.rs`

```text
Implementer mmap-baserede POSIX shared-memory buffers til store mediefiler og
tunge tilstandskæder.
```

### 🔹 Task 8.5: Rust Cutover Benchmark & Regression Test Suite

**Filer:** `tests/test_rust_cutover_performance.py`

```text
Sammenlign Python- og Rust-backendens ydeevne og verificer 100%
datakompatibilitet for SHA3-256-kæderne.
```
