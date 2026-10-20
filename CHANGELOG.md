# Changelog

Alle væsentlige ændringer i EiraOS dokumenteres her. Datoer angiver leveringsperioden, ikke nødvendigvis en publiceret release.

## [0.6.0] — WIP, ikke tagget endnu

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
- Dokumentation: [EIRA_Sprint7_Summary.md](docs/EIRA_Sprint7_Summary.md).

### Sprint 6 — Android bindings + FFI/WASM state export
- FFI-grænseflade i `crates/eira-core/src/ffi.rs` med fail-closed pointerhåndtering og
  `catch_unwind`-containment, så panik aldrig krydser FFI-grænsen.
- Kotlin binding (`android/eira-core-binding/`) og Gradle-scaffolding for Android-klienten.
- Integrationstest for FFI state-eksport i `tests/test_android_ffi_state.py`.
- Status: PR #68 og #69 er åbne; `v0.6.0` er derfor WIP indtil merge. Dokumentation:
  [EIRA_Sprint6_Summary.md](docs/EIRA_Sprint6_Summary.md).

## [0.5.0] — foreslået release, ikke tagget endnu

### Sprint 5 — Multi-Device E2EE State Sync
- Merkle DAG synkroniseringsmotor med diff og fork resolution: SHA3-256 med domæneseparation,
  kanonisk JSON og konflikt uden automatisk overskrivning af historik.
- E2EE payload-kryptering (**leverance åben: PR #68**; forberedende kode på main fra
  sprint-5/6-commits: ChaCha20-Poly1305 + HKDF-SHA256, HKDF info `eiraos-fleet-sync-v1`),
  plaintext-metadata (`id`, `version`, `hash`) for Merkle-sammenligning, og fail-closed ved
  fejlet integritetsvalidering (`PayloadIntegrityError`). #68 blokerer i øjeblikket #69 og
  Android-synkroniseringskæden.
- WebSockets real-time synkronisering i `fleetd`: handshake + rodudveksling,
  `sync.request_blocks`, `sync.push_blocks` og kædevalidering i lokal `StateStore`.
- Device pairing-registry med engangskode/QR-enrollment, X25519-nøglevalidering, heartbeat
  (TTL 300 s), revokering og automatisk udløb; SQLite-tidsstempler opbevares i parset format,
  så udløbssammenligninger aldrig fail-open.
- Integrationssuite `tests/test_fleet_e2ee_sync.py`: to-enheds E2EE-synkronisering med
  identisk SHA3-256-kæde, afvisning af uparrede enheder og rekonciliering efter offline ændringer.
- Dokumentation: [EIRA_Sprint5_Summary.md](docs/EIRA_Sprint5_Summary.md).

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
