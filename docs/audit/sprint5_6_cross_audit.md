# Sprint 5+6 Cross-audit — Issue #60

**Scope:** read-only audit of Sprint 5 fleet code and available Sprint 6 PRs. This report is the only file in branch `audit/s6-cross-audit`; no implementation files are changed.

**Baseline:** `main` at `ea9320b70c74493c3899e640341961944509d30a` (2026-10-20). This is newer than required baseline `c89a56e`.

## Findings

### [blocker] Kotlin hash-format validation accepts strings containing a valid substring

- **Location:** `android/eira-core-binding/src/main/java/app/eira/core/EiraStateEngine.kt:53` on PR #74 (`feat/s6-kotlin-binding`).
- **Evidence:** `HASH_PATTERN = Regex("[0-9a-f]{64}")` is used with `matches(hash)` at lines 24–26. The regex is not anchored; Kotlin's `Regex.matches` does require the entire input to match, so this specific combination does **not** accept a valid substring with a prefix/suffix. No finding is raised for this pattern as currently used. (Recorded to clarify the audit checked the call site, not just the regex.)
- **Disposition:** no defect confirmed for this call site.

### [blocker] Mixed-validity sync batch mutates state instead of rejecting the whole batch

- **Location:** `app/daemons/fleetd.py:98-133` (main).
- **Evidence:** `push_blocks()` increments `invalid` when `decrypt_state()` raises `PayloadIntegrityError` (lines 102–107), then proceeds to append successfully decrypted states from `pending` (lines 109–130) and returns both `accepted` and `invalid` (lines 132–137).
- **Impact:** a batch containing at least one invalid envelope can still commit other states. This violates the stated reject-all fail-closed contract for a mixed-validity batch.
- **Coverage:** the visible E2EE tests in PR #76 cover wrong-key rejection and assert no blocks are stored when all submitted blocks use the wrong key. They do not establish reject-all behavior for a batch containing both valid and invalid blocks. Add a regression test asserting the store remains unchanged for that mixed batch.

### [major] Room hash input uses platform JSON serialization; byte-for-byte cross-language parity is not demonstrated

- **Location:** `android/app/src/main/java/app/eira/storage/StateEntity.kt:18-28` on PR #79 (`feat/s6-room-store`).
- **Evidence:** `jsonForHash()` assembles the hash input with `JSONObject` and `.toString()`, including a nested `JSONObject(payload)`. The Python state contract and native FFI hash the canonical state representation; semantically equivalent JSON is not sufficient if serialized bytes differ.
- **Impact:** ordering/escaping and numeric representation differences (especially large integers, floats, Unicode and nested payloads) can produce different hashes across Python, native FFI and Android.
- **Verification boundary:** PR #77 supplies shared vectors for Unicode, 200-level nesting, integers above 2^53 and floats, but the Room PR's added instrumented test is a disabled skeleton according to its PR description. The available evidence does not prove Room serialization passes the shared vectors.
- **Required verification:** make the Room hash-input path consume the shared fixtures and assert exact hash equality with the Python/native expected values. This is an audit finding about missing demonstrated parity, not a claim that a specific vector has already failed.

### [major] Sprint 6 Room replay test is not active CI evidence

- **Location:** `android/app/src/androidTest/...` in PR #79; PR description identifies the instrumented test skeleton as `@Ignore`.
- **Evidence:** PR #79 states that the instrumented test is ignored. The patch adds `replayAll()` in `RoomStateStore.kt:50-68`, which validates chain ancestry and recomputes each stored state's hash.
- **Impact:** the new replay validation path lacks an active test proving tampered hashes, broken links and duplicate IDs fail closed in the Android/Room runtime.
- **Recommendation:** enable an Android test that exercises these cases and consumes the shared vectors. The test's exact path/line is not asserted here because the available PR metadata did not provide the ignored test's changed-file patch.

### [minor] Sprint 5 header parsing coerces input types rather than strictly rejecting them

- **Location:** `app/fleet/merkle_sync.py:24-48` (main).
- **Evidence:** `StateHeader.from_value()` converts identifiers/hashes with `str(...)` and metadata with `int(...)`, while defaulting omitted `version` to `1` and `timestamp_ns` to `0`.
- **Impact:** malformed wire values can be normalized instead of rejected at the input boundary. This weakens the explicit unknown-input/missing-data rejection contract and can hide type mismatches between Python and Kotlin/FFI.
- **Recommendation:** validate required fields and exact JSON types before constructing a header; add tests for booleans, numeric strings, missing version/timestamp, and invalid timestamp types. Confirm whether defaults are explicitly part of the agreed compatibility contract before treating the defaults themselves as defects.

## Scope audit

The available PR file lists were checked against their stated tasks:

- **PR #74 — Kotlin FFI binding:** `android/eira-core-binding/build.gradle.kts`, `EiraStateEngine.kt`, and `EiraStateEngineTest.kt` (3 files; matches its stated three-file scope).
- **PR #76 — Fleet E2EE sync:** `tests/test_fleet_e2ee_sync.py` and `tests/test_fleet_sync.py` (2 files; the latter is not listed in the PR description's “new tests” summary, so confirm it is within the task's authorized scope before merge).
- **PR #77 — shared Android vectors:** `tests/fixtures/android_test_vectors.json` (1 file; matches its stated fixture-only scope).
- **PR #79 — Room encrypted state store:** `RoomStateStore.kt`, `StateDao.kt`, `StateEntity.kt` (3 files; matches its stated scope).

No evidence of out-of-scope files was found in these changed-file lists. This is a changed-path check, not a full architectural scope certification.

## Ruff, tests, and CI

- This branch changes documentation only; no Python source or tests are changed.
- `ruff check .` and `python -m pytest tests/ -q` were **not run in this audit environment**. No local test count or CI result is claimed.
- The GitHub combined status query for baseline commit `ea9320b70c74493c3899e640341961944509d30a` returned no status entries; this is not evidence that CI passed.
- PR #76's description reports 202 passed / 8 skipped; PR #79 reports 211 passed / 2 skipped. These are PR-authored claims and were not independently rerun here.
- Cross-platform tests should run under Python 3.11 and 3.12 and include deep nesting, timestamps, JSON text/number distinctions, Unicode and integers above 2^53.

## Summary

**Confirmed blocker:** mixed-validity batches in `FleetSyncService.push_blocks()` can partially mutate the store.

**Major verification gap:** Room's `JSONObject` hash serialization has not been shown to match the canonical Python/native bytes using the shared fixtures, and the Room replay test is reported as ignored.

The Kotlin regex concern was checked against its use of `Regex.matches` and is **not** reported as a defect. Findings above distinguish confirmed behavior from missing verification; no implementation changes are proposed in this audit PR.
