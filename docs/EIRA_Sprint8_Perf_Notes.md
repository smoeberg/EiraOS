# Sprint 8 — eira-stated performance notes

**Scope:** `crates/eira-stated` append and read-path performance, measured through `app/core_rust.py` against the Python `StateStore` implementation.

## Reproducible benchmark gates

Run from the repository root after building the native library:

```bash
cargo build --release -p eira-core -p eira-stated
python -m pytest tests/test_rust_cutover_performance.py -q
```

The suite currently enforces:

| Operation | Measurement | Acceptance gate |
|---|---|---:|
| Rust append | p95 over 475 samples after the first 25 warm-up operations | < 1.0 ms |
| Rust `get_by_hash` | p95 over 110 reads after the first 10 warm-up reads | < 1.0 ms by default (`EIRA_RUST_READ_P95_MS`) |
| Other read paths | p95 for `get_by_id`, `list_states`, `get_history` | Within 10× Python p95 + 1 ms |
| Data compatibility | 120-state chain, all fields and lookup/history paths | Exact equality |
| Hash compatibility | Full 64-character SHA3-256 digest | Bit-identical |

## CI evidence and limits

- Sprint 8 cutover coverage PR #109 completed its CI workflow successfully, including `rust-ci`, `rust-tauri-ci`, and Python 3.11/3.12 jobs.
- That test pass means the numeric p95 assertions above passed in that run.
- **Exact observed p95 values were not emitted or persisted by the existing benchmark test**, so this document deliberately does not invent specific measurements or claim a stable production latency.
- GitHub-hosted CI runners are shared and noisy. Treat the thresholds as regression gates, not as a production capacity guarantee. Record machine, OS, Rust/Python versions, sample count, and measured p50/p95 when collecting a dedicated benchmark run.

## Correctness guardrails

Performance tuning must not alter the immutable state schema, six-field SHA3-256 hash domain, canonical JSON serialization, or Python/Rust digest parity. Ordinary-state parity is gated by the full-digest regression; exotic float representations and legacy-hash migration remain explicitly outside blanket cutover clearance.
