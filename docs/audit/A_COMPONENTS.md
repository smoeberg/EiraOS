# A — Komponentkort (statiske kildebeviser)

**Audit-base:** `main` / `audit/a-components-ipc` ved commit `5b750114523e0d5f02a471d9feaccd35712c1c76`  
**Metode:** Gennemgang af kildefiler via GitHub-indhold. Ingen daemon er startet i et Ubuntu-runtime-miljø i denne audit; derfor er *socket oprettet* ikke markeret som runtime-verificeret.  
**Scope:** Afsnit A i `docs/EIRA_GUI_Audit_Checklist.md`. Ingen kodeændringer.

## Komponentkort

| Komponent/ansvar | Fil og entrypoint | Socket / endpoint | Modenhed | Startstatus / begrundelse |
|---|---|---|---|---|
| State/audit (`stated`) | `app/daemons/stated.py` · `register_state_handlers()`; startet af `app.daemons.runner` | `stated.sock` | **Real**, med SQLite/Rust-store-valg og audit trail | Registreret i runner. Kan fejle ved import/store-init; faktisk start ikke runtime-testet. |
| Identity (`identityd`) | `app/daemons/identityd.py` · `register_identity_handlers()` | `identityd.sock` | **Real, delvist konfigurationsafhængig** | Registreret i runner. Provider-verifikation er ikke konfigureret, hvis provider-konfiguration/trust anchors mangler; daemon rapporterer dette via health. |
| Fleet (`fleetd`) | `app/daemons/fleetd.py` · `register_fleet_handlers()` | `fleetd.sock` | **Real/prototype-blandet** | Registreret i runner. Initialisering opretter/indlæser lokale secrets og registry; kan fejle på filsystem-/DB-forhold. WebSocket-server er valgfri og separat. |
| Veritas (`veritasd`) | `app/daemons/veritasd.py` · `register_veritas_handlers()` | `veritasd.sock` | **Real prototype** | Registreret i runner; lagene er implementeret som Python-komponenter. Eksterne trust-data kan være uopsat. Faktisk start ikke runtime-testet. |
| Intent (`intentd`) | `app/daemons/intentd.py` · `register_intent_handlers()`; kalder også legacy-registrering fra `app/daemons/intent_engine.py` | `intentd.sock` | **Real/prototype-blandet** | Registreret i runner. Legacy handler-sæt og nyt `intent.execute`-flow deler samme socket. Eksekvering i `app/executor.py` er eksplicit stub og kalder ingen ekstern API. |
| Graph (`graphd`) | `app/daemons/graphd.py` · `register_graph_handlers()` | `graphd.sock` | **Real/prototype-blandet** | Registreret i runner. Temporal/provenance queries bruger DB; spatial snapshot henter state via `stated.sock`. Faktisk start ikke runtime-testet. |
| Wallet (`walletd`) | `app/daemons/walletd.py` · kun `WalletDaemon` + demo under `__main__` | **Ingen IPC-socket** | **Stub/demo** | Ikke i `DAEMON_NAMES`, `REGISTRARS`, `DAEMON_ALIASES` eller `DAEMON_PORTS`. Ikke startbar via fælles runner; metoderne returnerer simulerede betalings-/credential-data. |
| Presence (`presenced`) | `app/daemons/presenced.py` · kun `PresenceDaemon` + demo under `__main__` | **Ingen IPC-socket** | **Stub/demo** | Ikke registreret i runner eller IPC-path/transport. In-memory annotations og hardcoded collaborator/timestamp; ingen IPC-server. |
| Context (`contextd`) | `app/daemons/contextd.py` · kun `ContextDaemon` + demo under `__main__` | **Ingen IPC-socket** | **Stub/demo** | Ikke registreret i runner eller IPC-path/transport. In-memory aktiv kontekst; ingen IPC-server. |
| Capability (ekstra) | `app/daemons/capabilityd.py` · kun `CapabilityDaemon` + demo under `__main__` | **Ingen IPC-socket** | **Stub/demo / ikke koblet til runner** | Ikke en af README's syv kernedaemons og ikke registreret i fælles runner. Må ikke tælles som aktiv IPC-daemon. |
| Legacy intent engine | `app/daemons/intent_engine.py` · `register_intent_handlers()` kaldt fra `intentd` | **Deler `intentd.sock`** | **Aktiv kompatibilitetsimplementering** | Ikke selvstændig daemon. Registrerer dashboard/parse/plan/confirm/journey/capability/presentation-metoder i intentd-serveren. |

