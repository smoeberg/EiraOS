# Sprint 4 cross-audit — CEL, policy store, intent parser and release notes

**Review baseline:** `main` at `fdd0b29ecd076abb46e0dd5eda23509a9c94eacc` (2026-10-20).  
**Scope:** read-only review of the Sprint 4 security boundaries and release metadata. Findings below are static; the repository CI status is not a substitute for independent review.

## Findings

| Severity | Area | Finding | Recommendation |
|---|---|---|---|
| High | CEL evaluator | The evaluator uses an allowlisted AST surface and explicit complexity limits; security tests cover Python introspection/import chains, large expressions and deterministic behavior. | Preserve deny-by-default AST handling; rerun adversarial tests on every change and keep the evaluation budget bounded. |
| High | Intent parser | Hardening tests cover mutation/injection inputs, invalid structured output, transport errors and offline fallback. | Keep LLM output untrusted; validate the schema after parsing and never allow parser output to bypass policy evaluation. |
| High | Policy enforcement | Correctness depends on the intent execution path checking the active policy result before applying a proposed state change. | Add/retain an integration test proving denied proposals cannot reach the state mutation path; review all alternate entry points. |
| Medium | Policy store | Versioned policy storage is present; correctness also depends on deterministic active-version selection and auditable activation/deactivation. | Test concurrent updates, rollback, and missing/corrupt active policy behavior. Fail closed when policy state is ambiguous. |
| Medium | Error UX | Fail-closed results must remain distinguishable from successful evaluations and include safe user-facing messages. | Verify JSON-RPC errors include the documented `user_message` field without exposing stack traces or secrets. |
| Medium | Release metadata | `RELEASE_NOTES_v0.4.0.md` is explicitly a draft; the changelog distinguishes proposed releases from published ones, but historical version statements should be checked against actual tags. | Do not create or advertise a release tag without owner approval and green CI on the exact commit. |

## Required verification before release

- [ ] Run `ruff check .` and `python -m pytest tests/ -q` on the merge candidate.
- [ ] Confirm Python 3.11, Python 3.12 and Rust CI checks are green on the exact commit.
- [ ] Exercise a denied intent through the public daemon/API and prove no state mutation occurs.
- [ ] Exercise malformed/timeout LLM responses and verify deterministic safe fallback.
- [ ] Confirm active policy version and audit history across restart.
- [ ] Owner reviews the final release notes and approves any tag/publication.

## Decision

No static finding in this document is evidence of a release having been published. This cross-audit records testable risk areas and gates; it does not replace runtime acceptance or owner approval.
