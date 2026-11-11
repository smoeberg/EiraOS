# EIRA Desktop Architecture v1.0

**Status:** Normativ — præsentationslag + session  
**Dato:** 3. juli 2026  
**Projekt:** EIRA OS  
**Relateret:**
- [EIRA Platform Principles v1.0](EIRA_Platform_Principles_v1.0.md)
- [EIRA_Ubuntu_Integration_v0.1.md](EIRA_Ubuntu_Integration_v0.1.md) §3
- [EIRA_OSS_Integration_Manifest_v0.1.md](EIRA_OSS_Integration_Manifest_v0.1.md) §5.7
- [EIRA_User_Experience_Logic_v0.1.md](EIRA_User_Experience_Logic_v0.1.md)
- [EIRA_Cognitive_Runtime_v1.0.md](EIRA_Cognitive_Runtime_v1.0.md)
- [EIRA_Paradigm_Bridging_Analysis_v0.1.md](EIRA_Paradigm_Bridging_Analysis_v0.1.md)
- [prototype/phase1/ui/](../../prototype/phase1/ui/) — reference UI

---

## 1. Scope

Dette dokument definerer **hvordan EIRA PC'ens skærm fungerer teknisk** — fra Wayland-session til Cognitive Interface — inklusive:

- Explorer Mode og Builder Mode
- `eira-shell` (Tauri) som application shell
- IPC mellem UI og Rust-daemons
- Regler for embedded WebViews og legacy-apps
- Hvad der **ikke** er browser, selv om det ligner det

**Spørgsmål dokumentet besvarer:**

> *Er hele frontenden en "Chrome clone"? Hvad kører i WebView, og hvad kører native?*

**Uden for scope:** Fleet Console (central web-portal), adapter-implementering, Policy Compiler backends — se respektive specs.

---

## 2. Arkitektonisk beslutning (ADR)

### 2.1 Kernebeslutning

> **Explorer Mode er en fullscreen application shell (Tauri + system WebView) — ikke et desktop-miljø.**

Det er bevidst den samme **model som Chrome OS** (shell = primær UI), men med EIRA-semantik (Intent + Actions + Trust), ikke faner og URL-bar.

### 2.2 Beslutningsmatrix

| Alternativ | Beslutning | Begrundelse |
|------------|------------|-------------|
| Custom compositor (COSMIC-lignende) | **NEJ** | Accessibility, vedligehold, skaler; bryder "usynligt Linux" |
| GNOME/KDE som hoved-UI (Explorer) | **NEJ** | Føles som "Linux desktop 2000"; bryder UX-principper |
| Electron + bundlet Chromium | **NEJ** | Tung (~200 MB), stor angrebsflade, duplikerer system-WebView |
| **Tauri 2 + WebKitGTK (Linux)** | **JA** | Native shell, system-WebView, Rust IPC, lille footprint |
| Minimal WM (labwc / cage) | **JA** | Fullscreen shell; vinduer kun i Builder |
| React i shell-UI | **JA** | Cognitive Interface; WCAG-testbar HTML/CSS |

### 2.3 Hvad "Chrome clone" betyder — og ikke betyder

| Påstand | Sandt? | Præcisering |
|---------|--------|-------------|
| "Hele EIRA er en browser" | **Nej** | Kun **præsentationslaget** renderer i WebView |
| "Explorer er en browser" | **Delvist** | Det er en **application shell** der bruger WebView til UI — ikke en generel browser |
| "Vi shipper Chromium" | **Nej** | WebKitGTK via systemet (Tauri); ikke Electron |
| "Brugeren ser faner og URL-bar" | **Nej** | Trust-dashboard, journeys, handlingskort, intent-input |
| "Al logik er JavaScript" | **Nej** | Intent, Identity, Graph, Adapters = **Rust daemons** |

### 2.4 Platform Principles

> EIRA erstatter ikke Linux. EIRA gør Linux brugbar for vidensarbejdere.

Desktop-arkitekturen **genopfinder ikke** display stack. Den **orkestrerer** Wayland + minimal compositor + én fullscreen app.

---

## 3. Fuld desktop-stak

