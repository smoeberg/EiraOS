# Audit F — critical gaps and synthesis

**Baseline:** `main` at `fdd0b29ecd076abb46e0dd5eda23509a9c94eacc` (2026-10-20).  
This is a static repository audit. It does not substitute for a clean Ubuntu boot/install test.

## Blockers

1. **Desktop boot/package acceptance is not evidenced.** UI and service source files exist, but a clean Ubuntu 24.04 build, login session, service startup, and AppArmor enforcement must be demonstrated with logs.
2. **E2EE empty payload contract mismatch.** Issue #68 says missing/empty payload must fail closed, while the existing test previously allowed an empty dictionary. PR #117 changes encryption and decryption to reject it; do not close the gap until CI and review pass.
3. **Hardware provenance was inferred from manifest text.** Camera/sensor strings are not cryptographic proof. PR #118 removes that implicit trust and requires an injected verifier before marking a hardware signature verified. A real deployment still needs a defined attestation format and trusted vendor roots.
4. **EUTL trust-list lifecycle is incomplete at the deployment boundary.** `EUTrustedList` consumes a locally provided snapshot; this does not itself establish official XML signature verification, refresh, freshness, or rollback protection. Those must be implemented and tested before claiming current EUTL trust.

## UX-damaging / high priority

1. **UI-to-daemon contracts need a live end-to-end check.** Static method registration and mock-based UI tests do not establish that the installed UI talks to the deployed daemons successfully.
2. **Failure paths need a release runbook.** Capture expected behavior for daemon unavailable, socket permission denied, timeout, malformed response, and restart/recovery.
3. **Fleet sync needs an integration run after the E2EE change.** Validate that empty payloads are rejected without corrupting the Merkle chain and that ordinary payloads sync between paired devices.

## Cosmetic / maintainability

1. Keep the changelog consistent about which version is released versus proposed; do not describe a proposed tag as published.
2. Make the GUI audit, implementation tracker, and release cross-audit part of the release checklist.
3. Define Sprint 10 scope explicitly; the prior Sprint 9 plan exists, but no authoritative Sprint 10 execution plan was identified in the reviewed baseline.

## Evidence / decisions

- E2EE behavior: `app/fleet/e2ee.py`, `tests/test_e2ee.py`, issue #68, proposed fix PR #117.
- Veritas hardware provenance: `app/veritas/c2pa_engine.py`, `tests/test_veritas_shield.py`, proposed fix PR #118.
- QEAA trust boundary: `app/veritas/layer2_qeaa.py`; EUTL snapshot parsing is not the same as official list refresh/signature validation.
- GUI evidence: `ui/src-tauri/`, `ui/src/components/`, `app/daemons/`; live Ubuntu evidence still required.

## Overall decision

**Not release-ready on static evidence alone.** Continue with Sprint 9 packaging and security work, then close the remaining gates only when test/host evidence is attached.
