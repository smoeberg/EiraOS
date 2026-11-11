# 🚀 Sprint 8: Detaljeret Eksekveringsplan & AI Prompts (v1.0)

**Fokus for Sprint 8 (Uge 15–16):**  
**Rust IPC Crate Cutover** og **Zero-Copy Unix Socket Performance**, der migrerer den kritiske tilstandsevaluering fra Python til køreklare Rust crates for ultra-lav latency (<1ms).

---

## 📋 Sprint 8 To-Do Oversigt

- [ ] **Task 8.1:** Rust `eira-ipc` Crate Optimization (`crates/eira-ipc/src/lib.rs`).
- [ ] **Task 8.2:** Rust `eira-stated` & SQLite Performance Engine (`crates/eira-stated/src/lib.rs`).
- [ ] **Task 8.3:** C-FFI / Python Bridge bindings for Rust `stated` (`crates/eira-stated/src/ffi.rs`).
- [ ] **Task 8.4:** Zero-Copy Shared Memory IPC Protocol (`crates/eira-ipc/src/shm.rs`).
- [ ] **Task 8.5:** Rust Cutover Benchmark & Regression Test Suite (`tests/test_rust_cutover_performance.py`).

---

## 🛠️ Detaljerede Prompts for Hver Opgave i Sprint 8

### 🔹 Task 8.1: Rust `eira-ipc` Crate Optimization
**Filer:** `crates/eira-ipc/src/lib.rs`  
**Prompt:**
```text
Du skal optimere Rust IPC craten i `crates/eira-ipc/src/lib.rs`.

Krav:
1. Implementer en højydelses asynkron JSON-RPC server/klient over Unix Domain Sockets ved hjælp af `tokio`.
2. Sørg for direkte zero-allocation JSON parring via `serde_json`.
```

---

### 🔹 Task 8.2: Rust `eira-stated` & SQLite Performance Engine
**Filer:** `crates/eira-stated/src/lib.rs`  
**Prompt:**
```text
Du skal implementere den højydende Rust tilstandsmotor i `crates/eira-stated/src/lib.rs`.

Krav:
1. Implementer uforanderlig SHA3-256 hashkædning i Rust med direkte SQLite connection pooling (`rusqlite`).
2. Opnå tilstands-appends med latency under 1 ms.
```

---

### 🔹 Task 8.3: C-FFI / Python Bridge bindings for Rust `stated`
**Filer:** `crates/eira-stated/src/ffi.rs`, `app/core_rust.py`  
**Prompt:**
```text
Du skal oprette C-FFI og PyO3/ctypes bindings for Rust `stated` i `crates/eira-stated/src/ffi.rs`.

Krav:
1. Opret C-kompatible export funktioner for at lade Python IPC kontrolplanet kalde den hurtige Rust backend.
```

---

### 🔹 Task 8.4: Zero-Copy Shared Memory IPC Protocol
**Filer:** `crates/eira-ipc/src/shm.rs`  
**Prompt:**
```text
Du skal implementere en Zero-Copy Shared Memory (POSIX shm) IPC protokol i `crates/eira-ipc/src/shm.rs`.

Krav:
1. Tillad lynhurtig overførsel af store mediefiler og tunge tilstandskæder via mmap shared memory buffers.
```

---

### 🔹 Task 8.5: Rust Cutover Benchmark & Regression Test Suite
**Filer:** `tests/test_rust_cutover_performance.py`  
**Prompt:**
```text
Du skal oprette en benchmark- og regressionstestsuite i `tests/test_rust_cutover_performance.py`.

Krav:
1. Sammenlign Python vs. Rust backend ydeevne og verificer 100% datakompabilitet på SHA3-256 kæderne.
```