## Runner- og socket-fakta

Kilde: `app/daemons/runner.py`, `app/ipc/paths.py`, `app/ipc/transport.py`.

- `python -m app.daemons.runner` starter **seks** services: `stated`, `identityd`, `fleetd`, `veritasd`, `intentd`, `graphd`.
- `--daemon all` betyder disse seks; ikke README's syv kernedaemons (`identityd`, `walletd`, `veritasd`, `graphd`, `presenced`, `contextd`, `intentd`).
- De seks Unix-socket-navne er `stated.sock`, `identityd.sock`, `fleetd.sock`, `veritasd.sock`, `intentd.sock`, `graphd.sock`.
- Standard socket-dir er `/run/eira`, hvis processen er root og kataloget allerede findes; ellers `data/run/` relativt til repoet. `EIRA_RUN_DIR` overstyrer dette. Runnerens `--socket-dir` default er `/run/eira`.
- Windows bruger TCP-loopback/portfiler i stedet for Unix sockets; det er ikke bevis for Ubuntu/Wayland-runtime.
- `JsonRpcServer.start()` binder socket i baggrundstråd og venter på ready-event; runner ruller allerede startede daemons tilbage, hvis en senere daemon fejler.

## Overlap og dataflow

- `app/daemons/intentd.py` registrerer `intent.execute`, og indlæser derefter `register_intent_handlers` fra `app/daemons/intent_engine.py`. Det er **to intent-API'er i én socket**, ikke to selvstændige daemon-processer.
- `app/intent_parser.py` indeholder både parser-/planfunktioner til legacy `intent_engine` og en separat `IntentParser`-klasse til den nye `intentd`-service. Det er et reelt overlap i intent-domænet, men en refaktorering er uden for issue-scope.
- `app/http_bridge.py` er dokumenteret som dev bridge; ved FastAPI-start kalder den `start_daemons()`, medmindre `EIRA_DISABLE_DAEMONS=1`.
- `app/executor.py` returnerer `status: executed_stub` og teksten “prototype — ingen ekstern API”; intent-confirmation er derfor ikke bevis på en reel ekstern handling.
- `app/graph_context.py` leverer relationstræ/“why”-bullets til graph/UI-kontekst, men er ikke en daemon eller socket.
- README's kernedaemon-liste og faktisk runner-liste er uens. De tre README-daemons `walletd`, `presenced`, `contextd` kan ikke bestå kravet “start alle syv og opret sockets” med den nuværende runner: de mangler registrering og canonical socket mapping. Dette er dokumenteret som en konkret blocker, ikke skjult som en succes.

## Runtime-beviser og gate

**Ikke udført i denne audit:** `python -m app.daemons.runner`, `ls -la /run/eira`, `systemctl status`, `wayland-info` og `python scripts/ipc_smoke_test.py`. GitHub-kildefiladgang giver ikke en Ubuntu-host eller adgang til brugerens systemd/Wayland-session; jeg vil ikke opfinde output.

Der findes en kandidat til lokal smoke-test: `python scripts/ipc_smoke_test.py`. Den bør køres på Ubuntu i et rent testmiljø med `EIRA_RUN_DIR` sat til en midlertidig mappe og `EIRA_STATE_DB`/databasen isoleret. Statisk review viser, at scriptet kalder `identity.step_up` uden `step_up_token`, mens `identity_step_up()` afviser manglende token. Derfor kan smoke-testen fejle ved det trin, selv hvis daemon-start/socket-binding virker.

**Gate-status:** Ikke bestået endnu. Seks daemonregistreringer er synlige statisk; de syv-daemon-krav er blokeret af manglende `walletd`/`presenced`/`contextd` IPC-registrering, og runtime-bevis mangler. Ingen kodeændring foreslås i denne issue, fordi scope kun tillader de to audit-dokumenter.