```
┌─────────────────────────────────────────────────────────────────┐
│  COGNITIVE INTERFACE (lag 14)                                    │
│  eira-shell UI — React i Tauri WebView                          │
│  Trust · Journeys · Handlingskort · Intent-input · Rationale    │
└────────────────────────────┬────────────────────────────────────┘
                             │ Tauri commands + IPC (Unix socket)
┌────────────────────────────▼────────────────────────────────────┐
│  eira-shell CORE (Rust, samme proces som Tauri backend)         │
│  Session state · Mode switch · Embedded view host · Portal bridge │
└────────────────────────────┬────────────────────────────────────┘
                             │ D-Bus / Unix socket
┌────────────────────────────▼────────────────────────────────────┐
│  EIRA DAEMONS (separate processer — aldrig i browseren)         │
│  eira-identityd · eira-intent-engine · eira-object-graphd       │
│  eira-governance-agent · eira-legacy-runtime · adapter-host     │
└────────────────────────────┬────────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────────┐
│  UBUNTU OSS (EIRA orkestrerer, ejer ikke)                       │
│  sssd · NetworkManager · CUPS · PipeWire · xdg-desktop-portal   │
└────────────────────────────┬────────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────────┐
│  DISPLAY SESSION                                                 │
│  Wayland · labwc/cage · XWayland (whitelist) · PipeWire         │
└────────────────────────────┬────────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────────┐
│  Ubuntu LTS + kernel + firmware                                │
└─────────────────────────────────────────────────────────────────┘
```

**Regel:** Ingen EIRA-daemon kommunikerer med internettet direkte fra WebView. UI taler kun med lokale sockets.

---

## 4. To tilstande: Explorer og Builder

### 4.1 Explorer Mode (95 % af brugere)

| Egenskab | Specifikation |
|----------|---------------|
| Layout | Fullscreen, ingen panel, ingen dock, ingen skrivebordsikoner |
| Navigation | Trust + handlinger + journeys — **ikke** filer/mapper |
| Vinduer | Ingen (undtagen modal overlays og embedded views) |
| WM-interaktion | cage foretrækkes (single-app); labwc hvis Builder-toggle kræves |
| Input | Intent-felt altid tilgængeligt (UX regel 6) |
| Boot-mål | Explorer synlig < 60s efter login ([OSS Manifest](EIRA_OSS_Integration_Manifest_v0.1.md)) |

**Mette ser kun "EIRA".** Aldrig "åbn Public360", aldrig filsti.

### 4.2 Builder Mode (~5 % — IT, udviklere, power users)

| Egenskab | Specifikation |
|----------|---------------|
| Formål | Break-glass: terminal, filer, Docker, virt-manager |
| Layout | labwc med panel; flere vinduer tilladt |
| POSIX | `/home` synlig — normal Ubuntu-oplevelse |
| Adgang | Policy-styret: rolle, OU, eller eksplicit bruger-flag |
| Exit | Tilbage til Explorer via shell — ikke logout |

> Builder er **bevidst undtagelsen** — ikke produktvisionen. ([Paradigm Bridging](EIRA_Paradigm_Bridging_Analysis_v0.1.md) §C)

### 4.3 Mode-switch

```
Explorer  ←── policy / bruger (IT) ──→  Builder
    │                                      │
    └──────── eira-shell styrer ──────────┘
```

| Trigger | Adfærd |
|---------|--------|
| IT-policy `builder.allowed: true` + genvej | Overlay: "Skift til Builder" |
| IT-policy `builder.allowed: false` | Skjult — ingen escape for slutbruger |
| Auto (fremtid) | Rolle-baseret ved login — policy, ikke hardcoded |

Mode-switch emitter Intent Audit event (`presentation.mode_changed`).

---

## 5. Pakken `eira-shell`

### 5.1 Opdeling

| Del | Teknologi | Ansvar |
|-----|-----------|--------|
| **eira-shell-ui** | React + TypeScript + Vite | Cognitive Interface komponenter |
| **eira-shell-core** | Rust (Tauri backend) | IPC, session, embedded views, portals |
| **eira-shell** (binær) | Tauri 2 | Wayland fullscreen client, autostart |

### 5.2 UI-moduler (Explorer)

