# Sprint 7 Summary — Spatial Canvas UI, Situation UI og Tauri v2 Desktop App Shell (v0.6.0, WIP)

Sprint 7 (uge 13–14) forbinder React-grænsefladen til dæmonernes Unix Domain Sockets via en
Tauri v2 Desktop App Shell og bygger den spatial-brugergrænseflade, som de tidligere sprints'
daemons og state-lag blev bygget til at betjene. Leverancen kom ind via to PR'er:

- **PR #83** (`feat/s7-tauri-ipc`, merged): Task 7.1 — Tauri v2 Unix-socket IPC-bridge.
- **PR #22** ("Sprint 7 8 spatial rust cutover", merged; commit `7d69ffb`): Task 7.2–7.5 —
  Spatial Canvas UI, Situation UI, Veritas HUD og e2e-tests (samme commit bragte også
  Sprint 8's Rust-cutover-forberedelse, som er dokumenteret separat).

## Leverancer

### Task 7.1 — Tauri v2 Unix-socket IPC-bridge (#83, merged)
`ui/src-tauri/src/ipc.rs` (525 linjer):

- Protokolbro mellem Tauri-kommandoer i frontend og dæmonernes JSON-RPC over Unix Domain
  Sockets (`stated`, `graphd`, `veritasd` m.fl.).
- Fail-closed fejlhåndtering: uventede socket-fejl, timeouts og ugyldige svar returneres som
  strukturerede fejl til frontend — der findes ingen "bedste gæt"-fallback.
- Timeout-semantik og lifecycle-håndtering, så en hængende dæmon aldrig blokerer UI-tråden.
- Tilknyttede konfigurationer: `ui/src-tauri/tauri.conf.json`, `capabilities/default.json`,
  `ui/src-tauri/Cargo.toml` og `ui/src/lib/ipc.ts` (frontend-indgang til IPC-laget).

### Task 7.2 — Spatial Canvas UI (PR #22, merged)
`ui/src/components/SpatialCanvas.tsx` (300 linjer):

- Kanvas-baseret navigation i tilstandsrummet med zoom/niveaustyring over state-grafen.
- Tilstande renderes fra state-hash-kæden (id, version, `previous_state_id`), så canvasen
  viser samme historik som Merkle-sync-laget (Sprint 5).
- Frontend-datakilden er `ui/src/lib/ipc.ts` → `ui/src-tauri/src/ipc.rs`; der hentes intet
  direkte fra daemons udenom IPC-laget.

### Task 7.3 — Situation UI (PR #22, merged)
`ui/src/components/SituationUI.tsx` (53 linjer):

- Kontekstafhængig situationsoversigt, der komponerer aktive dokumenter, forslag og
  evalueringsstatus i ét panel.
- Er funktionsopdelt fra kanvasen, så kanvas og situation kan udvikles uafhængigt.

### Task 7.4 — Veritas HUD (PR #22, merged)
`ui/src/components/VeritasHUD.tsx` (109 linjer):

- Synlig evalueringsstatus fra Veritas Shield: forslag vises som godkendt/afvist/beholdt
  direkte fra Veritas' evaluering.
- Fail-closed i UI: ukendt eller manglende evalueringsresultat vises aldrig som "godkendt".

### Task 7.5 — End-to-end UI-tests (PR #22, merged)
`ui/tests/e2e_canvas.test.ts` (108 linjer, vitest + testing-library):

- Renderer `App` med mockede IPC-svar og verificerer rendering af tilstandsgraf
  (`DocumentState`/`ProposalState`), forslagsflow og IPC-interaktion.
- `ui/tests/setup.ts` indeholder test-opsætningen; frontend-testdækningen følger samme
  fail-closed-principper som Python/Rust-suiten.

## Tests og verifikation

- Python-suiten på main: `pytest tests/` → 256 passed, 15 skipped, 1 xfailed (baseline
  inkl. Sprint 5–6); `ruff check .` ren.
- Frontend: `ui/tests/e2e_canvas.test.ts` via vitest (npm) — kræver npm-installation.
- Rust: `ui/src-tauri/` bygger med Tauri v2; `crates/eira-ipc` og `crates/eira-stated`
  (fra Sprint 8-forberedelsen i samme commit) dækker delte kontrakter.

## Udestående før v0.6.0 kan markeres som release

1. Merge af resterende åbne Sprint 6–7-PR'er (#86 Spatial Canvas accessibility, #87 Android
   Background Sync Service).
2. Grøn CI (Python 3.11 + 3.12, Rust-build) på det commit, der tages som release-punkt.
3. Ruff ren og suite grøn som ovenfor.
4. Tag beslutning (se tag-forslag nedenfor og i PR-beskrivelsen) — `v0.6.0` først efter
   ejerens releasebeslutning.

## Tag-forslag til Søren

- **`v0.5.0`:** alle Sprint 5-leverancer (#67, #70, #68, #69, #76, #80) er merged til main —
  commit `0251f12` er et velegnet tag-punkt, hvis CI er grøn dér.
- **`v0.6.0`:** Sprint 6 og 7 er merged, men #86 og #87 er åbne. Anbefaling: tag `v0.6.0`
  **efter** merge af #86/#87 (og efter at `CHANGELOG.md` fjerner "ikke tagget endnu") —
  på det commit, der merge'r denne docs-PR, eller et senere udpeget release-commit.
- `v0.5.0` og `v0.6.0` kan godt tages samme dag, men ikke på samme commit: tag aldrig to
  versioner ét sted — tag `v0.5.0` på `0251f12` (eller tidligere) og `v0.6.0` senere.

## Sprint 7 er IKKE: andre filer

Sprint 7-operatører må kun røre de filer, som deres opgave lister. Dokumentations-PR'en
(Sprint 7 Agent 10 · Task 7.8-release) ændrer udelukkende `CHANGELOG.md`,
`docs/EIRA_Sprint7_Summary.md` og (navigationstilføjelser i) `docs/EIRA_Document_Map_v0.1.md`.
Rust-cutover (Sprint 8), OS-pakning (Sprint 9) og produktionssikring (Sprint 10) er
egne sprints og dokumenteres i deres egne summaries.

## Sprint 8–10 (hvad mangler)

- **Sprint 8:** Rust-cutover af state-runtime (`app/core_rust.py`, `crates/eira-ipc`,
  `crates/eira-stated`, performance-tests i `tests/test_rust_cutover_performance.py`) —
  forberedelseskommitteret i Sprint 7, udfoldes og auditeres i Sprint 8.
- **Sprint 9:** OS-pakning og systemd-livscyklus for samlet EiraOS-afbildning.
- **Sprint 10:** produktionssikring: skrivebeskyttet root, rotation af fleet-nøgler og
  fuldt fail-closed opstartsflow.
