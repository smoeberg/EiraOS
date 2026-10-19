# Audit C — UI / Tauri build på Ubuntu 24.04

**Issue:** #25  
**Branch:** `audit/c-ui-tauri`  
**Dato:** 2026-10-19  
**Miljø:** Ubuntu 24.04.4 LTS (Noble), kernel 6.12.8+, x86_64  
**Scope:** Afsnit C i `docs/EIRA_GUI_Audit_Checklist.md` — dokumentation only, ingen kodeændringer.

---

## 1. Gate-status

| Gate | Resultat |
|------|----------|
| `cargo tauri dev` kører på Ubuntu 24.04 | **NEJ** — fuld fejlliste nedenfor |
| Frontend `npm run build` | **JA** — Vite-produktion build lykkedes |
| Vitest e2e (canvas) | **JA** — 2/2 tests passed |
| HTTP-leaks i aktiv UI-sti | **Delvis** — aktiv App-sti bruger Tauri IPC; legacy HTTP-moduler ligger stadig i repo |
| `src-tauri` + capabilities | **JA** — findes (`capabilities/default.json`) |

**Konklusion:** Gate er **ikke grøn**. Leverancen er denne rapport + prioriteret fejlliste (første tickets til Sprint 1–2).

---

## 2. Byggemiljø (beviser)

```text
PRETTY_NAME="Ubuntu 24.04.4 LTS"
VERSION_ID="24.04"
uname: Linux … 6.12.8+ #1 SMP … x86_64 GNU/Linux

node: v24.15.0
npm:  11.12.1
rustc: 1.75.0 (82e1608df 2023-12-21) (built from a source tarball)
cargo: 1.75.0
rustup: ikke installeret

npx @tauri-apps/cli → tauri-cli 2.12.3

DISPLAY / WAYLAND_DISPLAY: tomme (headless)
systemctl --user: Failed to connect to bus: No medium found
```

### `npx tauri info` (uddrag)

```text
[✘] Environment
    - OS: Ubuntu 24.4.0 x86_64
    ✘ webkit2gtk-4.1: not installed
    ✘ rsvg2: not installed          # runtime librsvg2-2 er dog installeret
    ✔ rustc: 1.75.0
    ✔ cargo: 1.75.0
    ⚠ rustup: not installed!
    - node: 24.15.0
    - npm: 11.12.1

[-] Packages
    - tauri 🦀: 2
    - @tauri-apps/api ⱼₛ: 2.11.1
    - @tauri-apps/cli ⱼₛ: 2.11.4

[-] App
    - CSP: default-src 'self' ipc: http://ipc.localhost; connect-src 'self' ipc: …
    - frontendDist: ../dist
    - devUrl: http://127.0.0.1:5173/
    - framework: React / Vite
```

### Systempakker

```text
# Installerede GTK-relaterede (uddrag)
libgtk-3-0t64, libgtk-3-bin, libgtk-3-common
libgtk2.0-0t64, librsvg2-2, librsvg2-common

# Manglende / ikke findbare i dette miljøs apt-indeks
libwebkit2gtk-4.1-dev  →  E: Unable to locate package
webkit2gtk-4.1 (pkg-config) → missing
```

> Bemærkning: På en **fuld** Ubuntu 24.04 desktop med standard-repos forventes `libwebkit2gtk-4.1-dev` at være tilgængelig. I dette audit-miljø (minimal/container-lignende) er pakken ikke i apt-indekset. Fejlen tæller stadig som blokerende for “ren Ubuntu 24.04”-gate indtil den er verificeret på en standard desktop-install.

---

## 3. Kommando-output (reproduktion)

### 3.1 Frontend — lykkes

```bash
cd ui && npm install --registry https://registry.npmjs.org/
# added 166 packages …

npm run build
# > tsc --noEmit && vite build
# ✓ 35 modules transformed.
# dist/assets/index-….js   202.38 kB │ gzip: 63.89 kB
# ✓ built in 1.44s

npm test
# ✓ tests/e2e_canvas.test.ts (2 tests) 174ms
# Test Files  1 passed (1)
```

### 3.2 Tauri / Cargo — fejler før compile

