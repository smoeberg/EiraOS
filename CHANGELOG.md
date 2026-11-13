# Changelog

Alle væsentlige ændringer i EiraOS dokumenteres her. Datoer angiver leveringsperioden, ikke nødvendigvis en publiceret release.

## [Unreleased]

### Model og AI-grænseflade
- AI-INTERFACE 1.0 er afstemt mod runtime efter #190: `eira-modeld` ejer adapterkaldet, samtalekontekst kommer fra appen/EIRA-CONVERSATION (ikke `contextd`), forespørgsler uden samtale begrænses til systemhandlinger, og EDP/EiraSystemAPI beskrives som adskilte handlingsfamilier bag samme Gate Kernel. Den aktive adapter er fortsat regelbaseret; ingen sprogmodel eller modelruntime er tilføjet.

Leveret 6.–12. november 2026 (PR #128 og frem). Ingen release er tagget siden 0.7.0.

### CI
- Packaging Acceptance er kortere: ISO og VM-installation i samme job (CI-billedet uploades og hentes ikke længere),
  ISO'er uploades uden ny komprimering, VM-disken bruger `cache=unsafe`, Rust-bygget har sccache, og testsuiterne
  på Ubuntu 26.04's Python og Node kører i et parallelt job i stedet for inde i pakkebygget (`DEB_BUILD_OPTIONS=nocheck`).
  Basis-ISO'ens cache gemmes kun, når ISO'en skifter.

### Gate Kernel og sikkerhed
- F1b, første hele vej: IntentBar → `eira-modeld` → `gate.propose` → samtykkeagenten → gatens egen status. Modellen
  forstår strømkommandoer og foreslår dem som EiraSystemAPI-handlinger; mangler en delegation, beder UI'et om den gennem
  agenten; afstår modellen, siger UI'et det ærligt. Strøm-menuen (manuel vej) findes kun i Builder Mode (ADR-0001).
  Delegationsteksten er skrevet i almindeligt dansk. VM-check `intent-power-reaches-gate-and-is-refused`
  (fundregister S-6).
- R-6.2: `eira-labwc` har `<trustedGroup>`-patchen. Samtykkeagentens vindue ligger over alle andre, også fuldskærm, og har
  fokus; andre klienter kan ikke tage fokus, starte træk-og-slip, holde input-grabs eller sætte et markørbillede imens.
  Afprøvet headless i CI med kontrolkørsler (`verify-trusted.sh`); sessionen starter ikke uden patchen; pakken er
  `0.20.3-1eira2`.
- Adgangsklasse pr. IPC-metode: en metode uden klasse kan ikke registreres; `stated`s skrivemetoder
  kræver EiraOS' egen tjenestebruger, og `state.sync_push` afviser en blandet batch helt (fundregister
  S-1, S-2); JSON-RPC-katalog genereret fra koden (`docs/reference/ipc-katalog.md`) og VM-check
  `user-cannot-write-stated`.
- Præsentationstilstanden hører til OS-brugeren på socketen, ikke til en session: terminalens eget
  Builder-tjek ser nu den tilstand, brugeren har valgt (fundregister S-4). `dashboard.get`,
  `identity.session` og tilstandsmetoderne opretter aldrig sessioner og viser aldrig en identitet, klienten
  påstår (S-5); VM-check `user-mode-without-session`.
