# Sprint 8 — Rust Cutover Checklist

**Purpose:** Gate full production cutover of state hashing / `stated` evaluation from the Python path to the Rust path (`eira-core` / `eira-stated`).

**Related:** [EIRA_Sprint8_Audit_Stated.md](./EIRA_Sprint8_Audit_Stated.md), [EIRA_Sprint8_Execution_Prompts.md](./EIRA_Sprint8_Execution_Prompts.md)

**Date:** 2026-10-20

---

## Hard gate — bit-identical SHA3-256

**Regression contract**

> The same logical state object, passed through the Python path and the Rust path, MUST produce **bit-identical** SHA3-256 digests (lowercase hex, 64 chars).

| Check | Evidence | Status |
|---|---|---|
| Six-field domain (`id`, `version`, `timestamp_ns`, `type`, `payload`, `previous_state_id`) | Python `app/core/state.py` ↔ Rust `eira_core::compute_hash_from_value` | **PASS** |
| Compact JSON, sorted keys, `ensure_ascii=False` / Unicode preserved | Audit S8 + core tests | **PASS** |
| Hash field itself is **not** part of the hashed body | Both implementations | **PASS** |
| Python `State.compute_hash()` == Rust FFI `eira_state_compute_hash` for ordinary vectors | `tests/test_android_ffi_state.py` (`test_python_and_ffi_hash_consistency`, unicode/large timestamp cases) | **PASS** |
| Python store append + Rust store append yield identical persisted records/hashes | `tests/test_rust_cutover_performance.py` (`test_python_and_rust_state_compatibility`, `test_bit_identical_sha3_hashes_python_vs_rust`) | **PASS** (when `eira-stated` / `eira-core` cdylib built) |
| Tampered payload fails closed on Rust path | `test_tampered_state_is_rejected_by_rust_before_insert`, FFI chain tests | **PASS** |

### Explicit regression command

```bash
cargo build --release -p eira-core -p eira-stated
python -m pytest tests/test_android_ffi_state.py tests/test_rust_cutover_performance.py -q
```

All hash assertions must compare **full 64-character hex strings** (`==`), not truncated prefixes.

---

## Supporting gates

| Gate | Criterion | Status |
|---|---|---|
| Performance | Rust append p95 < 1.0 ms (env `EIRA_RUST_APPEND_P95_MS`) | **PASS** when benchmark environment is stable (`test_rust_append_p95_is_under_one_millisecond`) |
| Fail-closed FFI | Null / invalid JSON → null pointer or status `-1`, never silent accept | **PASS** |
| SQLite immutability | Append validates hash before write; UPDATE/DELETE blocked by triggers | **PASS** (audit) |
| Workspace CI | `cargo test --workspace` green on CI stable toolchain | Operational |

---

## Compatibility findings (from Sprint 8 audit)

These do **not** block ordinary-state cutover, but must stay explicit:

| ID | Topic | Cutover impact |
|---|---|---|
| **S8-AUD-01** | Floating-point / exotic numeric canonicalization may differ (`json.dumps` vs `serde_json`) | **Mitigation:** state payloads in production use integers / strings for money and counters; reject `NaN`/`Infinity` (`allow_nan=False`). Shared float vectors remain optional follow-up. |
| **S8-AUD-02** | Python `is_hash_valid()` still accepts **legacy** hash format; Rust rejects it | **Mitigation:** cutover path uses only the current six-field compact contract; no new legacy hashes. Migration of historical rows is a separate data job if any legacy rows exist. |
| **S8-AUD-03** | `append()` is incremental; full-chain validation is a separate API | **Documented.** Cutover does not change this boundary. |

---

## Cutover clearance

### In scope for full cutover (cleared)

1. **Canonical SHA3-256 for normal Eira states** (UUID ids, int version/timestamp, string types, JSON object payloads without exotic floats, optional `previous_state_id`).
2. **Rust `eira-stated` as persistence engine** behind the existing Python control plane / FFI (`RustStateStore` / C ABI).
3. **Bit-identical digests** as continuous regression in CI (FFI + store paths).

### Out of scope / deferred

1. Automatic rewrite of any historical **legacy-hash** rows (S8-AUD-02).
2. Guaranteed cross-language parity for every IEEE-754 edge float representation (S8-AUD-01) without a frozen shared numeric corpus.
3. Treating a successful `append()` as proof of whole-chain cryptographic validity (S8-AUD-03).

### Decision

| Role | Decision |
|---|---|
| **Ordinary state cutover (Python control plane → Rust hash + store)** | **CLEARED** under the hard gate above |
| **Unconditional “all JSON numbers forever” equivalence** | **NOT CLEARED** until S8-AUD-01 shared vectors land |
| **Legacy-hash coexistence as a permanent feature** | **REJECTED** — fail-closed on Rust; Python legacy accept is migration-only |

**Signed clearance (process):** Sprint 8 cutover may proceed for the normal state contract once the regression command is green in CI. Re-open this checklist if the six-field domain or canonicalization rules change.

---

## Owner actions after merge

1. Keep `tests/test_android_ffi_state.py` and `tests/test_rust_cutover_performance.py` in the default CI path whenever the Rust toolchain job runs.
2. Do not add a Rust-only domain prefix (e.g. `EIRA_STATE_V1:`) without a coordinated Python change.
3. Track S8-AUD-01/02 as explicit follow-ups if float-heavy or legacy datasets appear in production.
