# EiraOS implementation tracker

**Baseline:** `main` at `fdd0b29ecd076abb46e0dd5eda23509a9c94eacc` (2026-10-20).  
Estimates below are planning estimates, not measured durations. Status is based on repository artifacts and known CI state; hardware/Ubuntu claims require recorded runtime evidence.

| Sprint / area | Evidence on main | Status | Remaining work | Estimate |
|---|---|---|---|---|
| 1 — core state / storage | `app/core/state.py`, state-related tests | Implemented baseline; needs integration confirmation | Verify migration/recovery and persistence on target image | 0.5–1 day |
| 2 — daemons / IPC | `app/daemons/`, `app/ipc/`, service files | Implemented baseline; live boot not established here | Live socket/permission/error-path acceptance | 1–2 days |
| 3 — Veritas Shield | `app/veritas/`, `app/daemons/veritasd.py`, `tests/test_veritas_shield.py` | Unit/integration coverage exists; hardware attestation and EUTL refresh remain bounded gaps | Define hardware attestation format/trust roots; signed EUTL snapshot refresh and freshness policy | 2–5 days after trust-source decisions |
| 4 — intent / CEL | `app/core/cel_evaluator.py`, `tests/test_intent_cel_constraints.py`, parser hardening tests | Security regression coverage present | Cross-audit findings, performance tests and policy-owner review | 1–2 days |
| 5 — fleet sync | `app/fleet/merkle_sync.py`, `device_registry.py`, `e2ee.py` | Merkle/registry implemented; empty-payload behavior being corrected in PR | Merge only after CI/review; run two-device integration suite | 1–2 days |
| 6 — Android / FFI | `crates/eira-core/src/ffi.rs`, `android/`, `tests/test_android_ffi_state.py` | Source and tests present | Validate native build/ABI and actual Android device integration | 2–4 days |
| 7 — desktop UI shell | `ui/src-tauri/`, `ui/src/components/` | UI sources and IPC bridge present | Clean Ubuntu build, real data flow and accessibility/usability review | 2–4 days |
| 8 — fleet stabilization | Sprint 8 PRs merged; main CI green at baseline | Complete per current sprint report | Regression/integration run after new security PRs | 0.5–1 day |
| 9 — OS packaging | `docs/EIRA_Sprint9_Execution_Prompts.md` | Planned, not proven complete by this audit | AppArmor enforcement, Debian/Ubuntu packages, bootable ISO, login/session tests | 3–6 days |
| 10 — production hardening | No authoritative Sprint 10 plan identified at baseline | Needs an agreed plan | Define release gates, threat model, backup/restore, observability, upgrade/rollback and signing | 1 day planning + 3–7 days implementation |

## Release gates

- [ ] CI green on the exact PR merge candidate.
- [ ] Clean Ubuntu 24.04 build and login/session evidence attached.
- [ ] Daemon/socket startup and least-privilege permissions verified.
- [ ] E2EE fail-closed behavior and two-device sync tested.
- [ ] Veritas limitations are explicit; no unverified hardware marker is treated as a signature.
- [ ] EUTL data provenance, signature validation, freshness and rollback behavior defined.
- [ ] Release notes and cross-audit reviewed by the repository owner.
- [ ] Tag and publication only after explicit owner approval.
