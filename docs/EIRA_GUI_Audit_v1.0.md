# EiraOS GUI-readiness audit (static review)

**Review baseline:** `main` at `fdd0b29ecd076abb46e0dd5eda23509a9c94eacc` (2026-10-20).  
**Method:** repository/file inspection only. This is not a claim that Ubuntu 24.04 boot, a live desktop session, or all daemon sockets were exercised on a clean host.

## Executive summary

The repository contains a Tauri v2 shell, IPC bridge, spatial/situation UI components, daemon IPC code, fleet sync components, and systemd/deployment material. The existence of code and unit tests is not proof of a complete installed desktop experience. The release gate remains **not yet demonstrated** until a clean Ubuntu 24.04 run records package installation, build output, session startup, service status, and socket permissions.

## Component map

| Area | Evidence in repository | Static status | Runtime evidence still needed |
|---|---|---|---|
| Desktop shell | `ui/src-tauri/`, Tauri v2 Rust sources | Present | Clean `cargo tauri dev` and packaged launch on Ubuntu 24.04 |
| IPC bridge | `ui/src-tauri/src/ipc.rs` | Present; uses daemon IPC | Verify each method against live daemon RPC contracts |
| Spatial canvas | `ui/src/components/SpatialCanvas.tsx` | Present | Real data flow and usability check |
| Situation UI | `ui/src/components/SituationUI.tsx` | Present | Live state/error/loading paths |
| Veritas HUD | `ui/src/components/VeritasHUD.tsx` | Present | Verify trust score and flags from live `veritasd` |
| Veritas daemon | `app/daemons/veritasd.py`, `tests/test_veritas_shield.py` | Implementation + IPC test present | Run daemon under installed service account |
| State daemon | `app/daemons/stated.py` | Source present | Socket creation, persistence, restart recovery |
| Graph daemon | `app/daemons/graphd.py` | Source present | Provenance RPC availability and error behavior |
| Intent daemon | `app/daemons/intentd.py` | Source present | End-to-end proposal/confirmation path |
| Fleet sync | `app/daemons/fleetd.py`, `app/fleet/` | Source present; encryption contract under review | Two-device integration with current E2EE envelope |
| Session / boot | `packaging/session/`, service/deployment files | Static review required per target image | Actual login, compositor, restart and logout behavior |
| Confinement | AppArmor profile files, if packaged | No runtime enforcement established by this audit | Confirm profiles load and deny unauthorized paths/sockets |

## IPC contract checklist

- [ ] Inventory each daemon's registered JSON-RPC methods and socket name from its source.
- [ ] Confirm JSON-RPC 2.0 success/error shapes and user-safe `user_message` behavior.
- [ ] Verify Unix socket owner/group/mode after service startup.
- [ ] Confirm UI IPC methods match the live daemon method names and parameter schemas.
- [ ] Test unavailable daemon, timeout, malformed response and daemon restart scenarios.

## Ubuntu 24.04 GUI acceptance run

Run on a clean Ubuntu 24.04 machine or VM and attach outputs to the release PR:

1. Record `lsb_release -a`, architecture, kernel, and installed build dependencies.
2. Run the documented Python/Rust/UI test suites and `cd ui && npm ci && cargo tauri dev` (adjust only if repository instructions specify a different package manager).
3. Start the packaged session using the supported session entry point; record login, compositor, shell and logout behavior.
4. Capture `systemctl --failed`, relevant `systemctl status` output, `journalctl` excerpts, and `ls -la /run/eira/` (or configured runtime directory).
5. Verify AppArmor status and profile enforcement, not just profile-file existence.
6. Exercise an intent proposal, confirmation, state update, graph/provenance view and Veritas result through the actual UI.
7. Record every failure as a linked issue; do not label a step passed without output.

## Readiness decision

**Status: conditional / not proven on a clean Ubuntu host.** Static code and tests provide evidence of component implementation, but this audit does not assert that all daemons start, the desktop boots, or packaging works end-to-end. The above runtime acceptance run is a release gate.
