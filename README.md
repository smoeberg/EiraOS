# EIRA Cognitive Runtime — Phase 1–3 Prototype

Python IPC daemons + HTTP dev bridge + React Cognitive Dashboard (Tauri IPC-ready).

**UI:** Calm Command v2 — se [UX Visual Language](../../docs/specs/EIRA_UX_Visual_Language_v0.1.md).  
**Situation UI (fase 0):** tom tilstand, Hvorfor-fold, relationstræ — se [Situation UI Vision](../../docs/specs/EIRA_Situation_UI_Vision_v0.1.md).

## Arkitektur (P1 IPC)

```
React UI  ──HTTP (dev)──►  http_bridge.py  ──IPC──►  intent.sock
Tauri UI  ──IPC (prod)──►                    identity.sock
                                              graph.sock
```

| Socket | Daemon (prototype) | Produktion |
|--------|-------------------|------------|
| `intent.sock` | eira-intent-engine | Rust `eira-intent-engine` |
| `identity.sock` | eira-identityd | Rust `eira-identityd` |
| `graph.sock` | eira-object-graphd | Rust `eira-object-graphd` |
| `fleet.sock` | eira-fleetd | `eira-governance-agent` (P1) |

**Prototype sockets:** `data/run/*.sock`  
**Produktion:** `/run/eira/*.sock` (sæt `EIRA_RUN_DIR`)

## Krav

- Python 3.11+ (AF_UNIX — Windows 10+ understøttet)
- Node.js 20+ (til UI, valgfrit)
- Valgfrit: Ollama + `mistral` til LLM-parse

## Kør (anbefalet — én kommando)

```powershell
cd eira-os/prototype/phase1
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.http_bridge:app --reload --port 8765
```

HTTP bridge **starter daemons automatisk** ved opstart.

### Scope closure P0 (juli 2026)

- **Sessions** — `X-EIRA-Session-Id` header; step-up er per session
- **Pending intents** — SQLite (overlever daemon-genstart)
- **fleetd** — `POST /v1/fleet/enroll`, `POST /v1/fleet/heartbeat`
- **Adapter health** — offline adapter blokerer plan/execute
- **IPC token** — valgfri `EIRA_IPC_TOKEN` env

Slet `data/eira.db` én gang efter opgradering for nye tabeller, eller kør app (auto-migration).

```powershell
$env:EIRA_IPC_TOKEN = "dev-secret"
```

## Kør daemons separat (som produktion)

**Terminal 1:**
```powershell
python -m app.daemons.runner
```

**Terminal 2:**
```powershell
uvicorn app.http_bridge:app --reload --port 8765
```

## IPC smoke test

```powershell
python scripts/ipc_smoke_test.py
```

Tester: `dashboard.get` → `intent.plan` → step-up block → `identity.step_up` → `intent.confirm`.

## JSON-RPC eksempel (intent.sock)

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

## Cognitive Dashboard

```powershell
cd ui
npm install
npm run dev
```

http://127.0.0.1:5173 → proxy til :8765

## Tauri + direkte IPC

Start daemons først, derefter:

```powershell
cd ui
npm run tauri dev
```

Rust commands: `dashboard_get`, `intent_plan` (kalder sockets direkte).

## Relaterede specs

- [EIRA_Desktop_Architecture_v1.0.md](../../docs/specs/EIRA_Desktop_Architecture_v1.0.md) §6 IPC
- [EIRA_Cognitive_Runtime_v1.0.md](../../docs/specs/EIRA_Cognitive_Runtime_v1.0.md)


---

## 🛡️ Project Veritas-Skjoldet (Informations- & Billedvalidering)

EiraOS indeholder en integreret, kryptografisk og narrativt intelligent modul for informations- og kildekritik (**`veritas-shield/`**):

- **Lag 1: Artikelanalyse (Det Røde Skjold):** 200 regelbaserede parametre for kildeforankring, parthøring og sproglig tone uden AI-hallucination (`veritas-shield/lag1-article-analysis/`).
- **Lag 2: EUDI Wallet Bridge (Det Grønne Skjold):** eIDAS 2.0 / QEAA validering af digitale afsendersignaturer (`veritas-shield/adapters/eudi-wallet-adapter/`).
- **Lag 3: Narrativ Kortlægning (Det Blå Skjold):** Mønstergenkendelse og tidsmæssig provenance i EiraOS Temporal Graph (`veritas-shield/lag3-narrative-mapping/`).
- **C2PA Billed- & Medievalidering:** Hardware-signaturer (Leica, Canon, Sony) og AI-genereringsdetektion (`veritas-shield/adapters/c2pa-image-validator/`).
- **Browser HUD Component:** Interaktiv status-indikator (🟢/🟡/🔴) til EiraOS Tauri browser (`ui/veritas-hud/`).


---

# 🚀 EiraOS 2.0 Architecture — The Six Core Daemons

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
