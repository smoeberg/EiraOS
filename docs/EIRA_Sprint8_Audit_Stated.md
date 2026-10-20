# Sprint 8 Audit — eira-stated

**Audit scope:** crates/eira-stated/src/lib.rs with cross-check against app/core/state.py, crates/eira-core/src/lib.rs and the stated FFI boundary.

**Audit date:** 2026-10-20

## Executive finding

The Rust state engine is structurally fail-closed and the SQLite pool/connection lifetimes are sound. The canonical SHA3-256 field domain matches the Python canonical contract for ordinary JSON values.

However, the cross-language hash contract is **not fully equivalent for all supported JSON numbers**, and Python currently accepts a **legacy hash format** that Rust deliberately rejects. These are compatibility findings rather than immediate memory-safety defects.

No code changes were made as part of this audit.

## 1. SHA3-256 domain separation / canonical input

### Match confirmed

Python defines the hashed state domain as exactly these six fields:

id, version, timestamp_ns, type, payload, previous_state_id.

The Python implementation:
- constructs a new six-field body;
- sorts object keys;
- uses compact separators;
- preserves Unicode (ensure_ascii=False);
- hashes UTF-8 bytes with SHA3-256;
- excludes the stored hash field itself.

Rust eira-core::compute_hash_from_value applies the same six-field projection and recursively canonicalizes JSON before SHA3-256. Therefore StateRecord::compute_hash() in eira-stated uses the same domain and does not accidentally hash the persisted hash field.

The known Unicode state vector in the Rust core tests is also compatible with the Python contract.

### Important nuance: no explicit cryptographic domain tag

Neither implementation prefixes the byte stream with a literal domain marker such as EIRA_STATE_V1:. Thus the current "domain separation" is the **schema/field projection**, not a cryptographic domain-prefix construction.

This is correct for cross-language parity: adding a Rust-only domain prefix would break Python compatibility. If a future explicit cryptographic domain tag is desired, it must be specified and changed in both implementations together.

### Finding S8-AUD-01 — numeric canonicalization risk

**Severity: Medium — interoperability**

Python uses json.dumps(...) while Rust uses serde_json number rendering. For integers the representations are compatible in the normal state model, but floating-point values can have different textual canonicalization rules (exponent formatting, decimal representation and related edge cases).

The Python payload type permits arbitrary JSON values, including numbers. Therefore "same semantic JSON" does not guarantee "same SHA3 input bytes" for every possible numeric payload.

**Recommendation:** define the numeric subset permitted by the cross-platform state contract, or add explicit cross-language canonicalization vectors covering integers, decimal/floating values, exponent notation and nested numeric payloads. Do not add an ad-hoc Rust formatter without updating the Python contract.

## 2. Legacy hash compatibility

### Finding S8-AUD-02 — Python accepts hashes Rust rejects

Python State.is_hash_valid() accepts either:
1. the current canonical hash, or
2. compute_legacy_hash(), which uses default Python JSON serialization.

Rust StateRecord::validate_hash() accepts only the canonical eira-core::compute_hash_from_value() result.

This creates an intentional-but-undocumented cutover asymmetry: a state that Python considers valid because it carries a legacy hash can be rejected by Rust eira-stated.

**Severity: Medium — cutover compatibility**

**Recommendation:** explicitly decide whether legacy hashes are migration-only. If yes, document a bounded migration policy and keep the Rust engine fail-closed on legacy hashes. If legacy hashes remain valid indefinitely, the Rust validator needs an explicit compatibility path and matching tests.

## 3. rusqlite/r2d2 pooling lifetime

### Finding: no lifetime defect identified

The pool stores SqliteConnectionManager; individual calls obtain a PooledConnection through StateStore::connection().

Observed lifetime discipline is sound:
- connection() returns an owned pool guard;
- query/statement borrows remain inside the function scope;
- list_states() consumes the query iterator before the connection guard is dropped;
- append() drops its prepared statement before returning;
- initialization uses a temporary connection guard;
- the FFI handle owns the complete StateStore, so the pool outlives every operation made through that handle;
- closing the FFI handle drops the boxed StateStore, which drops the pool after outstanding operation borrows have ended.

The in-memory configuration deliberately uses pool size 1, preserving a single shared SQLite in-memory database rather than accidentally creating separate per-connection databases.

**Assessment: PASS.**

## 4. Fail-closed behavior

### Hash and persistence path

append() validates the state hash before any SQLite write. A mismatch returns HashMismatch; a missing previous state returns MissingPrevious; SQLite/pool failures propagate as typed errors.

Immutable UPDATE/DELETE triggers further prevent ordinary mutation of persisted states.

### FFI path

The FFI layer converts engine errors to negative error codes, catches Rust panics, and returns null pointers for failed string-returning operations. This preserves the fail-closed boundary for callers.

### Finding S8-AUD-03 — chain validation semantics are split

eira-core::validate_chain_from_json() validates:
- unique state IDs;
- previous-state ordering/existence in the supplied chain;
- each state's canonical hash.

eira-stated::StateStore::append() validates the state's own hash and checks that previous_state_id exists in SQLite, but does not independently re-validate the previous state's hash during append.

Because the database schema makes states immutable and appends validate their own hashes, this is reasonable under the trusted-storage invariant. It is not equivalent to validating an entire imported chain.

**Severity: Low/Medium — invariant boundary**

**Recommendation:** document that append() is an incremental persistence operation, while complete chain validation belongs to the chain-validation API. Do not silently treat a successful append as proof that the entire chain is cryptographically valid.

## 5. Overall audit status

| Area | Status | Finding |
|---|---|---|
| Six-field SHA3 domain projection | **PASS** | Matches Python canonical contract |
| Unicode / compact JSON behavior | **PASS** | Compatible for ordinary JSON strings/objects |
| Numeric canonicalization | **REVIEW** | S8-AUD-01 |
| Python legacy-hash acceptance | **REVIEW** | S8-AUD-02 |
| r2d2/rusqlite connection lifetime | **PASS** | No lifetime defect identified |
| Append fail-closed behavior | **PASS** | Hash checked before write |
| FFI error/panic boundary | **PASS** | Errors do not become success |
| Whole-chain vs incremental validation | **REVIEW** | S8-AUD-03 |

## Conclusion

eira-stated does **not** need an emergency code correction based on this review. Its pool ownership and immediate fail-closed behavior are sound, and its canonical six-field SHA3 domain agrees with Python for the normal state contract.

Before declaring the Sprint 8 Rust cutover fully cross-platform equivalent, the numeric canonicalization edge cases and the legacy-hash migration policy should be made explicit and covered by shared vectors.

**Audit result: PASS WITH COMPATIBILITY FINDINGS.**
