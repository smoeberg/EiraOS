# B — IPC-kontrakter og socket-sikkerhed

**Audit-base:** `main` / `audit/a-components-ipc` ved commit `5b750114523e0d5f02a471d9feaccd35712c1c76`  
**Metode:** Statisk gennemgang af `app/daemons/*.py` og `app/ipc/*.py`. Runtime-permissions er ikke målt på Ubuntu.  
**Scope:** Afsnit B i `docs/EIRA_GUI_Audit_Checklist.md`. Ingen kodeændringer.

## Transport og framing

- Unix-socket serveren læser **én JSON-request pr. linje** (newline-framing) og sender én JSON-response pr. linje.
- På Unix bruger transporten `AF_UNIX`; Windows bruger loopback TCP og portfiler. Det er en udviklings-/kompatibilitetssti, ikke produktionens Unix-socket-kontrakt.
- Klienten `app/ipc/client.py` sender `jsonrpc: "2.0"`, `id: 1`, `method` og `params`, og læser første newline-framed svar.
- `JsonRpcServer.handle_line()` parser JSON og kræver et objekt, men **validerer ikke** `jsonrpc == "2.0"`, at `id` er til stede/gyldigt, eller JSON-RPC-reglen om notifications. Serveren svarer også på requests uden `id`. Derfor er formatet JSON-RPC-lignende, men ikke fuld JSON-RPC 2.0-overholdelse.
- Ukendt metode giver `-32601`; ugyldige params giver `-32602`; uventet handler-fejl giver `-32603`. Alle servergenererede svar har `jsonrpc: "2.0"`, `id` og enten `result` eller `error`.
- `params` normaliseres via `request.get("params") or {}`; tomme/falsey værdier som `null`, `false`, `0` eller tom streng behandles dermed som tomt objekt i stedet for at blive afvist som ugyldig params-type.

## Metoder pr. socket

Alle nedenstående metoder er registreret i `register_*_handlers()`; `health` findes på alle seks aktive sockets.

| Socket | Metoder |
|---|---|
| `stated.sock` | `state.append`, `state.get`, `state.get_by_hash`, `state.get_history`, `state.list`, `state.sync_push`, `state.sync_pull`, `audit.append`, `audit.verify`, `health` |
| `identityd.sock` | `identity.session`, `identity.step_up`, `identity.providers`, `identity.verify_production_certificate`, `health` |
| `fleetd.sock` | `fleet.enroll`, `fleet.heartbeat`, `fleet.device.get`, `fleet.list`, `fleet.pairing.create`, `fleet.device.enroll`, `fleet.device.revoke`, `sync.handshake`, `sync.request_blocks`, `sync.push_blocks`, `health` |
| `veritasd.sock` | `veritas.evaluate`, `veritas.process_evidence`, `health` |
| `intentd.sock` | `intent.execute`, `dashboard.get`, `intent.parse`, `intent.plan`, `intent.confirm`, `journey.list`, `journey.get`, `journey.advance`, `capability.list`, `presentation.mode_get`, `presentation.mode_set`, `health` |
| `graphd.sock` | `graph.temporal_query`, `graph.context`, `graph.provenance.trace`, `graph.spatial_snapshot`, `health` |

### Metoder, som mangler en socket

| Komponent | Kode findes | Manglende kontrakt |
|---|---|---|
| `walletd` | `WalletDaemon.optimize_and_pay()`, `list_credentials()` | Ingen `register_wallet_handlers`, ingen JSON-RPC server, ingen socket alias/path/port. Returnerer simuleret `PAID` og hardcoded credentials. |
| `presenced` | `PresenceDaemon.annotate_object()`, `get_object_presence()` | Ingen handlerregistrering/socket; in-memory demo. |
| `contextd` | `ContextDaemon.set_context()`, `get_context()` | Ingen handlerregistrering/socket; in-memory demo. |

## Fejlformat og UX-regel `user_message`

JSON-RPC-fejl er `{"jsonrpc":"2.0","id":...,"error":{"code":...,"message":"..." ,"data":{...}}}`. UX-reglen er kun delvist opfyldt: flere domænefejl lægger `user_message` i `error.data`, men formatet er ikke centralt håndhævet.

Eksempler fra kildekoden:

- **Med `user_message`:** `identity.step_up` for manglende/ikke-understøttet step-up, `intent.confirm` ved manglende assurance/afklaring, `intent.execute` ved constraint violation, `app/executor.py` ved manglende/offline adapter, og IPC-tokenfejl.
- **Uden garanteret `user_message`:** generisk `METHOD_NOT_FOUND`, ugyldig JSON/params, `stated` valideringsfejl, `graph.temporal_query` manglende parametre, fleet-protokolfejl og generisk `INTERNAL_ERROR`. Handlerens fejltekst havner ofte kun i `error.message`.
- Serveren fjerner interne exception-detaljer ved uventede fejl og sender `Internal daemon error`, hvilket er godt for informationsafgrænsning, men giver ikke UI en dansk brugerbesked.
- `JsonRpcError.data` bliver `{}` når data er falsy, og `error_response()` udelader `data`, når objektet er tomt.

**Konklusion:** `user_message` er et konventionelt felt i udvalgte handlers, ikke en garanteret kontrakt for alle fejl. UI skal have fallback, men en fremtidig ændring bør centralisere mappingen. Ingen kodeændringer foretages i denne audit.

## Socket-permissions og peer-kontrol

Kilde: `app/ipc/socket_security.py`, `app/ipc/transport.py`, `app/daemons/base.py`.

- `setup_unix_socket()` binder socket, sætter mode **0660** som default og forsøger at sætte group til `eira`. Hvis gruppen ikke findes, `resolve_group_gid()` falder tilbage til processens GID. `chown`-fejl ignoreres.
- Socketfilen fjernes først, hvis den allerede findes; `ensure_run_dir()` opretter run-kataloget, men sætter ikke selv eksplicit ejer-/mode-bits på kataloget.
- `JsonRpcServer._serve_client()` kalder `validate_peer_credentials()`, der læser Linux `SO_PEERCRED`. Men serveren sender **ingen** `allowed_uids` eller `allowed_gids`; funktionen indsamler credentials, men håndhæver derfor ingen peer-allowlist. Adgang hviler primært på katalog-/socket-permissions.
- `socket_access_allowed()` findes, men er ikke tilsluttet serverens aktuelle accept-path. `_supplementary_gids()` returnerer altid tom mængde. `secure_socket_path()` håndhæver 0600, men bruges ikke af `bind_server()`; faktisk default er 0660.
- `EIRA_IPC_TOKEN` er valgfri. Hvis miljøvariablen ikke er sat, afviser `strip_and_validate_ipc_auth()` ikke manglende token. Hvis den er sat, sammenlignes token med `hmac.compare_digest`; auth-fejl indeholder `user_message`.
- Daemons med root/systemd-kørsel, manglende `eira`-gruppe eller forkert `/run/eira`-katalog kan få anden adgangsprofil end forventet. Den faktiske mode/owner/group skal verificeres på mål-Ubuntu med `stat`/ `namei -l` og `systemctl`.

## Foreslået runtime-evidens (ikke udført)

Kør på en Ubuntu 24.04 testhost — med isoleret state/database og en dedikeret run-dir:

```bash
set -euxo pipefail
export EIRA_RUN_DIR="$(mktemp -d)"
export EIRA_STATE_DB="$EIRA_RUN_DIR/state.db"
python -m app.daemons.runner --socket-dir "$EIRA_RUN_DIR" &
runner_pid=$!
trap 'kill "$runner_pid" 2>/dev/null || true; wait "$runner_pid" 2>/dev/null || true; rm -rf "$EIRA_RUN_DIR"' EXIT
for name in stated identityd fleetd veritasd intentd graphd; do
  test -S "$EIRA_RUN_DIR/$name.sock"
  stat -c '%n mode=%a uid=%u gid=%g type=%F' "$EIRA_RUN_DIR/$name.sock"
done
python scripts/ipc_smoke_test.py
```

Bemærk: smoke-testen har en statisk identificeret inkonsistens: den kalder `identity.step_up` uden `step_up_token`, mens handleren kræver token. Smoke-testen skal rettes i en separat kodeopgave eller køres med et gyldigt test-token i testdata. Det er ikke gjort her, fordi issue #24 forbyder kodeændringer.

**Gate-status:** JSON-RPC-kontrakterne er kortlagt statisk. Fuld JSON-RPC 2.0 og ensartet `user_message` er ikke opfyldt; peer-credentials er ikke begrænset med allowlist; runtime permissions og daemon-start er ikke målt. De tre manglende daemon-sockets er dokumenteret ovenfor.