- Gate Kernel 1.0: otte lag, samtykke bundet til indholdshash, atomar udførelse og audit (#136); de
  gamle skriveveje svarer `E_GATE_REQUIRED` og er siden fjernet (#137, #180).
- Deterministisk renderer: samtykke binder til den tekst, brugeren så (#138).
- Gate 1.1 med to handlingsfamilier (ADR-0002): EiraSystemAPI-familien og strøm via logind bag gaten (#139).
- Procesidentitet fra `SO_PEERCRED`; modellen kan aldrig samtykke eller bekræfte (#150).
- Desktop-brugeren kan ikke skrive gatens database: `eira-clients` adskilt fra `eira` (#142).
- Samtykke-TTL på `CLOCK_BOOTTIME` (#143); samtykkenøglen kun i RAM og kun for den aktuelle boot (#178).
- Audit-anker i journald og hos Fleet (#155) og journalens FSS-segl med overdragelse af nøglen (#167).
- Samtykkeagenten `eira-consent-agent` (Rust, setgid): kun den kan samtykke og bekræfte (#153, #158, #175).
- Delegation "på vegne af" via den betroede vej, registreret i gatens audit (#157, #164).

### Rettigheder fra Fleet (ADR-0003)
- EIRA Rights Set 1.0 som eksekverbar kontrakt med skema, verifikator og testvektorer (#141).
- Lag 6 autoriserer mod det Fleet-signerede rettighedssæt; et signeret standardsæt ligger i pakken (#144, #145).
- EIRA Fleet Rights API: grænseflade, rod- og driftsnøgler med tilbagekaldelse, HTTPS + mTLS, enroll
  og planlagt synkronisering (#146–#149); enhedsnøglen i TPM i kontrakten (#177).
- `fleetd`: administratorkrav, `device_id` fra nøglen, gamle inventarmetoder fjernet (#176).

### Identitet, model og samtale
- Installeret desktop-login (RFC 8252) gennem `identityd` (#151, #152); leverandørneutral OIDC,
  `did:eira:<provider-id>.<subjekt>` uden indbygget udbyder (#169).
- Modelprocessen `eira-modeld` som egen bruger uden net, med en regelbaseret adapter (#166).
- Samtalelag og hændelsesstrøm til Explorer (#156).

### Desktop og system
- Rigtig Linux-terminal (PTY) i Builder Mode (#131); EiraSystemAPI v1 med strøm og batteri (#132).
- Hændelsesdrevet Explorer uden strømknap og terminal uden for Builder (ADR-0001, #133).
- Phase 0 IPC & Event Bus som kode og tests i `crates/eira-core` (#134).

### Pakning, installation og CI
- Installerbart EiraOS-ISO på Ubuntu Desktop 26.04 med installationstest i VM (#130).
- `eira-labwc`: labwc 0.20.3 uden privilegerede Wayland-protokoller (#163).
- Rent sessionsmiljø uden arvede `EIRA_*`- og loader-variabler (#159).
- VM-testen installerer offline fra et lokalt pakkearkiv (#160); eksplicit modulliste i `.deb` (#183);
  apt-fallback til spejle uden for ubuntu.com og robusthed mod DNS- og keyserver-fejl (#175, #184).

### Beslutninger og kontrakter
- ADR-0002 (to handlingsfamilier), ADR-0003 (rettigheder fra Fleet), ADR-0004 (vendor-neutral GUI),
  ADR-0005 (kontekster), ADR-0006 (livets indbakke) (#137, #140, #168, #170, #171).
- Kontrakter: EIRA-CONTEXT 1.0 v0.3 og testplan (#172, #173), EIRA-CONSENT-AGENT (#158), EIRA-IDENTITY (#169),
  forslag om et menneske- og fællesskabscentreret fundament (#165).
- Dokumentation: sprintdokumenter og den gamle `docs/specs/` arkiveret, ny README (#181, #182);
  udviklingsplan, statusrettelser og arkivering af `contracts/` og `docs/audit/` (dette PR).

### Rettelser
- `identityd`s AppArmor-profil manglede de `/proc`- og logind-filer, som login og samtykkeagentens
  registrering læser; på en rigtig maskine ville AppArmor have afvist begge (fundet af VM-checket
  `identityd-no-apparmor-denials` på #186).
- Fleet auth-bypass, OIDC JWKS-URL, en flaky Rust-test og UI-tegnkodning (#129).

### Oprydning
- Fjernede `ui/node_modules`, `__pycache__`-filer, `data/run/*.port` og løse filer (`jid`, `rid`)
  fra git og udvidede `.gitignore` (node_modules, Rust `target/`, `data/run/`, SQLite WAL-filer).
- Fjernede de forældede `packaging/systemd/`-units; de hærdede units i `systemd/` er de eneste,
  som `.deb`-pakken og `scripts/deploy_systemd.sh` installerer.
- README: rettede stier og links, opstartsvejledning fra repoets rod, korrekte socket-navne og en
  statustabel over alle ni daemons i stedet for de modstridende tal (6/7).

## [0.7.0] — released 2026-10-20

Alle sprint 5-7-PR'er er merged og CI er grøn; dette er det første tag.

### Sprint 7 — Spatial Canvas UI, Situation UI og Tauri v2 Desktop App Shell
- Tauri v2 Unix-socket IPC-bridge i `ui/src-tauri/src/ipc.rs`: protokolkerne på tværs af
  daemonernes Unix Domain Sockets, fail-closed fejlhåndtering og timeout-semantik, så React-
  grænsefladen taler direkte med `stated`/`graphd`/`veritasd` over Tauri IPC (Task 7.1).
- Spatial Canvas UI i `ui/src/components/SpatialCanvas.tsx`: kanvas-baseret navigation i
  tilstandsrummet med zoom/niveau-inddeling bundet til tilstandshash-kæden.
- Situation UI i `ui/src/components/SituationUI.tsx` og Veritas HUD i
  `ui/src/components/VeritasHUD.tsx`: kontekstafhængig situationsoversigt og synlig
  evalueringsstatus fra Veritas Shield.
- End-to-end UI-test i `ui/tests/e2e_canvas.test.ts` (vitest + testing-library): rendering af
  tilstandsgraf, forslagsflow og IPC-interaktion mod mockede daemon-svar.
- Dokumentation: [EIRA_Sprint7_Summary.md](docs/archive/sprints/EIRA_Sprint7_Summary.md).

### Sprint 6 — Android bindings + FFI/WASM state export
- FFI-grænseflade i `crates/eira-core/src/ffi.rs` med fail-closed pointerhåndtering og
  `catch_unwind`-containment, så panik aldrig krydser FFI-grænsen.
- Kotlin binding (`android/eira-core-binding/`) og Gradle-scaffolding for Android-klienten.
- Integrationstest for FFI state-eksport i `tests/test_android_ffi_state.py`.
- Status: issue #68 (E2EE) og #69 (device pairing) er lukket, og koden ligger på main. Dokumentation:
  [EIRA_Sprint6_Summary.md](docs/archive/sprints/EIRA_Sprint6_Summary.md).

## [0.5.0] — foreslået release, ikke tagget endnu

### Sprint 5 — Multi-Device E2EE State Sync
- Merkle DAG synkroniseringsmotor med diff og fork resolution: SHA3-256 med domæneseparation,
  kanonisk JSON og konflikt uden automatisk overskrivning af historik.
- E2EE payload-kryptering (issue #68, lukket; ChaCha20-Poly1305 + HKDF-SHA256, HKDF info
  `eiraos-fleet-sync-v1`), plaintext-metadata (`id`, `version`, `hash`) for Merkle-sammenligning,
  og fail-closed ved fejlet integritetsvalidering (`PayloadIntegrityError`).
- WebSockets real-time synkronisering i `fleetd`: handshake + rodudveksling,
  `sync.request_blocks`, `sync.push_blocks` og kædevalidering i lokal `StateStore`.
- Device pairing-registry med engangskode/QR-enrollment, X25519-nøglevalidering, heartbeat
  (TTL 300 s), revokering og automatisk udløb; SQLite-tidsstempler opbevares i parset format,
  så udløbssammenligninger aldrig fail-open.
- Integrationssuite `tests/test_fleet_e2ee_sync.py`: to-enheds E2EE-synkronisering med
  identisk SHA3-256-kæde, afvisning af uparrede enheder og rekonciliering efter offline ændringer.
- Dokumentation: [EIRA_Sprint5_Summary.md](docs/archive/sprints/EIRA_Sprint5_Summary.md).

## [0.4.0] — foreslået release, ikke tagget endnu

### Sprint 4 — Intent og CEL
- Indførte en begrænset CEL-kompatibel policy-evaluator med eksplicit understøttede AST-noder, kompleksitetsgrænser og fail-closed resultat ved evalueringsfejl.
- Tilføjede versionsstyret SQLite-lagring af policy-regler med historik, aktivering/deaktivering og standardpolitikker for betalinger, bevillinger, byggetilladelser, sagsfrister og habilitet.
- Koblede `intentd` til policy-store og transformation engine, så forslag evalueres mod gældende constraints før state anvendes.
- Udvidede intent-parseren med regelbaserede forslag, valgfri lokal Mistral/Ollama-parser, validering af strukturerede resultater og indlejring af kontekst i forslag.

### Sprint 3 — Veritas Shield
- Tilføjede Veritas-daemonens IPC-integrationstest og dækning af evaluering, health, socket-rettigheder og shutdown-livscyklus.
- Dokumenterede fail-closed-adfærd ved fejl i individuelle Veritas-lag samt at dæmonen forbliver tilgængelig efter en fejlet evaluering.

### Sprint 2 — Daemons og IPC
- Udvidede JSON-RPC-daemonregistrering og health-endpoints på tværs af kernekomponenter.
- Strammede JSON-RPC-kontraktvalidering, fejlens `user_message`-felt og peer-credential-/Unix-socket-adgangskontrol.
- Tilføjede systemd-units og deployment-script til at starte daemonerne under dedikeret `eira`-bruger/-gruppe.

### Release-forbehold
- Denne changelog opsummerer kode og tests, der er til stede i repositoryets Sprint 2–4-linje; den er ikke i sig selv dokumentation for en publiceret binær release.
- Foreslået Git-tag: `v0.4.0`. Opret først tag efter review, grøn CI og ejerens releasebeslutning.

## Tidligere versioner

Tidligere historik er endnu ikke samlet i denne fil.
