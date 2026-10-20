# Sprint 5 Summary — Multi-Device E2EE State Sync (v0.5.0)

Sprint 5 (uge 9–10) etablerede grundlaget for E2EE tilstandssynkronisering mellem en brugers
flåde af enheder (Ubuntu PC'er, bærbare og Android-kloner). Sprintet omfattede fem opgaver
(Task 5.1–5.5). Merged til `main`: `feat/s5-merkle-sync` (#67) og `feat/s5-device-registry`
(#70). **Task 5.2 (E2EE) er den formelle leverance stadig åben som PR #68** — krypteringsmodulet
nedenfor kom med forberedende sprint-5/6-commits, men #68 er den autoritative leverance og
blokerer i øjeblikket #69 (fleetd-sync) og hele Android-synkroniseringskæden.
Merge-rækkefølge: #67 ✅ → #70 ✅ → #68 → #69 → 6.1 → 6.5 → 6.2/6.5b → 6.3 → 6.4 → 7.1 →
audit → docs.

## Leverancer

### Task 5.1 — Merkle DAG hash-træ synkroniseringsmotor (#67, merged)
`app/fleet/merkle_sync.py`:

- `MerkleSyncEngine` konstruerer Merkle-snapshots ud fra `State.hash` og `previous_state_id`,
  beregner diff mellem to enheders snapshots, og opløser forgreninger via `ForkResolution`
  (konflikt markeres — motoren overskriver aldrig historien selv).
- Datatyperne `StateHeader` (id, version, hash, previous_state_id, timestamp_ns),
  `MerkleSnapshot`, `SyncDiff` (med `in_sync`) og `ForkResolution` (med `has_conflict`).
- Hashkonvention: SHA3-256 med domæneseparations-præfiks (`eira-merkle-dag-v1\x00` for roden,
  `eira-merkle-node-v1\x00` for noder), kanonisk JSON (`sort_keys`, kompakte separatorer) og
  tom-rod-konstant for tom historik. Alle hashes valideres mod `^[0-9a-f]{64}$`.
- Coverage: `tests/test_merkle_sync.py` (163 linjer, tilføjet i #67).

### Task 5.2 — E2EE payload-sikkerhedsmodul — **ÅBEN: PR #68** (forberedende kode på main)
`app/fleet/e2ee.py`:

- `StatePayloadEncryptor` med ChaCha20-Poly1305 + HKDF-SHA256, algoritmetag
  `ChaCha20-Poly1305+HKDF-SHA256`, payload-version 1.
- Nøgleafledning ud fra master-parsynkroniseringsnøgle (min. 256 bit) og fleet-salt (min. 128 bit),
  med `info = "eiraos-fleet-sync-v1\x00" + key_context`.
- Krypteret payload kan ikke dekrypteres med forkert nøgle: fejl markeres som
  `PayloadIntegrityError` (fail-closed — ingen fallback til ukrypteret).
- Plaintext-metadata (`id`, `version`, `hash`) følger forsynet for Merkle-sammenligning uden
  at lække payload-indholdet.

### Task 5.3 — WebSockets real-time sync i fleetd (til stede i main fra sprint-5/6-forberedende commits)
`app/daemons/fleetd.py`:

- Synkroniseringssekvens: handshake + udveksling af Merkle-roden → `sync.request_blocks` for
  manglende hashes → `sync.push_blocks` med E2EE-blokke → kædevalidering i lokal `StateStore`.
- `generate_device_keypair` eksponeret fra fleetd til registrationsflowet.

### Task 5.4 — Device pairing & public key registry (#70, merged)
`app/fleet/device_registry.py`:

- `DeviceRegistry` med SQLite-lagring (delt `:memory:`-forbindelse trådsikkert; filbaserede
  registre opretter selv omliggende mappe).
- Enrollment via engangskode/QR: `create_pairing_token` (TTL, standard 300 s) og `enroll`
  med X25519-valideret offentlig nøgle, enhedsnavn og OS-type (Ubuntu, Android).
- Lifecykel: `assert_authorized` (ukendt/revokeret enhed → `DeviceAuthorizationError`,
  fail-closed), `heartbeat` (TTL 300 s), `revoke`, `list_active` og automatisk udløb af
  forældede enheder (`_expire_stale_devices`).
- Konvention: tidsstempler opbevares i SQLite-parset format (ingen `T`/offset-suffiks i
  ISO-8601), så udløbssammenligninger i SQL aldrig bliver `NULL` og dermed fail-open.
- Coverage: `tests/test_device_registry.py` (tilføjet i #70).

### Task 5.5 — E2EE integrationssuite
`tests/test_fleet_e2ee_sync.py`:

- `test_e2ee_state_sync_between_two_devices()`: 5 tilstande på Enhed A → synkronisering over
  fleetd → identisk SHA3-256-kæde verificeret på Enhed B.
- `test_unauthorized_device_rejected()`: uparret enhed afvises under handshake.
- `test_reconciliation_after_offline_edits()`: to enheder med offline-ændringer fletter deres
  Merkle DAGs ved genopkobling.

## Fail-closed-regler konstateret i Sprint 5

| Situation | Adfærd |
|-----------|--------|
| Ukendt/revokeret enhed under `assert_authorized` | `DeviceAuthorizationError` — adgang nægtet |
| Integritetstjek fejler ved dekryptering | `PayloadIntegrityError` — payload afvises |
| Manglende `id`/`hash` i state-header | `ValueError` — snapshot afvises |
| Efterladt/udløbet enhed (heartbeat TTL) | Ekskluderet fra `list_active`, automatisk udløb |
| Udløbssammenligning med uparset tidsstempel | Undgået: tidsstempler i SQLite-parset format |

## Hvad mangler (Sprint 7–10)

- **PR #68 (åben, kritisk vej):** Formel E2EE-leverance (`StatePayloadEncryptor`). Blokerer
  #69 og hele Android-sync-kæden — den eneste tilbageværende blokering på Sprint 5's kritiske vej.
- **PR #69 (åben):** fleetd-sync over den rigtige `MerkleSyncEngine`
  (API: `compute_block_hash`, `verify_block`, `missing_blocks`); `StatePayloadEncryptor`
  stubs/injektion indtil #68 merger.
- **PR #76 (åben):** Fleet E2EE sync — envelope encryption for fleetd.
- **Sprint 7:** Spatial Canvas UI, Situation UI og Tauri v2 desktop shell over IPC.
- **Sprint 8:** Produktivisering af flåden (stabilitet, opsamling af Sprint 5/6).
- **Sprint 9:** OS-pakning/distribution.
- **Sprint 10:** Produktionshærdning.

## Release-forbehold

- `v0.5.0` er foreslået, ikke tagget. Tag oprettes først efter review, grøn CI og ejerens
  releasebeslutning (jf. CHANGELOG.md).
