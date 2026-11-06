# 🐧 EiraOS — The Cognitive Overlay for Ubuntu 24.04 LTS

EiraOS er udviklet specifikt som det **kognitive og intent-drevne lag oven på Ubuntu Linux**:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        EiraOS UX / Intent Shell                         │
│     (Spatial Canvas, Conversational UI, 100-Level Veritas Indicator)    │
├─────────────────────────────────────────────────────────────────────────┤
│                      EiraOS Core System Daemons                         │
│  (stated, identityd, fleetd, veritasd, intentd, graphd + 3 prototyper)  │
├─────────────────────────────────────────────────────────────────────────┤
│                   Ubuntu 24.04 LTS Substrate / Kernel                   │
│   (Linux Kernel, Systemd, AppArmor, Hardware Drivers, APT / Snap)       │
└─────────────────────────────────────────────────────────────────────────┘
```

### Hvorfor Ubuntu som fundament?
1. **Ubuntu leverer infrastrukturen:** Hardware-drivere, GPU/NPU-acceleration, sikkerhed (AppArmor) og Canonical LTS-stabilitet.
2. **EiraOS leverer værdien:** Slut med det forældede 2000'er skrivebords-paradigme (filer/mapper/menuer). EiraOS forvandler Ubuntu til et **objekt-, tillids- og intent-drevet operativsystem**.
3. **Native Systemd Integration:** De seks produktionsdaemons pakkes i `eira-os-core.deb` som hærdede `systemd`-units (`systemd/eira-*.service`, samlet under `eira.target`). Se statustabellen nedenfor.

# EIRA Cognitive Runtime — Phase 1–3 Prototype

Python IPC daemons + HTTP dev bridge + React Cognitive Dashboard (Tauri IPC-ready).

**UI:** Calm Command v2 — se [UX Visual Language](docs/specs/EIRA_UX_Visual_Language_v0.1.md).  
**Situation UI (fase 0):** tom tilstand, Hvorfor-fold, relationstræ — se [Situation UI Vision](docs/specs/EIRA_Situation_UI_Vision_v0.1.md).

## Arkitektur (P1 IPC)

```
Tauri UI  ──Tauri IPC──►  send_ipc_request (Rust)  ──JSON-RPC──►  /run/eira/<daemon>.sock
curl/dev  ──HTTP──────►  app.http_bridge (kun dev) ──JSON-RPC──►
```

Alle daemons taler newline-framet JSON-RPC 2.0 over Unix domain sockets. Adgang styres med
`SO_PEERCRED` (UID/GID-allowlist) og en valgfri `EIRA_IPC_TOKEN`.

| Daemon | Socket | Status | Pakket i `.deb` |
|--------|--------|--------|-----------------|
| `stated` | `stated.sock` | Implementeret (append-only state, Rust-backend via FFI valgfri) | Ja |
| `identityd` | `identityd.sock` | Implementeret (session, certifikatverifikation); step-up returnerer `step_up_provider_unavailable` | Ja |
| `fleetd` | `fleetd.sock` | Implementeret (pairing, heartbeat, E2EE Merkle-sync, WebSocket) | Ja |
| `veritasd` | `veritasd.sock` | Implementeret (lag 1–3, C2PA via ekstern `c2patool`) | Ja |
| `intentd` | `intentd.sock` | Implementeret (parser, CEL-constraints, bekræftelsesgate) | Ja |
| `graphd` | `graphd.sock` | Implementeret (temporal object graph) | Ja |
| `walletd` | `walletd.sock` | Prototype — afviser altid (`NOT_CONFIGURED`) | Nej |
| `presenced` | `presenced.sock` | Prototype — kun in-memory | Nej |
| `contextd` | `contextd.sock` | Prototype — kun in-memory | Nej |

**Socket-mappe:** `data/run/` under udvikling, `/run/eira/` i produktion (styres med `EIRA_RUN_DIR`;
Tauri-shellen læser også `EIRA_SOCKET_DIR`).

## Krav

- Linux med Unix domain sockets (målplatform: Ubuntu 24.04 LTS). Daemon-IPC'en kræver `SO_PEERCRED`
  og virker derfor ikke på Windows i øjeblikket.
- Python 3.11+
- Node.js 20+ og Rust (stable) til Tauri-shellen
- Valgfrit: Ollama + `mistral` til LLM-parse

## Kør (udvikling)

Fra repoets rod:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
alembic upgrade head
uvicorn app.http_bridge:app --reload --port 8765
```

HTTP-broen **starter daemons automatisk** ved opstart (slå fra med `EIRA_DISABLE_DAEMONS=1`).

### Scope closure P0 (juli 2026)

- **Sessions** — `X-EIRA-Session-Id` header; step-up er per session
- **Pending intents** — SQLite (overlever daemon-genstart)
- **fleetd** — `POST /v1/fleet/enroll`, `POST /v1/fleet/heartbeat`
- **Adapter health** — offline adapter blokerer plan/execute
- **IPC token** — valgfri `EIRA_IPC_TOKEN` env

Slet `data/eira.db` én gang efter opgradering for nye tabeller, eller kør app (auto-migration).

```bash
export EIRA_IPC_TOKEN=dev-secret
```

## Kør daemons separat (som produktion)

**Terminal 1:**
```bash
python -m app.daemons.runner --socket-dir data/run
```

**Terminal 2:**
```bash
EIRA_DISABLE_DAEMONS=1 EIRA_RUN_DIR=data/run uvicorn app.http_bridge:app --reload --port 8765
```

## IPC smoke test

```bash
python scripts/ipc_smoke_test.py
```