`ui/src-tauri/Cargo.toml` kræver:

```toml
edition = "2024"
rust-version = "1.85"
```

Installeret toolchain er **1.75.0** uden `edition2024`-feature.

```bash
cd ui && npx tauri build
# failed to run 'cargo metadata' …
# error: failed to parse manifest at `…/ui/src-tauri/Cargo.toml`
# Caused by:
#   feature `edition2024` is required
#   The package requires the Cargo feature called `edition2024`,
#   but that feature is not stabilized in this version of Cargo (1.75.0).
```

```bash
cd ui/src-tauri && cargo check
# samme parse-fejl på edition2024
```

`cargo tauri dev` kan derfor ikke startes: metadata-parse fejler før WebView/deps overhovedet nås.

---

## 4. Dependencies-liste

### 4.1 npm (`ui/package.json` — installerede top-level)

| Pakke | Version (resolved) | Rolle |
|-------|-------------------|--------|
| react / react-dom | 19.2.8 | UI |
| @tauri-apps/api | 2.11.1 | Frontend ↔ Rust invoke |
| @tauri-apps/cli | 2.11.4 (dev) | `tauri dev/build` |
| vite | 7.3.6 | Bundler |
| typescript | 5.9.3 | Typecheck |
| @vitejs/plugin-react | 5.2.0 | React transform |
| vitest + testing-library + jsdom | 3.x / 16.x / 26.x | Tests |

**npm audit:** 5 vulnerabilities (1 moderate, 2 high, 2 critical) ved install — ikke triaget i denne audit (kosmetisk ift. build-gate).

### 4.2 Cargo (`ui/src-tauri/Cargo.toml`)

| Crate | Version | Rolle |
|-------|---------|--------|
| tauri | 2 | Desktop shell |
| tauri-build | 2 | build.rs |
| serde / serde_json | 1 | JSON-RPC |
| tokio | 1 (io-util, net, time) | Unix socket IPC |

### 4.3 System (Tauri 2 Linux prerequisites)

| Pakke | Status på audit-host |
|-------|----------------------|
| libwebkit2gtk-4.1-dev | **Mangler** (ikke i apt-indeks her) |
| build-essential, pkg-config, libgtk-3-dev, librsvg2-dev, patchelf, … | Delvist / ukendt — webkit er den eksplicitte fejl fra `tauri info` |
| Rust ≥ 1.85 (rustup anbefalet) | **Mangler** (1.75.0, ingen rustup) |

Officiel reference: https://v2.tauri.app/start/prerequisites/

---

## 5. HTTP-leaks (grep)

Søgning i `ui/` (`.ts`/`.tsx`/`.rs`/`.json`/`.html`), ekskl. package-lock og schema-URL’er:

| Fil | Fund | Aktiv i `App.tsx`? |
|-----|------|---------------------|
| `ui/src/api.ts` | `fetch(\`${API}/v1/auth/oidc/config\`)` | Nej (kun via `AuthButton`) |
| `ui/src/api.ts` | `fetch(\`${API}/v1/auth/oidc/mock-login\`)` | Nej |
| `ui/src/api.ts` | `window.location.assign(\`${API}/v1/auth/oidc/login\`)` | Nej |
| `ui/src/api.ts` | `fetch(\`${API}/v1/dashboard\`)` | Nej |
| `ui/src/api.ts` | `fetch(\`${API}/v1/intent/plan\`)` | Nej |
| `ui/src/api.ts` | `fetch(\`${API}/v1/journeys/…/advance\`)` | Nej |
| `ui/src/graph.ts` | `fetch(\`${API}/v1/graph/context?…\`)` | Nej |
| `ui/src/lib/ipc.ts` | `invoke("send_ipc_request", …)` | **Ja** — eneste datasti fra `App` |
| `ui/src-tauri/src/ipc.rs` | Unix JSON-RPC til `/run/eira/{daemon}.sock` | **Ja** (produktionsti) |
| `ui/src-tauri/tauri.conf.json` | `devUrl: http://127.0.0.1:5173` | Dev-only Vite HMR |
| `ui/vite.config.ts` | **Ingen** proxy til `:8765` / http_bridge | — |

