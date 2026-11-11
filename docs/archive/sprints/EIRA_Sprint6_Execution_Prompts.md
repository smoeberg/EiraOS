# 🚀 Sprint 6: Detaljeret Eksekveringsplan & AI Prompts (v1.0)

**Fokus for Sprint 6 (Uge 11–12):**  
Etablering af **Android Client Bindings**, **FFI / WASM State Engine Wrappers** og **Mobil Lokal-State Repla**y, så Android-kloner kan genafspille og verificere EiraOS tilstandskæden lokalt.

---

## 📋 Sprint 6 To-Do Oversigt

- [ ] **Task 6.1:** Core State Model WASM / C-FFI Export (`crates/eira-core/src/ffi.rs`).
- [ ] **Task 6.2:** Android Kotlin Core Binding Layer (`android/eira-core-binding/`).
- [ ] **Task 6.3:** Android Background Sync Service (`android/app/src/main/java/app/eira/sync/SyncService.kt`).
- [ ] **Task 6.4:** Android Local Encrypted State Storage (`android/app/src/main/java/app/eira/storage/RoomStateStore.kt`).
- [ ] **Task 6.5:** Android & FFI State Playback Integration Test Suite (`tests/test_android_ffi_state.py`).

---

## 🛠️ Detaljerede Prompts for Hver Opgave i Sprint 6

### 🔹 Task 6.1: Core State Model WASM / C-FFI Export
**Filer:** `crates/eira-core/src/ffi.rs`, `Cargo.toml`  
**Prompt:**
```text
Du skal oprette C-FFI og WASM bindinger for EiraOS kerne-tilstandsmodellen i `crates/eira-core/src/ffi.rs`.

Krav:
1. Eksporter C-kompatible funktioner (`#[no_mangle] pub extern "C"`):
   - `eira_state_compute_hash(json_payload: *const c_char) -> *mut c_char`: Beregner SHA3-256 hash for en givet tilstand.
   - `eira_state_validate_chain(states_json: *const c_char) -> i32`: Verificerer at en række stater udgør en ubrudt SHA3-256 hashkæde.
2. Håndter hukommelsesallokering og frigivelse sikkert via `eira_free_string(ptr: *mut c_char)`.
3. Verificer at C-bindingerne kompilerer uden advarsler til både `x86_64` og `aarch64-linux-android`.
```

---

### 🔹 Task 6.2: Android Kotlin Core Binding Layer
**Filer:** `android/eira-core-binding/src/main/java/app/eira/core/EiraStateEngine.kt`  
**Prompt:**
```text
Du skal oprette Kotlin FFI-bindingerne for Android i `EiraStateEngine.kt`.

Krav:
1. Implementer `EiraStateEngine` via JNI (Java Native Interface) eller JNA:
   - Indlæsning af det kompilerede C/Rust bibliotek (`libeira_core.so`).
   - Kotlin wrappers for `computeHash()` og `validateChain()`.
2. Håndter native fejl og konverter dem til Kotlin `StateValidationException`.
3. Skriv unit-tests i Kotlin (`EiraStateEngineTest.kt`), der bekræfter korrekt beregning af SHA3-256 hashes på Android-platformen.
```

---

### 🔹 Task 6.3: Android Background Sync Service
**Filer:** `android/app/src/main/java/app/eira/sync/SyncService.kt`  
**Prompt:**
```text
Du skal oprette Android baggrundssynkroniseringstjenesten i `SyncService.kt`.

Krav:
1. Implementer en Android `WorkManager` / `JobService` i `SyncService.kt`:
   - Periodisk og push-trigget opkobling til skrivebordsmaskinens `fleetd` over WebSockets.
   - Udveksling af Merkle-rødder og modtagelse af E2EE krypterede tilstandsblokke.
   - Dekryptering og lokal lagring ved brug af brugerens synkroniseringsnøgle.
2. Sørg for at baggrundssynkroniseringen er strømeffektiv og respekterer Android Doze Mode.
```

---

### 🔹 Task 6.4: Android Local Encrypted State Storage
**Filer:** `android/app/src/main/java/app/eira/storage/RoomStateStore.kt`  
**Prompt:**
```text
Du skal oprette den lokale krypterede SQLite tilstandslager-komponent for Android i `RoomStateStore.kt`.

Krav:
1. Implementer `RoomStateStore` ved hjælp af Android Room / SQLCipher:
   - Database-skema der matcher EiraOS `states` tabellen (id, version, timestamp_ns, type, payload, previous_state_id, hash).
   - Fuld kryptering af databasen på enheden via Android Keystore system-nøgler.
   - Replay-funktionalitet, der genopbygger den aktuelle app-tilstand ved opstart.
2. Skriv en Android-instrumenteret test der bekræfter at data ikke kan læses i klartekst fra enhedens lagermedie.
```

---

### 🔹 Task 6.5: Android & FFI State Playback Integration Test Suite
**Filer:** `tests/test_android_ffi_state.py`  
**Prompt:**
```text
Du skal oprette en integrationstestsuite i `tests/test_android_ffi_state.py`.

Krav:
1. Test FFI-bindingerne og cross-platform tilstandskompatibilitet:
   - `test_python_and_ffi_hash_consistency()`: Generer en `State` i Python og verificer at C-FFI / WASM beregner eksakt samme SHA3-256 hash.
   - `test_chain_validation_across_platforms()`: Send en tilstandskæde fra `stated` til FFI-validatoren og bekræft godkendelse.
   - `test_tampered_chain_detected_by_ffi()`: Manipuler en enkelt byte i en historisk payload og bekræft at FFI-validatoren afviser kæden.
2. Verificer at `pytest tests/test_android_ffi_state.py` kører med 100% succes.
```