| Modul | Datakilde | Beskrivelse |
|-------|-----------|-------------|
| `Dashboard` | object-graphd + intent-engine | Hilsen, fokus, tilstand |
| `TrustPanel` | trust/evidence service | Trust-badges, kilder |
| `JourneyPanel` | journey orchestrator | Progress, trin |
| `ActionCards` | agent prioritizer | Handlingskort (regel 4: én skriger) |
| `IntentBar` | intent-engine | Parse → plan → bekræft |
| `RationaleOverlay` | reasoning engine | "Fordi: …" før execute |
| `StepUpFlow` | identityd | MitID / org_acting — inline, ikke separat app |
| `EmbeddedView` | shell-core host | Begrænset web/native indlejring |

### 5.3 Referenceimplementering

Prototype: `eira-os/prototype/phase1/ui/` — React dashboard mod HTTP API.  
Produktion: samme UI ind i Tauri; HTTP erstattes af IPC til `eira-intent-engine` m.fl.

---

## 6. IPC-kontrakt (normativ)

### 6.1 Transport

| Fra | Til | Transport |
|-----|-----|-----------|
| eira-shell-ui | eira-shell-core | Tauri `invoke()` |
| eira-shell-core | eira-* daemons | Unix domain socket `/run/eira/*.sock` |
| eira-shell-core | system (portals) | D-Bus `org.freedesktop.portal.*` |
| Daemons indbyrdes | | D-Bus + Unix socket (ingen HTTP localhost i MVP) |

**Anti-pattern:** UI → `http://127.0.0.1:8765` i produktion (kun prototype).

### 6.2 Socket-layout

```
/run/eira/
  identity.sock      → eira-identityd
  intent.sock        → eira-intent-engine
  graph.sock         → eira-object-graphd
  governance.sock    → eira-governance-agent (read-only for shell)
  legacy.sock        → eira-legacy-runtime
```

### 6.3 Eksempel: dashboard (JSON-RPC 2.0 over socket)

**Request:**
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "dashboard.get",
  "params": { "actor_id": "mette@kommune.dk" }
}
```

**Response:**
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "greeting": "Hej Mette",
    "focus": "Kommunepilot",
    "state": "Arbejde",
    "trust_items": [],
    "active_journeys": [],
    "mistral_available": true
  }
}
```

### 6.4 Metoder (MVP vertical slice)

| Metode | Daemon | Beskrivelse |
|--------|--------|-------------|
| `dashboard.get` | intent-engine | Aggregér dashboard-state |
| `intent.parse` | intent-engine | Parse raw input |
| `intent.plan` | intent-engine | Parse + capability + agency |
| `intent.confirm` | intent-engine | Bekræft og kø execute-pipeline |
| `journey.list` | intent-engine | Aktive journeys |
| `journey.advance` | intent-engine | Afslut trin |
| `identity.session` | identityd | Aktuel session + assurance |
| `identity.step_up` | identityd | Start step-up flow |
| `graph.temporal_query` | object-graphd | Validity window query |
| `presentation.mode_get` | shell-core | Explorer / Builder |
| `presentation.mode_set` | shell-core | Skift mode (policy-gated) |
| `legacy.open` | legacy-runtime | Start RDP/VM session |

Alle write-metoder emitter Intent Audit via kalende daemon.

