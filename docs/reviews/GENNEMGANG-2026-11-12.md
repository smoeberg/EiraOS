# Eksterne gennemgange 12. november 2026 — fundregister

**Grundlag:** `main` ved `c73fc05` (efter #175). Seks uafhængige gennemgange, kaldt G0–G5 nedenfor.
**Metode:** Hver konkret påstand er tjekket i koden. Vurderingen siger, om fundet holder, ikke hvem der fandt det. Planens id'er henviser til [UDVIKLINGSPLAN](../UDVIKLINGSPLAN.md).

| Kilde | Omfang | Kørte tests |
|---|---|---|
| G0 | Statisk, med linjehenvisninger (terminal, IntentBar, HTTP-bro, dashboard) | Nej |
| G1 | Overordnet, uden filhenvisninger | Nej |
| G2 | Statisk, bredt | Nej |
| G3 | Statisk, dokumentation og links | Nej |
| G4 | Statisk, sikkerhedsgrænser og dokumentation mod kode | Nej |
| G5 | Statisk og kørsel (877 Python-, 92 UI-tests, cargo) | Ja |

**Vurderinger:** *Bekræftet* (holder som beskrevet), *Delvist* (holder, men alvor eller årsag er en anden), *Afvist* (holder ikke), *Rettet* (rettet i PR #185 eller tidligere), *Dækket* (findes allerede, med belæg).

## 1. Sikkerhed og korrekthed

| # | Fund | Kilde | Vurdering | Belæg | Alvor | Plan |
|---|---|---|---|---|---|---|
| S-1 | **Desktop-brugeren kan skrive i `stated`:** `state.append`, `state.sync_push` og `audit.append` har ingen kaldertjek, og socketen er åben for `eira-clients` | G4 | **Bekræftet** | `app/daemons/stated.py:174-184`; `systemd/eira-stated.service` giver socketen til `eira-clients`; ingen handler bruger `_peer` | **Høj**: enhver proces som brugeren kan indsætte tilstandsblokke og audit-hændelser i `stated`. Gatens egen audit (`gate_audit`, FSS-segl) er ikke berørt | F0b.1 |
| S-2 | **`state.sync_push` committer delvist:** ugyldige blokke springes stille over (`except Exception`), gyldige gemmes | G2 (om fleetd) | **Delvist**: hullet er lukket i `fleetd` (`push_blocks` afviser hele batchen), men findes i `stated` | `app/daemons/stated.py:108-135`; `app/daemons/fleetd.py:129-137` | Høj, sammen med S-1 | F0b.1 |
| S-3 | **Ingen adgangsklasse pr. IPC-metode.** Kun gaten, login, samtykkeagenten, `fleetd`, `delegationd` og modelprocessen ser på kalderen | G4, G2 | **Bekræftet** | `PEER_KEY` bruges kun i de nævnte moduler | Høj: S-1 er ét eksempel; næste nye metode kan blive det næste | F0b.2 |
| S-4 | **Terminalen afvises altid:** `presentation.mode_get` uden `session_id` opretter en ny anonym session | G0 | **Bekræftet** | `ui/src/App.tsx:28`, `ui/src-tauri/src/lib.rs:107-136`, `app/daemons/intent_engine.py:20-21` | Høj (funktionsfejl, ikke sikkerhed) | F1.5 |
| S-5 | **Sessioner ud fra påstået `actor_id`:** `ensure_session` opretter sessioner for enhver identitet en klient angiver; `identity.session` returnerer rækken for et givet id | G0 | **Bekræftet** | `app/session_store.py:99-130`, `app/daemons/identityd.py:26-36` | Mellem: gaten godtager kun autentificerede sessioner bundet til UID'en (`app/gate/kernel.py`, test i `tests/test_gate_caller.py`), men UI og tabeller viser påståede navne | F1.5 |
| S-6 | **IntentBar har ingen vej gennem gaten** | G0 | **Bekræftet**. G0's anbefaling om at vise gengivelsen i UI'et **afvises**: efter #175 viser samtykkeagenten den | `ui/src/components/IntentBar.tsx:48`, `app/daemons/intentd.py:231` | Høj (kernefunktion mangler) | F1b |
| S-7 | **LLM-klient i gate-processen:** `app/mistral.py` og `app/intent_parser.py` er pakket og importeres af `intentd`; `dashboard.get` kalder `is_mistral_available()` hver gang, uanset flaget | G5 | **Delvist**: `intentd` har `RestrictAddressFamilies=AF_UNIX`, så kaldet fejler på en installeret maskine. Principbrud og død kode, ingen netadgang | `app/daemons/intent_engine.py:35`, `app/intent_parser.py:298-306`, `systemd/eira-intentd.service:51` | Mellem | F1.2 |
| S-8 | **Den gamle `IntentDaemonService`** kan skrive tilstand efter et CEL-tjek | G4 | **Delvist**: kan ikke nås over IPC (`intent.execute` er `gate_required`), og intet andet modul kalder den. Død kode | `app/daemons/intentd.py:31` (klassen), `:231` (IPC-registreringen) | Lav | F1.2 |
| S-9 | **`build_agency`** udleder delegation af ordene "økonomi"/"skole" i org-enheden | G5 | **Bekræftet**, men indgår kun i den gamle `intent.parse/plan`, ikke i gatens delegation | `app/mistral.py:98-106` | Lav | F1.2 |
| S-10 | **HTTP-broen har skriveruter uden session** (wallet, presence, context) | G0, G5 | **Bekræftet**, kun udviklingsmiljø | `app/http_bridge.py:61-71`; ikke i pakken (`scripts/app_modules.py:43-44`, `tests/test_no_http_bridge_prod.py`) | Lav | F1.6 |
| S-11 | **IPC-tokenet er valgfrit** | G5 | **Delvist**: værre end beskrevet, for tokenet ligger i `/etc/eira/eira.conf` som `root:eira-clients 0640` og beskytter derfor ikke mod desktop-brugeren. Grænsen er socket-rettigheder plus `SO_PEERCRED`, og det står ingen steder | `packaging/debian/postinst:64-71`, `app/ipc/auth.py:14-35` | Mellem (dokumentation; S-3 er den rigtige rettelse) | F0b.2, D-3 |
| S-12 | **Root har altid IPC-adgang** | G5 | **Bekræftet**, bevidst (EIRA-CONSENT-AGENT §9: root er uden for trusselsmodellen) | `app/ipc/socket_security.py:114` | Info | D-3 |
| S-13 | **Stille `except … pass`** | G2 | **Delvist**: 22 steder i den pakkede kode; ingen skjuler en sikkerhedsfejl. Ét bør logge: gatens audit-lyttere (Fleet-ankeret) sluges uden spor | `app/gate/store.py:300-303` | Lav | F1.7 |
| S-14 | **Executors er tynde; `Executor.run` rejser `NotImplementedError`** | G2, G3 | **Afvist som fejl**: bevidst. Ukendte handlinger afvises (fail-closed), og der er to executors (outbox og strøm) | `app/gate/executors.py:54-71`, `tests/test_gate_kernel.py:534` | — | F7 |
| S-15 | **Samtidighed, engangsbillet og crash skal testes** | G3 | **Dækket** | `tests/test_gate_kernel.py:349, 358, 444, 455, 643, 667, 688`; `tests/test_gate_system.py:197, 206` | — | — |
| S-16 | **Hash-paritet Python/Rust/Kotlin** | G2 | **Delvist**: Python↔Rust testes over FFI (`tests/test_android_ffi_state.py`); Android bygges og testes slet ikke i CI | `.github/workflows/` har intet Android-job | Mellem | F1.8 |
| S-17 | **Ingen evidens for ren boot på Ubuntu 26.04** | G2 | **Afvist**: `packaging-acceptance` installerer ISO'et i en VM og kører 72 checks på den installerede pakke | `packaging/installer/ci/eira-ci-report` | — | — |
| S-18 | **`walletd`, `presenced`, `contextd` mangler socket og handlers** | G2 | **Afvist som beskrevet**: de registreres af `runner.py`, men er bevidst ikke pakket. Rigtigt er, at de skal væk | `app/daemons/runner.py:16-27`, `packaging/daemon-policy.json` | — | F1.2 |
| S-19 | **Step-up afviser MitID Erhverv** | G4 | **Bekræftet**, bevidst fail-closed, indtil en betroet udbyder er tilsluttet | `app/daemons/identityd.py:40` | Mellem (funktion mangler) | F4.3 |
| S-20 | **Fleet-interoperabilitet er ikke bevist** mod `eira-fleet-control` | G4 | **Bekræftet**: testvektorerne ligger her, men intet afprøver den anden side | `tests/vectors/rights-set/` | Mellem | F1.9 |
| S-21 | **To veje til databaseskemaet:** Alembic og `init_db()` med `ALTER TABLE` ved opstart | G5 | **Bekræftet** | `alembic/versions/001_initial_schema.py`, `app/session_store.py:38-95` | Lav | F1.10 |
| S-22 | **Forældet Pydantic-API** `req.dict()` | G5 | **Bekræftet**, kun i udviklingsbroen | `app/routers/veritas.py:27, 32, 38` | Lav | F1.6 |
| S-23 | **Gate-politik: samtidig aktivering og rollback, "tvetydig politik → afvis"** bør dækkes bedre | G2 | **Uafklaret**: gaten afviser en ændret politik siden forslaget (`E_POLICY`, GATE-KERNEL §8), men samtidig aktivering er ikke testet særskilt | `tests/test_gate_kernel.py` | Lav | F1.7 |

## 2. Dokumentation

| # | Fund | Kilde | Vurdering | Plan |
|---|---|---|---|---|
| D-1 | Samtykkeagentens status forskellig i README og `specs/README` | G3, G4 | **Rettet** i #185 | — |
| D-2 | CHANGELOG mangler alt efter 0.7.0; `RELEASE_NOTES_v0.4.0.md` og `docs/audit/F_GAPS.md` er forældede | G2, G5 | **Rettet** i #185 (CHANGELOG; arkiveret) | — |
| D-3 | **Ingen samlet sikkerhedsmodel.** `docs/security/socket-permissions.md` beskriver en svagere adfærd end koden (fejler lukket for `/run/eira`); IPC-token, root og trusselsmodel står intet sted samlet | G2, G4, G5 | **Bekræftet** (`app/ipc/socket_security.py:200-207`) | Plan §4.1 |
| D-4 | **Ingen `SECURITY.md`** (sårbarhedsrapportering) | G5 | **Bekræftet** | Plan §4.2 |
| D-5 | **Ingen samlet JSON-RPC-katalog** over sockets, metoder, adgangsklasse og fejlkoder | G1, G2, G5 | **Bekræftet**. Skal genereres fra koden, ellers bliver det forældet; hænger sammen med S-3 | F0b.2 |
| D-6 | **Ingen implementeringsmatrix** (krav → kode → test → VM-test → status) | G2, G3, G4 | **Bekræftet** | Plan §4.3 |
| D-7 | **Ingen miljøvariabel-reference** (`EIRA_IPC_TOKEN`, `EIRA_STRICT_SOCKET_GROUP`, `EIRA_BUILDER_MODE_ALLOWED`, …) | G5 | **Bekræftet** | Plan §4.4 |
| D-8 | **`app/gate/consent_proof.py`-docstringen** beskriver den gamle model (nøglen i appen og i sessionsrækken) | G4 | **Bekræftet**; koden følger den nye model | F1.7 |
| D-9 | **`android/` er udokumenteret** og uden CI | G1, G5 | **Bekræftet** | F1.8 |
| D-10 | **`ui/veritas-hud/index.html`** er udokumenteret | G5 | **Bekræftet**: en løs fil, som intet bruger (Veritas-HUD'en er `ui/src/components/VeritasHUD.tsx`) | F1.6 |
| D-11 | **Ingen `CONTRIBUTING.md`**, ingen PR- og issue-skabeloner; ingen guide til "ny beskyttet handling fra ende til anden" | G2, G5 | **Bekræftet** | Plan §4.5 |
| D-12 | **Migrationsstrategi udokumenteret** | G5 | **Bekræftet** (S-21) | F1.10 |
| D-13 | Testplanens CI-job `context-home` findes ikke | G4 | **Forventet**: kommer med F2.2 | F2.2 |
| D-14 | 139 brudte links | G3 | **Delvist**: i arkivet, som er markeret som ikke-normativt; ingen i de aktive dokumenter efter #185 | — |
| D-15 | Kontrakter står som udkast (GATE-KERNEL, AI-INTERFACE, EDP, EIRA-IDENTITY) | G4 | **Ejerens beslutning** | Planens §6 |
| D-16 | Manglende IPC-skemaer (`ipc-intent-v1.json` m.fl.) | G2 | **Afvist som beskrevet**: listen stod i det nu arkiverede `contracts/`. Behovet dækkes af D-5 | F0b.2 |
| D-17 | FFI-livscyklus, produktionsopsætning, teststrategi og UI-tilstandsflow | G1 | **Delvist**: produktionsopsætning er `.deb` + ISO (`docs/INSTALL.md`); FFI og UI-flow mangler | F1.8, plan §4.3 |

## 3. Konsekvenser for planen

1. **Nyt trin F0b — IPC-adgangskontrol** kommer før alt andet, fordi S-1 er et reelt integritetshul på den installerede pakke.
2. F1.2 udvides med S-7, S-8, S-9 (gate-processen må kun indeholde gaten), F1.6 med S-22 og D-10, og der kommer nye punkter F1.7–F1.10.
3. Dokumentationen (D-3 til D-11) får sin egen liste i planen (§4). D-5 og D-6 genereres fra koden, så de ikke forældes.
