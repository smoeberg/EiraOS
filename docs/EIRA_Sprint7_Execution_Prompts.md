# 🚀 Sprint 7: Detaljeret Eksekveringsplan & AI Prompts (v1.0)

**Fokus for Sprint 7 (Uge 13–14):**  
**Spatial Canvas UI**, **Situation UI** og **Tauri v2 Desktop App Shell**, der forbinder React-grænsefladen direkte til dæmonernes Unix Domain Sockets over Tauri IPC.

## 📋 Sprint 7 To-Do Oversigt

- [ ] **Task 7.1:** Tauri v2 Native Unix Socket Bridge (`ui/src-tauri/src/ipc.rs`).
- [ ] **Task 7.2:** Spatial Canvas Workspace Component (`ui/src/components/SpatialCanvas.tsx`).
- [ ] **Task 7.3:** Situation UI & State Action Cards (`ui/src/components/SituationUI.tsx`).
- [ ] **Task 7.4:** Interaktivt Veritas HUD Component (`ui/src/components/VeritasHUD.tsx`).
- [ ] **Task 7.5:** React & Tauri End-to-End UI Integration Test (`ui/tests/e2e_canvas.test.ts`).

## 🛠️ Detaljerede Prompts for Hver Opgave i Sprint 7

### 🔹 Task 7.1: Tauri v2 Native Unix Socket Bridge

**Filer:** `ui/src-tauri/src/ipc.rs`, `ui/src-tauri/src/main.rs`

```text
Implementer Rust Tauri command `send_ipc_request(daemon: String, method: String,
params: Value) -> Result<Value, String>` med direkte Unix Domain Socket-forbindelse
til `/run/eira/<daemon>.sock`, JSON-RPC, timeout, strukturerede fejl og asynkron
tokio socket-I/O.
```

### 🔹 Task 7.2: Spatial Canvas Workspace Component

**Filer:** `ui/src/components/SpatialCanvas.tsx`

```text
Implementer React + TypeScript Spatial Canvas med pan/zoom, interaktive
tilstandsobjekter og relationer samt realtidsdata over Tauri IPC fra graphd og
stated.
```

### 🔹 Task 7.3: Situation UI & State Action Cards

**Filer:** `ui/src/components/SituationUI.tsx`

```text
Implementer Situation UI, der præsenterer kontekstbaserede handlinger og
dynamiske action cards fra modtagne ProposalState-objekter.
```

### 🔹 Task 7.4: Interaktivt Veritas HUD Component

**Filer:** `ui/src/components/VeritasHUD.tsx`

```text
Implementer Veritas HUD overlay med Trust Score 0–100% samt opdeling på Lag 1–3
og C2PA-mediesignaturer.
```

### 🔹 Task 7.5: React & Tauri End-to-End UI Integration Test

**Filer:** `ui/tests/e2e_canvas.test.ts`

```text
Skriv Playwright/Vitest E2E-tests for Spatial Canvas og Veritas HUD.
```