### 6.5 Fejlmodel

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "error": {
    "code": -32001,
    "message": "assurance_required",
    "data": {
      "required": "org_acting",
      "current": "eid_low",
      "user_message": "Denne handling kræver MitID Erhverv"
    }
  }
}
```

UI **må ikke** parse fejl ad hoc — brug `user_message` til rationale (UX regel 5).

---

## 7. Embedded views og WebView-regler

### 7.1 Hvornår indlejres indhold?

| Scenario | Mekanisme | Bruger ser |
|----------|-----------|------------|
| M365 / SharePoint dokument | Adapter returnerer `embed_url` | Indhold i EIRA-ramme — ingen browser-chrome |
| Public360 web-UI (midlertidig) | Embedded WebView | Samme |
| Legacy Win32 / VBA | `legacy.open` → RDP/KVM | Session i ramme eller fullscreen — stadig "EIRA" |
| LibreOffice (whitelisted) | Legacy Bridge + native app | App-vindue — **kun** hvis policy tillader |
| Generel websøgning | **FORBUDT** i Explorer | — |

### 7.2 WebView-sikkerhed (normativ)

| Regel | Beskrivelse |
|-------|-------------|
| W1 | Ingen arbitrær URL-navigation — kun adapter-godkendte URLs |
| W2 | CSP: `default-src 'self'; connect-src 'none'` for shell-UI |
| W3 | Embedded views: isoleret WebView-instans per session |
| W4 | Ingen `window.open` til ekstern browser uden policy |
| W5 | Cookies/session fra embedded view må ikke persistere på tværs af actors |
| W6 | All navigation logged til Intent Audit |

### 7.3 Chrome OS-parallellen

| Chrome OS | EIRA |
|-----------|------|
| PWA i vindue | Embedded adapter-view |
| Ingen adresselinje | Ingen URL-bar — intentioner erstatter navigation |
| Linux apps (Crostini) | Builder Mode + Legacy Runtime |

---

## 8. Legacy Bridge og Legacy Runtime

### 8.1 To forskellige lag

| Lag | Formål | Teknologi |
|-----|--------|-----------|
| **Legacy Runtime** | Win32/RDP/VM sessions | FreeRDP, libvirt/KVM |
| **Legacy Filesystem Bridge** | "Gem som…" for POSIX-apps | eira-fuse, xdg-desktop-portal override |

Se [Paradigm Bridging](EIRA_Paradigm_Bridging_Analysis_v0.1.md) §A.

### 8.2 Explorer-flow for legacy

```
Bruger: "Åbn Budget.xlsm"
  → intent.plan → capability: legacy.excel
  → legacy-runtime: vælg RDP | VM | LibreOffice (policy)
  → Resultat returneres til Object Graph — ikke separat desktop
```

Brugeren trykker **[Åbn]** — systemet vælger sti. ([Windows Parity](EIRA_Windows_Parity_Architecture_v0.1.md) §3.5)

### 8.3 Portal-integration

File picker, screencast, open-uri:

- **Primary:** `xdg-desktop-portal` + EIRA portal implementation
- **Fallback:** GTK/Qt native dialogs i Builder only

---

## 9. Session og boot

### 9.1 Autostart-kæde (systemd)

```
multi-user.target
  → eira-firstboot.service (engangs enroll)
  → graphical.target
  → eira-session.service
       → labwc/cage
       → eira-shell.service (fullscreen)
       → eira-identityd, eira-governance-agent, …
