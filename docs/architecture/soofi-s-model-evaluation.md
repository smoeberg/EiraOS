# Soofi S — Monitoring and Evaluation Plan for EiraOS

**Status:** Evaluation plan; not a model adoption decision  
**Owner:** EiraOS architecture/model integration  
**Review trigger:** Officially accessible weights and a clear license for the intended use  
**Default policy:** Local inference; no automatic cloud escalation

## 1. Purpose

Track Soofi S as a possible future language-understanding and task-planning model for EiraOS. The goal is to evaluate it against current candidates using reproducible EiraOS-specific tests, not to depend on an announced release or reported benchmark scores.

Soofi S must remain an optional provider behind EiraOS' model-independent interface. The deterministic EiraOS Gate remains the only authority for permissions, consent, and protected execution.

## 2. Current status: verify, do not assume

Project availability, model access, license, benchmark claims, quantizations, and release dates can change. This document deliberately does not freeze those details as facts. At each review, record the date, exact official source URL, model revision, access result, license text/version, and evidence.

A model page or downloadable preview does not necessarily mean unrestricted public access, production readiness, or permission to redistribute. A planned open release is not a committed delivery date. Do not use a model in a shipped product until the exact artifact's terms have been reviewed.

## 3. Official sources to monitor

Check these primary sources at a regular cadence (for example, monthly) and when a release announcement is made:

1. Soofi project site: https://www.soofi.info/
2. Soofi S project page: https://www.soofi.info/soofi-s/
3. Soofi Project model organization: https://huggingface.co/Soofi-Project
4. DFKI official site/news: https://www.dfki.de/

Use official project announcements and the exact model repository as the source of truth. Third-party posts and benchmark aggregations can be leads, not release/license authority.

### Review log template

Append an entry for each review:

| Field | Value to record |
|---|---|
| Review date | ISO 8601 date |
| Official announcement | URL and publication date |
| Exact model artifact | Repository, revision/commit, variant and quantization |
| Access | Public, gated with approval, or unavailable; include reproducible result |
| License | Exact license identifier and link to the full text |
| Redistribution / commercial use | Explicitly verified; do not infer from “open” wording |
| Runtime | Ollama, llama.cpp, vLLM or other; exact version and known limitations |
| Local-only verification | Network behavior and telemetry/configuration review |
| Decision | Monitor / sandbox test / benchmark / accept / reject |
| Evidence | Commands, logs, hashes, benchmark outputs and reviewer |

## 4. Entry criteria before benchmarking

Do not begin integration beyond an isolated sandbox until the following are checked:

- **Access:** exact weights can be acquired legally and reproducibly.
- **License:** terms permit the planned use, including commercial deployment and redistribution if applicable.
- **Artifact identity:** record the model revision, tokenizer/chat template, runtime version, quantization, and SHA-256 hashes.
- **Local operation:** basic inference works with networking disabled after artifacts are acquired, unless a specific network-dependent feature has been separately reviewed and explicitly enabled.
- **Tool-call format:** confirm the exact checkpoint's tool-call syntax and runtime support; a model-card claim alone is insufficient.
- **Resource fit:** measure actual RAM/VRAM, load time, tokens/second, first-token latency, power/thermal behavior, and stability on representative target PCs.
- **Language fit:** test German and English, and test Danish if Danish remains a supported EiraOS interface language. Do not assume a language is supported because another European language is.
- **Maintenance:** record release status, known issues, update policy, and a rollback/pinning strategy.

MoE active parameter count alone does not determine memory use. Total weights, quantization, KV cache, context length, runtime overhead, and concurrency all affect hardware requirements.

## 5. Benchmark design

Compare Soofi S against the exact pinned versions of the current EiraLang/EiraAI candidates, including Teuken and Devstral Small 2 where those remain viable. Include any new candidate only by adding it to the same harness and test corpus.

Use at least 200 curated EDP scenarios initially, with versioned inputs, expected outcomes, and a held-out set. Include:

- ordinary requests with unambiguous intent;
- multilingual requests and translation;
- entity and parameter extraction;
- missing information requiring clarification;
- ambiguous or contradictory instructions;
- valid and invalid action proposals;
- unsupported action types and malformed arguments;
- prompt injection and attempts to override system policy;
- requests for prohibited or out-of-scope actions;
- duplicate/retried requests and stale context;
- long multi-step tasks where planning is useful;
- refusal/abstention when no safe proposal can be made.

Keep test cases and scoring rules stable across candidates. Do not put held-out examples into prompts or fine-tuning data.

### Metrics

| Area | Measure |
|---|---|
| Intent understanding | Exact action-type accuracy and per-class precision/recall |
| Argument extraction | Exact argument match; missing/extra/incorrect fields |
| Schema reliability | Valid schema rate; unknown-field rate |
| Clarification | Correct abstention/clarification on ambiguous or incomplete input |
| Tool selection | Correct tool/capability selection and argument correctness |
| Safety | Unauthorized proposal rate and successful Gate bypasses |
| Language | Per-language results, including Danish if in scope |
| Reliability | Reproducibility across repeated runs; failure and timeout rates |
| Performance | First-token latency, throughput, peak RAM/VRAM, load time and stability |
| Sovereignty | Verified offline behavior and documented network activity |

Report raw counts and per-category results as well as aggregate scores. Model confidence is not a truth score or permission grant.

## 6. Security is a release gate, not an average score

A candidate must not be accepted if any test demonstrates that model output can bypass the Gate or directly execute protected actions. Security checks must include:

- malformed or missing fields fail closed;
- forbidden targets and capabilities are rejected by the Gate;
- changing parameters invalidates prior confirmation;
- permissions and session assurance are rechecked at execution time;
- retries/concurrency do not duplicate non-idempotent effects;
- direct executor calls cannot bypass authorization;
- cloud routing cannot happen silently;
- partial failure is reported honestly.

The model may propose an unsafe action during adversarial testing; the critical requirement is that the Gate blocks it and the result is auditable. Record both proposal quality and Gate enforcement behavior.

## 7. Integration strategy

1. **Monitor:** follow official sources; do not block current EiraOS work on a future release.
2. **Acquire:** once access and license are clear, pin the exact artifact and record hashes.
3. **Sandbox:** test runtime loading and offline inference with no system-action permissions.
4. **Adapter:** implement the model behind the existing model-independent interface; return typed proposal, abstain, or error.
5. **Benchmark:** run the same versioned EDP test set used for other candidates.
6. **Gate tests:** prove the model has no direct OS/API/executor path and cannot bypass Gate policy.
7. **Hardware validation:** run on representative target machines, including the minimum supported hardware.
8. **Decision:** publish results, limitations, license review outcome, and a go/no-go recommendation.
9. **Rollout:** only after approval, enable behind a feature flag with pinned versions and a rollback path.

## 8. Decision rules

**Advance to a pilot only if all are true:**

- exact artifact and license are acceptable;
- local operation and network behavior are verified;
- benchmark results meet the project's per-language and task thresholds;
- all Gate security acceptance tests pass;
- resource use meets the target hardware budget;
- reproducible evaluation artifacts and rollback are available.

**Reject or defer** if weights remain inaccessible, terms are ambiguous, local-only behavior cannot be established, the runtime is unstable, tool-call reliability is insufficient, target hardware is exceeded, or any Gate bypass is found.

Do not replace both EiraLang and EiraAI merely because one model supports tool calling. Test whether a single-model configuration is sufficiently accurate, robust, maintainable, and efficient compared with a two-model configuration.

## 9. Relationship to EiraOS architecture

This plan supplements [EiraOS System Architecture](eiraos-system-architecture.md), [EiraSystemAPI](eira-system-api.md), and the repository's Gate implementation/tests.

- The model is an untrusted parser/planner and action-proposal component.
- EDP and EiraOS-owned contracts remain stable across model changes.
- The Gate remains authoritative for schema/semantic validation, authorization, consent, and execution.
- Local inference is the default; cloud escalation requires explicit user choice and policy checks.
- No model, benchmark, or trust/confidence score can authorize an action.

**Decision today:** keep Soofi S on the candidate list; do not make it a dependency or delay Gate work while waiting for public access.