`API = ""` betyder relative fetches mod samme origin (Vite-dev eller Tauri asset-host). Der er **ingen** vite-proxy til HTTP-bridge, så legacy `api.ts`/`graph.ts` virker kun hvis noget serverer `/v1/*` på samme origin.

**Regelbrud ift. Contributor Prompt:** “Ingen HTTP i produktion: UI taler KUN JSON-RPC over /run/eira/*.sock”.  
Aktiv shell (`App.tsx`) overholder reglen. Legacy-moduler + `AuthButton` gør det **ikke** og er stadig i træet.

---

## 6. Real vs. mock — komponentkortlægning

| Komponent | Sti | Status | Datakilde | Note |
|-----------|-----|--------|-----------|------|
| **SpatialCanvas** | `ui/src/components/SpatialCanvas.tsx` | **Real (IPC)** | `stated` / `graphd` via `sendIpcRequest` | Poller states + graph snapshot; fallback layout hvis graph fejler |
| **VeritasHUD** | `ui/src/components/VeritasHUD.tsx` | **Real (IPC + presentational)** | Props fra `App` → `veritasd` / `veritas.evaluate` | Ægte lag-UI (C2PA, evidence, narrative, …); afhænger af daemon |
| **SituationUI** | `ui/src/components/SituationUI.tsx` | **Real (presentational)** | Proposals fra SpatialCanvas/stated | Ingen egen netværkskald |
| **Dashboard** | — | **Ingen UI-komponent** | Kun type + `fetchDashboard()` i `api.ts` | HTTP-legacy; ikke monteret i `App` |
| **IntentBar** | — | **Findes ikke** | — | Ingen fil/komponent med det navn i `ui/` |
| **AuthButton** | `ui/src/AuthButton.tsx` | **Orphan / HTTP** | `api.ts` OIDC/mock | Ikke importeret af `App.tsx` |
| **EmptyState** | `ui/src/EmptyState.tsx` | **Orphan** | Statisk | Ikke importeret |
| **RelationTree / WhyFold** | `ui/src/RelationTree.tsx`, `WhyFold.tsx` | **Orphan / HTTP-adjacent** | `graph.ts` types | Ikke importeret af `App` |
| **veritas-hud/** | `ui/veritas-hud/index.html` | **Standalone mock/demo** | Inline HTML/JS, hardcodet eksempel-URL | Browser-HUD prototype, ikke Tauri-shell |

### `src-tauri` capabilities

- Fil: `ui/src-tauri/capabilities/default.json`
- Identifier: `default`, window `main`, permissions: `core:default`
- IPC-allowlist i Rust: `stated`, `identityd`, `fleetd`, `veritasd`, `intentd`, `graphd` (aliases uden `d`-suffix accepteres)
- Socket-root: `EIRA_RUN_DIR` eller default `/run/eira/{daemon}.sock`
- Token: valgfri `EIRA_IPC_TOKEN` indsættes under `_eira.ipc_token`

---

## 7. Arkitektur (nuværende)

```
┌─────────────────────────────────────────────────────────┐
│  App.tsx (aktiv shell)                                  │
│    SpatialCanvas ──IPC──► stated / graphd               │
│    VeritasHUD    ◄──IPC── veritasd (via App handleSelect)│
│    SituationUI   ◄── props (proposals)                  │
└───────────────────────────┬─────────────────────────────┘
                            │ invoke("send_ipc_request")
                            ▼
┌─────────────────────────────────────────────────────────┐
│  src-tauri (Rust)  ipc.rs → AF_UNIX /run/eira/*.sock    │
└─────────────────────────────────────────────────────────┘

Legacy (ikke i App-træet, stadig i repo):
  api.ts / graph.ts / AuthButton ──fetch──► /v1/*  (HTTP-bridge forudsætning)
```

---

## 8. Fejlliste → første tickets (Sprint 1–2)

Prioritering jf. checklist F (blokerende / ødelæggende UX / kosmetisk).

### Blokerende (forhindrer `cargo tauri dev` på Ubuntu 24.04)

| ID | Titel | Detalje |
|----|-------|---------|
| **C-B1** | Rust-toolchain ≥ 1.85 + rustup | `Cargo.toml` kræver `edition = "2024"` og `rust-version = "1.85"`. Host har 1.75 uden edition2024 → `cargo metadata` fejler. Ticket: dokumentér/script `rustup` install + pin i CI/README. |
| **C-B2** | System-deps: `libwebkit2gtk-4.1-dev` (+ øvrige Tauri 2 Linux deps) | `tauri info`: webkit2gtk-4.1 not installed. Pakke ikke tilgængelig i dette miljøs apt; skal verificeres på standard Ubuntu 24.04 desktop og ind i setup-script/docs. |
| **C-B3** | Headless / manglende session-bus | Ingen `DISPLAY`/`WAYLAND_DISPLAY`, ingen user systemd bus. GUI-runtime kan ikke demonstreres her — kræver rigtig desktop-session til accept-screenshot. |

### Ødelæggende for UX / kontrakt

| ID | Titel | Detalje |
|----|-------|---------|
| **C-U1** | Fjern eller isoler HTTP-legacy i produktionsti | `api.ts` + `graph.ts` + `AuthButton` bruger `fetch(/v1/…)`. Overtræder “ingen HTTP i produktion”. Enten slet/orphan-markér eller flyt bag feature-flag kun til browser-dev. |
| **C-U2** | IntentBar mangler | Checklist nævner IntentBar; ingen komponent findes. Intent-plan findes kun som HTTP i `api.ts`. Skal bygges som IPC-mod `intentd` i Sprint 1–2. |
| **C-U3** | Dashboard-UI mangler | Kun TypeScript-interface + HTTP-fetch; ingen React-overflade i aktiv shell. |
| **C-U4** | Auth/OIDC kun via HTTP | Ingen IPC-baseret login-sti i aktiv App; `AuthButton` er orphan. |

### Kosmetisk / vedligehold

| ID | Titel | Detalje |
|----|-------|---------|
| **C-K1** | npm audit (5 vulns) | Kør `npm audit` triage; opdatér `@tauri-apps/api`/`cli` til seneste 2.12.x hvis ønsket. |
| **C-K2** | Orphan-komponenter | `EmptyState`, `RelationTree`, `WhyFold` — afklar slet vs. genbrug i Situation UI. |
| **C-K3** | `veritas-hud/index.html` standalone | Demo-HTML; hold adskilt fra Tauri-shell eller integrér bevidst. |
| **C-K4** | Vite uden proxy til http_bridge | README nævner stadig HTTP-dev-flow; `vite.config.ts` har ingen proxy — dokumentation vs. kode mismatch. |

---

## 9. Screenshots / GUI-beviser

**Ikke muligt i dette miljø:** ingen Wayland/X11-session, ingen `cargo tauri dev`.  

Frontend-build og Vitest (med mocket IPC via `window.__EIRA_TEST_IPC__`) er grønne og dokumenterer at React-shell + canvas-test kører headless.

Anbefalet accept-bevis på rigtig Ubuntu 24.04 desktop efter C-B1/C-B2:

```bash
# efter rustup + webkit deps
cd ui && npm install && cargo tauri dev
# + screenshot af Spatial Workspace + VeritasHUD
# + wayland-info / echo $XDG_SESSION_TYPE
```

---

## 10. Acceptkriterier (issue #25)

| Kriterium | Status |
|-----------|--------|
| `docs/audit/C_UI_TAURI.md` med build-rapport, deps, real-vs-mock, HTTP-grep | **Opfyldt** (denne fil) |
| Fejlliste pr. fejl = første ticket Sprint 1–2 | **Opfyldt** (§8) |
| `cargo tauri dev` kører **eller** fuld fejlliste | **Opfyldt via fejlliste** (C-B1, C-B2, C-B3) |
| Ingen kodeændringer / daemons | **Overholdt** |
| PR mod main med beviser | **Denne branch + PR** |

---

*Audit udført uden ændringer i applikationskode. Næste skridt efter merge: opret tickets C-B1…C-U4 i Sprint 1–2 backlog.*
