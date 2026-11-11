# Sprint 0 — Audit af EiraOS `main` (GUI-readiness)

Branch: `audit/ubuntu-gui-readiness` · Leverance: `docs/EIRA_Implementation_Tracker.md` + `docs/EIRA_GUI_Audit_v1.0.md`
Regel: **ingen kodeændringer i `main`** — audit er en dokumentationsbranch.

## A. Komponentkort (hvad findes og starter det?)

For hver komponent: kan den startes? Hvad taler den med? Fuldfør eller rod?

```bash
# 1. Daemons
python3 app/daemons/<name>.py &   # identityd, walletd, veritasd, graphd, contextd, intentd, stated, runner
ls -la /run/eira/ 2>/dev/null     # hvilke sockets oprettes faktisk?
```

- [ ] Tabel: daemon → fil → entrypoint → socket → oprettet? → implementeret/stub/dead
- [ ] Tjek overlap: findes der to implementationer af samme ansvar? (fx intent-parsing i `app/intent_parser.py` vs. daemon)
- [ ] `app/ipc/`, `app/http_bridge.py`, `app/executor.py`, `app/graph_context.py` — hvem kalder hvad?

## B. IPC-kontrakter

- [ ] Liste alle metoder pr. socket (`dashboard.get`, `intent.parse`, `intent.plan`, `intent.confirm`, …)
- [ ] JSON-RPC 2.0 overholdt overalt, eller mixed legacy-format?
- [ ] Fejlformat: returneres `user_message` (UX regel 5) fra daemons?
- [ ] Socket-permissions: hvem kan tilgå hvad? (gruppe-uid, chmod)

## C. UI / Tauri

```bash
cd ui && npm install && cargo tauri dev
```

- [ ] Bygger `ui/` på ren Ubuntu 24.04 med `libwebkit2gtk-4.1-dev`? Notér fejl og manglende deps.
- [ ] Taler UI-koden i dag med HTTP-bridge eller sockets? Grep: `http_bridge`, `fetch(`, `/run/eira`
- [ ] Hvilke komponenter fra `ui/src` er reelle vs. mock (Dashboard, IntentBar, VeritasHUD, SpatialCanvas)?
- [ ] Er der en `src-tauri` med capabilities defineret?

## D. Session og boot

- [ ] `packaging/session/eira-session` — peger den på ikke-eksisterende `eira-spatial-desktop`?
- [ ] Findes systemd-units (`eira.target`, daemon-units)? Er de user- eller system-level?
- [ ] Er der AppArmor-profiler, og gælder de den faktiske kode?

## E. Fleet / Sikkerhed

- [ ] `app/fleet/` (device_registry, e2ee, merkle_sync): implementeret eller skelet?
- [ ] Krypterings- og enroll-antagelser dokumenteret i kode vs. specs

## F. Kritiske mangler for desktopbrug (leverancen)

Sorter i tre kategorier og prioriter:

1. **Blokerende** — forhindrer boot ind i shell (session-script, shell crash-loop, manglende deps)
2. **Ødelæggende for UX** — dataflow fungerer ikke end-to-end (IPC-kontrakt-mismatch, manglende fejl-UX)
3. **Kosmetisk** — polish, manglende skærme, styling

## G. Acceptkriterier for auditten

- [ ] `docs/EIRA_GUI_Audit_v1.0.md`: komponenttabel + IPC-kontraktliste + modenhedsgrad (real / stub / dead)
- [ ] `docs/EIRA_Implementation_Tracker.md`: sprint 1–6 med reviderede estimater fra fakta
- [ ] Alle 7 daemons kan startes og sockets oprettes (eller dokumenteret hvorfor ikke)
- [ ] `cargo tauri dev` kører på Ubuntu 24.04 (eller fejl-liste som first ticket for Sprint 1–2)
- [ ] PR åbnes med "beviser": kommando-output, skærmbilleder, `wayland-info`/`systemctl`-status
