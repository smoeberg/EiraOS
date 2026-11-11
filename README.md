# EiraOS

EiraOS er et europæisk, leverandørneutralt styresystemlag oven på **Ubuntu 26.04 LTS**. Det samler en persons digitale liv (arbejde, privat, familie, fællesskaber) i adskilte **kontekster**, lader en AI hjælpe med at forstå og foreslå handlinger og sikrer, at intet med konsekvenser sker uden en kontrol, personen kan stole på.

> **AI'en foreslår. Gaten afgør. Systemet udfører.**

## Grundprincipper

Hvert princip er besluttet i en ADR og gjort konkret i en kontrakt under [`specs/`](specs/README.md).

| Princip | Hvad det betyder | Kilde |
|---|---|---|
| Gaten | Alle beskyttede handlinger går gennem Gate Kernel: validering, politik, samtykke, autorisation, udførelse og verifikation. Modellen kan aldrig samtykke eller bekræfte | [GATE-KERNEL](specs/GATE-KERNEL-1.0.md), [ADR-0002](docs/decisions/ADR-0002-gate-to-handlingsfamilier.md) |
| Rettigheder fra Fleet | En organisation styrer sine enheder med signerede rettighedssæt; enheden verificerer dem selv | [ADR-0003](docs/decisions/ADR-0003-rettigheder-fra-fleet.md), [RIGHTS-SET](specs/EIRA-RIGHTS-SET-1.0.md), [FLEET-RIGHTS-API](specs/EIRA-FLEET-RIGHTS-API-1.0.md) |
| Leverandørneutral | Ingen udbyder er indbygget i kernen. Login via enhver OIDC-udbyder; webapps i en udskiftelig motor; Microsoft og andre er tilvalg i adaptere | [ADR-0004](docs/decisions/ADR-0004-gui-arkitektur-vendor-neutral.md) |
| Kontekster | Én Linux-bruger pr. kontekst, egen nøgle, eget hjem (S3/WebDAV), ingen deling mellem kontekster. Personen kan altid tage sine data med (exit-garanti) | [ADR-0005](docs/decisions/ADR-0005-kontekster-og-datas-hjem.md), [EIRA-CONTEXT](specs/EIRA-CONTEXT-1.0.md) |
| Livets indbakke | Al input (mail, beskeder, kalender, telefoni) kommer ind gennem adaptere til én indbakke pr. kontekst. Åbne standarder er førsteklasses | [ADR-0006](docs/decisions/ADR-0006-livets-indbakke.md) |

## Arkitektur

```
┌──────────────────────────────────────────────────────────────────────┐
│  Eira UI (Tauri + React)          Webapps (Web App Manager, planlagt) │
├──────────────────────────────────────────────────────────────────────┤
│  eira-labwc (Wayland-compositor)   eira-consent-agent (betroet sti)  │
├──────────────────────────────────────────────────────────────────────┤
│  Daemons, JSON-RPC over Unix-sockets (/run/eira, SO_PEERCRED)        │
│  intentd (Gate Kernel) · identityd · stated · graphd · delegationd   │
│  fleetd · veritasd · eira-modeld (modellen, egen bruger, ingen net)  │
├──────────────────────────────────────────────────────────────────────┤
│  Ubuntu 26.04 LTS: kernel, systemd, AppArmor, greetd                 │
└──────────────────────────────────────────────────────────────────────┘
```

Den samlede arkitektur er beskrevet i [EiraOS Architecture Baseline 1.0](docs/architecture/eiraos-architecture-baseline-1.0.md).

## Status

Ærlig status pr. november 2026. "Pakket" betyder, at komponenten er i `.deb`-pakken og afprøves i VM-acceptancetesten i CI.

| Komponent | Status | Pakket |
|---|---|---|
| `intentd` med Gate Kernel | Implementeret: otte lag, audit-kæde med segl i journalen, rettighedssæt fra Fleet | Ja |
| `identityd` | Implementeret: OIDC-login, sessioner, samtykkenøgle | Ja |
| `stated`, `graphd`, `delegationd`, `veritasd` | Implementeret | Ja |
| `fleetd` | Implementeret: tilmelding af enheder, synkronisering. Synkroniseringen må ikke bære brugerdata (EIRA-CONTEXT §10) | Ja |
| `eira-modeld` | Implementeret: modellen kører som egen bruger, uden net, og gaten afviser den uden en menneskelig delegation | Ja |
| `eira-labwc` | labwc 0.20.3 med en hærdet konfiguration | Egen pakke, afprøvet i CI |
| Samtykkeagenten | Kontrakt [EIRA-CONSENT-AGENT](specs/EIRA-CONSENT-AGENT-0.1.md); implementering under review | Nej |
| Kontekster (`eira-contextd`) | Kontrakt og testplan accepteret; ikke implementeret. `app/daemons/contextd.py` er en gammel prototype, der skal erstattes | Nej |
| Web App Manager, livets indbakke | Besluttet i ADR-0004 og ADR-0006; ingen kontrakt endnu | Nej |
| `walletd`, `presenced` | Prototyper, som altid afviser eller kun lever i hukommelsen | Nej |

Hver kontrakt har sin egen statustabel over, hvad der er implementeret og verificeret.

## Dokumentation

- **Kontrakter:** [`specs/`](specs/README.md)
- **Beslutninger:** [`docs/decisions/`](docs/decisions/) (ADR-0001–0006)
- **Arkitektur og GUI:** [`docs/architecture/`](docs/architecture/)
- **Installation på en pc:** [`docs/INSTALL.md`](docs/INSTALL.md)
- **Vision og forslag:** [`docs/manifest/`](docs/manifest/), [`docs/proposals/`](docs/proposals/)
- **Arkiv** (tidligere faser, ikke normativt): [`docs/archive/`](docs/archive/README.md)

## Udvikling

Krav: Linux (daemon-IPC'en bruger `SO_PEERCRED`), Python 3.11+, Node.js 20+ og Rust (stable) til UI'et.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
alembic upgrade head

# Daemons i deres egen proces, som i produktion
python -m app.daemons.runner --socket-dir data/run

# Eira UI (i en anden terminal)
cd ui && npm ci && EIRA_RUN_DIR="$(cd .. && pwd)/data/run" npm run tauri dev
```

UI'et taler med daemons gennem én Tauri-kommando, `send_ipc_request` (`ui/src-tauri/src/ipc.rs`). Daemons taler newline-framet JSON-RPC 2.0 over Unix-sockets i `data/run/` under udvikling og `/run/eira/` i produktion.

`app/http_bridge.py` er en HTTP-bro **kun til udvikling**; den er ikke med i produktionspakken.

### Tests

```bash
python -m pytest -q          # Python
ruff check app tests         # lint
cd ui && npx tsc --noEmit && npm test
cargo test --workspace
```

Pakken og installations-ISO'et bygges og afprøves i en VM af workflowet `packaging-acceptance` (se [`docs/INSTALL.md`](docs/INSTALL.md)).

## Licens

Se [LICENSE](LICENSE).