Tester: `dashboard.get` → `intent.plan` → step-up block → `identity.step_up` → `intent.confirm`.
Bemærk: `identity.step_up` er fail-closed, indtil en step-up-provider er konfigureret.

## JSON-RPC eksempel (intentd.sock)

```json
{"jsonrpc":"2.0","id":1,"method":"intent.plan","params":{"raw_input":"Godkend budget","focus":"Kommunepilot"}}
```

Én request per linje, newline-framet.

## HTTP endpoints (dev bridge)

| Endpoint | IPC metode |
|----------|------------|
| `GET /v1/dashboard` | `dashboard.get` |
| `POST /v1/intent/plan` | `intent.plan` |
| `POST /v1/intent/confirm` | `intent.confirm` |
| `POST /v1/identity/step-up` | `identity.step_up` |
| `POST /v1/graph/temporal` | `graph.temporal_query` |
| `GET /health` | alle daemon `health` |

## Desktop-shell (Tauri + direkte IPC)

Start daemons først (se ovenfor), derefter:

```bash
cd ui
npm ci
EIRA_RUN_DIR="$(cd .. && pwd)/data/run" npm run tauri dev
```

React-grænsefladen kalder daemons gennem én Tauri-kommando, `send_ipc_request`
(`ui/src-tauri/src/ipc.rs`). `npm run dev` alene starter kun Vite på http://127.0.0.1:5173;
uden Tauri er der ingen IPC, og Vite har ingen proxy til HTTP-broen.

Frontend-test: `cd ui && npm ci && npx tsc --noEmit && npm test`.

## Relaterede specs

- [EIRA_Desktop_Architecture_v1.0.md](docs/specs/EIRA_Desktop_Architecture_v1.0.md) §6 IPC
- [EIRA_Cognitive_Runtime_v1.0.md](docs/specs/EIRA_Cognitive_Runtime_v1.0.md)


---

## 🛡️ Project Veritas-Skjoldet (Informations- & Billedvalidering)

EiraOS indeholder en integreret, kryptografisk og narrativt intelligent modul for informations- og kildekritik (**`veritas-shield/`**):

- **Lag 1: Artikelanalyse (Det Røde Skjold):** 200 regelbaserede parametre for kildeforankring, parthøring og sproglig tone uden AI-hallucination (`veritas-shield/lag1-article-analysis/`).
- **Lag 2: EUDI Wallet Bridge (Det Grønne Skjold):** eIDAS 2.0 / QEAA validering af digitale afsendersignaturer (`veritas-shield/adapters/eudi-wallet-adapter/`).
- **Lag 3: Narrativ Kortlægning (Det Blå Skjold):** Mønstergenkendelse og tidsmæssig provenance i EiraOS Temporal Graph (`veritas-shield/lag3-narrative-mapping/`).
- **C2PA Billed- & Medievalidering:** Hardware-signaturer (Leica, Canon, Sony) og AI-genereringsdetektion (`veritas-shield/adapters/c2pa-image-validator/`).
- **Browser HUD Component:** Interaktiv status-indikator (🟢/🟡/🔴) til EiraOS Tauri browser (`ui/veritas-hud/`).


---

# 🚀 EiraOS 2.0 — målarkitektur

> Dette afsnit beskriver målbilledet. Den aktuelle implementeringsstatus for hver daemon står i tabellen under *Arkitektur (P1 IPC)*.

EiraOS 2.0 introducerer en revolutionerende operativsystem-model, hvor **Økonomi (Wallet)**, **Troværdighed (Veritas)** og **Samarbejde (Presence)** er dybe, integrerede system-daemons på linje med netværk og filsystem:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            EiraOS 2.0 Kernel                                │
├───────────────┬─────────────────────────────────────────┬───────────────────┤
│ 1. identityd  │ Bruger, Organisationer, Nøgler, EUDI   │ Identitets-lag    │
├───────────────┼─────────────────────────────────────────┼───────────────────┤
│ 2. walletd    │ SEPA Instant, Open Banking PSD3, EUDI  │ Økonomi & Agent   │
├───────────────┼─────────────────────────────────────────┼───────────────────┤
│ 3. veritasd   │ Evidence Engine, C2PA, Trust Score 0-100%│ Troværdighed      │
├───────────────┼─────────────────────────────────────────┼───────────────────┤
│ 4. graphd     │ Temporal Knowledge Graph, Objekter      │ Hukommelses-lag   │
├───────────────┼─────────────────────────────────────────┼───────────────────┤
│ 5. presenced  │ Conversation follows Object, Beslutninger│ Samarbejde        │
├───────────────┼─────────────────────────────────────────┼───────────────────┤
│ 6. intentd    │ Fortolker Intention & Orkestrerer       │ Eksekvering       │
└───────────────┴─────────────────────────────────────────┴───────────────────┘
```

## Nøglesøjler i EiraOS 2.0

### 1. `walletd` (Økonomisk Optimering & EUDI)
- Omgår us-baserede kreditkortmonopoler (Visa/Mastercard) ved automatisk at vælge den billigste europæiske betalingsvej (**SEPA Instant**, **Digital Euro**, **Open Banking PSD3**).
- Håndterer brugerens **EUDI Wallet** certifikater, samtykker og digitale nøgler.

### 2. `veritasd` (Evidence & Trust Engine)
- Beregner en præcis **Trust Score (0-100%)** for alle indkommende informationer, tekst, billeder (C2PA) og dokumenter før de indlejres i objektgrafen.

### 3. `presenced` (Objektbaseret Samarbejde)
- **"Conversation follows Object":** Drøftelser, beslutninger og ekspertise er forankret direkte på Objekterne i Knowledge Graph (Bygning, Projekt, Dokument), ikke i isolerede chat-kanaler.