```

### 9.2 Login-flow

```
1. GDM/greetd eller cage direkte login
2. eira-identityd: Entra OIDC / passkey
3. eira-shell: Explorer Mode default
4. dashboard.get: prefetch fokus + handlingskort
5. Bruger klar — ingen skrivebord, ingen startmenu
```

### 9.3 Factory Enroll

Se [EIRA_Factory_Enroll_v0.1.md](EIRA_Factory_Enroll_v0.1.md). Desktop krav: første boot ender i Explorer med tom Object Graph — ikke installer-wizard.

---

## 10. Offline og performance

| Komponent | Offline-adfærd |
|-----------|-----------------|
| eira-shell UI | ✅ Lokal — Tauri assets på disk |
| Dashboard read | ✅ Cached graph + trust |
| Intent parse (rules) | ✅ På cachede entiteter |
| Intent parse (LLM) | ⚠️ Kræver lokal Ollama — fallback til rules |
| Intent execute (write) | ❌ Fail closed uden netværk + assurance |
| Embedded view | ❌ Kræver netværk — vis kø-status |

**"Dead Desktop" er diskvalificerende** — Explorer skal vise cached state + tydelig offline-indikator ([Paradigm Bridging](EIRA_Paradigm_Bridging_Analysis_v0.1.md) §B).

### 10.1 Performance-mål (MVP)

| Mål | Target |
|-----|--------|
| Cold boot → Explorer | < 60s |
| dashboard.get | < 200ms (p95, warm) |
| intent.plan (rules) | < 100ms (p95) |
| Mode switch Explorer↔Builder | < 2s |

---

## 11. Sikkerhed

### 11.1 Lag-rækkefølge (uændret)

```
1. Ubuntu MAC (AppArmor)     ← hard ceiling
2. EIRA Capability Layer
3. EIRA Intent / Agent
4. Presentation (eira-shell)
```

AppArmor vinder ved konflikt — log begge, vis rationale ([Ubuntu Integration](EIRA_Ubuntu_Integration_v0.1.md) §4).

### 11.2 eira-shell AppArmor-profil

- Netværk: kun Unix sockets til `/run/eira/*` og D-Bus
- Ingen raw `CAP_SYS_ADMIN`
- Embedded WebView: separat child-profil hvis muligt

### 11.3 Supply chain

- UI assets bundled i `.deb` / Flatpak — ingen CDN i produktion
- `npm` build reproducible i CI; SBOM per release train

---

## 12. Accessibility

| Tilstand | Tilgang |
|----------|---------|
| Explorer | WCAG 2.1 AA via HTML/CSS — axe-core i CI |
| Keyboard | Fuld keyboard-navigation af handlingskort + intent-bar |
| Skærmlæser | WebKit a11y tree i Explorer |
| Builder | Ubuntu Orca + standard GTK a11y |
| High contrast | CSS `prefers-contrast` + policy tema |

**Ikke** genopfind skærmlæser i custom compositor.

---

## 13. Fleet og versionering

| Felt | Eksempel |
|------|----------|
| Pakke | `eira-shell_2.4.1` |
| Release train | `EIRA 2.4 @ Ubuntu 24.04` |
| Fleet inventory | eira-shell version rapporteres til governance-agent |

Desktop-opdateringer følger staged rollout — ikke bruger-initieret `apt upgrade` ([Ubuntu Integration](EIRA_Ubuntu_Integration_v0.1.md) §2).

---

## 14. Anti-patterns (forbudt)

| Anti-pattern | Hvorfor |
|--------------|---------|
| Electron + Chromium bundle | Tung, sikkerhed, duplikeret stack |
| GNOME Shell som Explorer | Forkert produkt |
| HTTP REST mellem UI og daemons i prod | Angrebsflade, unødvendig |
| Arbitrær browser i Explorer | Bryder UX regel 1 |
| Silent execute fra UI | Bryder UX regel 5 + Intent Protocol |
| Custom compositor fra bunden | Vedligehold, a11y |
| Remote UI (thin client) | Bryder local-first; ikke EIRA OS |

---

## 15. Implementeringsfaser

| Fase | Leverance | Map til prototype |
|------|-----------|-------------------|
| **P0** | eira-shell fullscreen på labwc + static dashboard | `ui/` i browser |
| **P1** | IPC til intent-engine + identityd + graphd | `app/daemons/` + `data/run/*.sock` |
| **P2** | intent.plan + step-up inline | Phase 2 backend + `intent.confirm` |
| **P3** | Embedded view (én adapter) | M365 eller Public360 |
| **P4** | Builder Mode toggle | labwc panel |
| **P5** | Legacy Runtime fra Explorer | FreeRDP integration |

Vertical slice (Sprint 0): P0 + P1 + P2.

---

## 16. Dokumenthierarki

```
EIRA_Platform_Principles_v1.0.md
EIRA_Ubuntu_Integration_v0.1.md          §3 desktop (kort)
EIRA_Desktop_Architecture_v1.0.md        ← dette dokument (fuld)
EIRA_User_Experience_Logic_v0.1.md       UX-regler Explorer
EIRA_Cognitive_Runtime_v1.0.md         Trust, Journey, Interface
EIRA_OSS_Integration_Manifest_v0.1.md  §5.7 display/session
EIRA_Paradigm_Bridging_Analysis_v0.1.md Legacy Bridge
```

---

## 17. Opsummering

| Spørgsmål | Svar |
|-----------|------|
| Bæres hele frontenden af en Chrome clone? | **Explorer-UI: ja (WebView-shell). Hele EIRA: nej.** |
| Shipper vi Chromium? | **Nej — WebKitGTK via Tauri.** |
| Er det en browser? | **Nej — beslutnings-shell med Intent, ikke faner.** |
| Hvor kører intelligensen? | **Rust daemons — ikke i JavaScript.** |
| Hvad med IT/legacy? | **Builder Mode + Legacy Runtime — bevidst undtagelser.** |

> **eira-shell er skrivebordet for vidensarbejdere — men motoren sidder i Rust under UI'et.**

---

*EIRA Desktop Architecture v1.0 — Fortroligt udviklingsdokument*
