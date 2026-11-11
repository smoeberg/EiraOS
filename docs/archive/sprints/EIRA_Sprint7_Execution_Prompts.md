# 🚀 Sprint 7: Detaljeret Eksekveringsplan & AI Prompts (v1.0)

**Fokus for Sprint 7 (Uge 13–14):**  
 **Spatial Canvas UI**, **Situation UI** og **Tauri v2 Desktop App Shell**, der forbinder React-grænsefladen direkte til dæmonernes Unix Domain Sockets over Tauri IPC.

---

## 📋 Sprint 7 To-Do Oversigt

- [ ] **Task 7.1:** Tauri v2 Native Unix Socket Bridge (`ui/src-tauri/src/ipc.rs`).
- [ ] **Task 7.2:** Spatial Canvas Workspace Component (`ui/src/components/SpatialCanvas.tsx`).
- [ ] **Task 7.3:** Situation UI & State Action Cards (`ui/src/components/SituationUI.tsx`).
- [ ] **Task 7.4:** Interaktivt Veritas HUD Component (`ui/src/components/VeritasHUD.tsx`).
- [ ] **Task 7.5:** React & Tauri End-to-End UI Integration Test (`ui/tests/e2e_canvas.test.ts`).

---

## 🛠️ Detaljerede Prompts for Hver Opgave i Sprint 7

### 🔹 Task 7.1: Tauri v2 Native Unix Socket Bridge
**Filer:** `ui/src-tauri/src/ipc.rs`, `ui/src-tauri/src/main.rs`  
**Prompt:**
```text
Du skal oprette Tauri v2 Unix Socket bridge-modulet i `ui/src-tauri/src/ipc.rs`.

Krav:
1. Implementer Rust Tauri command `send_ipc_request(daemon: String, method: String, params: Value) -> Result<Value, String>`:
   - Åbn direkte Unix Domain Socket-forbindelse til `/run/eira/<daemon>.sock`.
   - Send JSON-RPC forespørgsel og afvent svar.
2. Håndter timeouts og returner strukturerede fejlmeddelelser til React-frontend.
3. Sørg for at Tauri-bridgen anvender asynkron tokio socket-I/O.
```

---

### 🔹 Task 7.2: Spatial Canvas Workspace Component
**Filer:** `ui/src/components/SpatialCanvas.tsx`  
**Prompt:**
```text
Du skal oprette Spatial Canvas workspace-komponenten i `ui/src/components/SpatialCanvas.tsx`.

Krav:
1. Implementer React + TypeScript Spatial Canvas med pan/zoom interaktion.
2. Canvas skal visualisere tilstandsobjekter og relationer som interaktive noder.
3. Hent tilstands-data i realtid over Tauri IPC fra `graphd` og `stated`.
```

---

### 🔹 Task 7.3: Situation UI & State Action Cards
**Filer:** `ui/src/components/SituationUI.tsx`  
**Prompt:**
```text
Du skal oprette Situation UI komponenten i `ui/src/components/SituationUI.tsx`.

Krav:
1. Implementer Situation UI, der præsenterer handlinger baseret på brugerens aktuelle kontekst.
2. Generer dynamic action cards ud fra modtagne `ProposalState` objekter.
```

---

### 🔹 Task 7.4: Interaktivt Veritas HUD Component
**Filer:** `ui/src/components/VeritasHUD.tsx`  
**Prompt:**
```text
Du skal oprette Veritas HUD komponenten i `ui/src/components/VeritasHUD.tsx`.

Krav:
1. Implementer Veritas HUD overlay med visuel Trust Score cirkel (0–100%).
2. Vis opdeling på Lag 1–3 og C2PA medie-signaturer.
```

---

### 🔹 Task 7.5: React & Tauri End-to-End UI Integration Test
**Filer:** `ui/tests/e2e_canvas.test.ts`  
**Prompt:**
```text
Du skal oprette end-to-end integrationstests for UI i `ui/tests/e2e_canvas.test.ts`.

Krav:
1. Skriv Playwright/Vitest E2E tests for Spatial Canvas og Veritas HUD.
```
