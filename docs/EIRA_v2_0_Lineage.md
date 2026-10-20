# EIRA v2.0 — Lineage (Sprint 5–6 tilføjelser)

Denne fil tildeles udelukkende tilføjelser: hver 2025-påstand fra manifestet køres mod
2026-implementering. Linjer over de allerede afleverede sprints findes i
[CHANGELOG.md](../CHANGELOG.md), sprintsummater i [docs/](.), og de kanoniske 2025-dokumenter i
[manifest/](manifest/README.md).

## Sprint 5 (v0.5.0) — tilstandssynkronisering

| Manifest-påstand (2025) | 2026-spec | 2026-implementering | Status |
|---|---|---|---|
| En brugers tilstand følger brugeren — ikke enheden | E2EE sync mellem brugerens enheder | `app/fleet/merkle_sync.py` (#67), `app/fleet/e2ee.py` (formel leverance: PR #68, åben — blokerer #69 og Android-kæden) | ✅ #67 merged / ⏳ #68 åben |
| Flåde af Ubuntu-PC'er, bærbare og Android-kloner | Real-time WebSockets sync i fleetd | `app/daemons/fleetd.py` | ✅ på main (WebSocket-handshake, request/push blocks) |
| Enhedsparinger styres af brugeren — ikke af platformen | Pairing-registry i egen daemon, ingen tredjepart | `app/fleet/device_registry.py` (#70) | ✅ merged |
| Sikkerhed før bekvemmelighed | Fail-closed ved ukendt enhed eller korrupt payload | `DeviceAuthorizationError`, `PayloadIntegrityError` | ✅ #70 merged / ⏳ E2EE via #68 |

### Kontrakter tilføjet i Sprint 5

- **Hashkonvention:** SHA3-256, 64 hex-lowercase (`^[0-9a-f]{64}$`), domæneseparerede præfikser
  (`eira-merkle-dag-v1\x00` for DAG-roden, `eira-merkle-node-v1\x00` for noder), kanonisk JSON
  (`sort_keys`, kompakte separatorer, `allow_nan=False`), og defineret tom-rod-konstant.
- **E2EE-konvention:** `ChaCha20-Poly1305+HKDF-SHA256`, payload-version 1, HKDF-info
  `eiraos-fleet-sync-v1\x00 + key_context`, master-nøgle ≥ 256 bit, fleet-salt ≥ 128 bit.
  Integritetsfejl = afvisning; der findes ingen ukrypteret fallback. **Status:** forberedende
  kode på main; den formelle leverance er PR #68 (åben) — den eneste tilbageværende blokering
  på Sprint 5's kritiske vej.
- **Device-lifecycle:** paringstokens med TTL (standard 300 s) → enrollment (X25519-nøgle,
  navn, OS-type) → heartbeat (TTL 300 s) → udløb/revokering. Uparret eller revokeret enhed
  afvises altid — fail-closed.
- **Tidsstempel-konvention:** SQLite-tidsstempler opbevares i SQL-parset format (uden `T`- og
  UTC-offset-suffiks), så udløbssammenligninger aldrig returnerer `NULL` og dermed fail-open.

## Sprint 6 (v0.6.0, WIP) — Android bindings + FFI/WASM

| Manifest-påstand (2025) | 2026-spec | 2026-implementering | Status |
|---|---|---|---|
| Tredjeparts-API'er er valgfrie, men Eiras eget API er altid til stede | Lokal eira-core-FFI, ingen sky-afhængighed for tilstandseksport | `crates/eira-core/src/ffi.rs` (PR #68) | ⏳ åben |
| Genuin multitasking på mobil | Android-klient over Kotlin binding | `android/eira-core-binding/`, `android/app/` (PR #69) | ⏳ åben |

### Kontrakter tilføjet i Sprint 6 (WIP)

- **FFI-konvention:** null-pointer afvises straks; `catch_unwind` (via `AssertUnwindSafe`)
  sikrer, at panik i eira-core returneres som fejlstatus og aldrig aborter processen. Fejl
  returneres altid som fejl — aldrig som tom resultat.
- **Bemærkning:** v0.6.0 er WIP indtil #68 og #69 merges. Linjer i tabellen ovenfor udfyldes
  først med status ✅ ved merge.
