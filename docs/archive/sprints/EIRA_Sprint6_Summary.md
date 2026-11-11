# Sprint 6 Summary — Android bindings + FFI/WASM state export (v0.6.0, WIP)

Sprint 6 (uge 11–12) fokuserer på **Android Client Bindings** og **FFI/WASM State Exports**.
Arbejdet er i gang: PR #68 (`feat/s6-ffi-export`) og #69 (`feat/s6-kotlin-binding`) er **åbne**,
og version `v0.6.0` er derfor markeret **WIP indtil begge merges** (jf. CHANGELOG.md).

## Status pr. fil

| Komponent | Fil | Status |
|-----------|-----|--------|
| FFI-eksport af tilstande | `crates/eira-core/src/ffi.rs` | WIP (PR #68) |
| Kotlin binding (Android) | `android/eira-core-binding/` | WIP (PR #69) |
| Android-scaffolding | `android/` (Gradle-filer, `android/app/`) | WIP (PR #69) |
| FFI state integrationstest | `tests/test_android_ffi_state.py` | WIP (PR #68) |

## Kontrakter på FFI-grænsen (fail-closed)

`ffi.rs` følger fail-closed-kontrakten også på FFI-grænsen:

- Null-input pointer afvises straks ("input pointer is null") — ingen fallback til tom streng.
- Input kopieres ud via `CStr`/`CString` med eksplicit levetidshåndtering (`unsafe`-blokke
  begrænset til pointer-læsning/skrivning).
- `catch_unwind` (via `AssertUnwindSafe`) sikrer, at panik i eira-core aldrig krydser FFI-grænsen
  som abort — fejl returneres som fejlstatus, ikke crash.

## Udestående før v0.6.0 kan markeres som release

1. Merge af #68 (FFI-eksport) og #69 (Kotlin binding).
2. Grøn CI på Python 3.11 + 3.12 og Rust-build.
3. Ruff ren (`ruff check .`) — se fællesregler.
4. Aftalt releasebeslutning fra ejeren; tag `v0.6.0` først derefter.

## Sprint 6 er IKKE: andre filer

Sprint 6-operatører må kun røre de filer, som deres opgave lister. Ændringer til fx
`app/daemons/` eller `ui/` hører under PR #71 (åben: intentd constraint-enforcement) og
må ikke blandes ind i Sprint 6-dokumentations-PR'en.
