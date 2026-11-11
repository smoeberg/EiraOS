# EiraOS Sprint 8 — IPC security and correctness audit

- **Task:** 8.1-audit
- **Reviewed file:** `crates/eira-ipc/src/lib.rs`
- **Baseline:** `0f50c4ff4a163917a612c1fb665624d8b8ec1dcc` (`0f50c4f`)
- **Scope:** Tokio JSON-RPC over Unix domain sockets (UDS); frame parsing, large-payload DoS, socket permissions/path lifecycle, and timeout semantics.
- **Change type:** Documentation-only audit. No implementation files changed.
- **Method:** Static review of the baseline source and crate configuration. These are code-review findings, not claims that exploit PoCs or load tests were run.

## Executive summary

The newline-delimited frame reader enforces a maximum while reading inbound frames, but the configured bound is not consistently an allocation bound: server responses and client requests are fully serialized into growable vectors before their size is checked. In addition, the server spawns an unbounded task for each accepted connection and has no per-connection read deadline. Socket mode defaults to `0660`, but the configured mode and parent directory trust are not validated, and path cleanup has race/lifecycle concerns. The client timeout bounds how long the caller waits; it does not cancel work already accepted by the server or establish whether a timed-out operation executed.

## Findings

### IPC-01 — Response size limit is checked after serialization

- **Severity:** High (availability / resource exhaustion)
- **Evidence:** `encode_response` serializes handler output into the growable `output: Vec<u8>` using `serde_json::to_writer`; `serve_connection` checks `response.len() > config.max_frame_bytes` only after `encode_response` has completed.
- **Impact:** `max_frame_bytes` does not cap peak memory used to construct a response. A handler returning a very large `RawValue` (or a large error `data`) can force a large allocation before the frame is rejected. Multiple concurrent responses multiply the memory pressure.
- **Recommendation:** Enforce a hard output limit during serialization (for example, a writer that refuses writes after the configured byte budget), and return a bounded protocol/internal error without retaining the oversized response. Treat both result payload and error data as untrusted for size purposes.
- **Validation to add:** A handler returning a payload larger than the configured limit should be rejected while output memory remains bounded; include an oversized error-data case.

### IPC-02 — Unbounded connection tasks and no server-side read deadline

- **Severity:** High (availability / denial of service; requires access to the socket)
- **Evidence:** `serve` calls `tokio::spawn` for every accepted connection without a semaphore or connection cap. `serve_connection` loops on `read_frame` without a read/idle timeout. Each connection allocates a frame buffer and may grow it up to `max_frame_bytes` (default 16 MiB), in addition to its reader and response buffers.
- **Impact:** A local client that can access the socket can open many connections and leave them idle or drip-feed incomplete frames. This can tie up tasks/file descriptors and grow memory substantially. The 16 MiB per-frame bound limits one frame, not aggregate resource consumption.
- **Recommendation:** Bound active connections (for example, with a Tokio semaphore), apply a deadline to receiving a complete request frame, and consider an aggregate/in-flight request budget. Ensure timeout and parse-error paths close the connection and release permits.
- **Validation to add:** Slow/incomplete frame expires; excess connections are rejected or queued under a documented cap; resources are released after disconnect and timeout.

### IPC-03 — Client request size is checked only after building the full serialized buffer

- **Severity:** Medium (availability / memory pressure in the client process)
- **Evidence:** In `UnixRpcClient::call`, `serde_json::to_writer(&mut request, ...)` serializes all parameters into a `Vec<u8>`; only after appending the newline does the code compare `request.len()` with `max_frame_bytes`.
- **Impact:** The request is rejected before transmission, but only after memory has already been allocated for the complete serialized value. A caller passing a very large parameter value can cause a transient large allocation despite the configured limit.
- **Recommendation:** Apply the same bounded-writer approach to request serialization, or serialize through a capped buffer that fails as soon as the byte budget is exceeded.
- **Validation to add:** Oversized params return `FrameTooLarge` without constructing a full unbounded request buffer.

### IPC-04 — Socket path lifecycle relies on directory trust and has replacement races

- **Severity:** Medium (local privilege boundary / availability; impact depends on parent-directory permissions)
- **Evidence:** `prepare_socket_path` uses `symlink_metadata` and then removes any existing socket, without checking its owner or whether it belongs to a live server. The check and removal/bind are separate filesystem operations. `SocketCleanup::drop` later removes the path by name without verifying that it still refers to the socket this server created. `serve` creates parent directories with `create_dir_all` but does not set or validate their permissions. `socket_mode` is configurable and passed directly to `set_permissions` without validating that it is suitably restrictive.
- **Impact:** Starting a second server can unlink the pathname of an existing live server. In a parent directory writable by another local principal, path replacement races can redirect connections or cause cleanup to remove a replacement entry. A permissive configured mode or parent directory can expose the IPC endpoint beyond the intended trust group.
- **Recommendation:** Require and document a trusted, non-world-writable parent directory; validate the requested socket mode against an explicit policy; avoid blindly unlinking an existing socket unless stale-socket ownership/liveness is established. For cleanup, verify socket identity (device/inode) before unlinking, and keep the check/bind/cleanup lifecycle resistant to path replacement.
- **Validation to add:** Existing live socket is not silently displaced; symlink/non-socket paths are rejected; unsafe modes and untrusted parent-directory conditions fail closed; cleanup does not remove a replacement path.

### IPC-05 — Request timeout does not imply server cancellation or a known outcome

- **Severity:** Medium (correctness / operation semantics)
- **Evidence:** `UnixRpcClient::call` wraps connect, serialization, write, and response read in `timeout(config.request_timeout, operation)`. On expiry it returns `IpcError::Timeout`. The server has no request deadline or cancellation message, and `serve_connection` invokes the synchronous `RpcHandler::handle` once a complete request is read.
- **Impact:** When the client times out after sending a request, dropping the client future/socket does not roll back handler side effects or prove that the request was not processed. The server may continue executing it, and the caller may retry a non-idempotent method and cause duplicate effects. A slow or blocking handler can also occupy a Tokio worker thread; the client deadline does not bound server execution.
- **Recommendation:** Document timeout as **outcome unknown** once request transmission may have begun. Require idempotency/deduplication for retryable operations, or add an explicit request deadline/cancellation protocol with clearly defined semantics. Ensure potentially blocking handler work is not run directly on an async executor worker.
- **Validation to add:** Simulate a request whose handler commits an effect but delays the response; verify the client receives timeout while the test demonstrates that the effect may still occur. Add an idempotency test for any retry mechanism.

### IPC-06 — JSON-RPC request ID and notification rules are not validated

- **Severity:** Low (protocol correctness / interoperability)
- **Evidence:** `BorrowedRequest` stores `id` as `&RawValue`, so the parser accepts any syntactically valid JSON value for the ID and echoes it. The field is required, so a JSON-RPC notification (which omits `id`) fails deserialization rather than being handled as a notification.
- **Impact:** Requests with object/array IDs can be answered even though JSON-RPC 2.0 IDs are constrained to string, number, or null; notifications do not receive the JSON-RPC notification behavior. This is unlikely to be a memory-safety issue, but it creates inconsistent protocol semantics.
- **Recommendation:** Explicitly validate ID shape and decide whether notifications are supported. If unsupported, reject them consistently as a documented protocol restriction; if supported, process them without sending a response.
- **Validation to add:** Tests for string/number/null IDs, invalid object/array IDs, missing ID, and malformed JSON.

## Frame parsing assessment

- **Positive:** `read_frame` consumes newline-delimited frames incrementally and checks the accumulated bytes against `max_frame_bytes` before extending the frame. It distinguishes clean EOF before a frame from EOF after a partial frame (`TruncatedFrame`).
- **Positive:** The client rejects an oversized serialized request before writing it, and both client/server inbound frame reads use the configured maximum.
- **Caveat:** These checks bound inbound frame length, not all allocations associated with parsing/serialization or the aggregate memory across connections. In particular, findings IPC-01 through IPC-03 remain open.
- **Configuration:** Defaults are a 16 MiB frame, 64 KiB read buffer, 10-second client request timeout, and socket mode `0660`. The 10-second timeout is client-side only; the 16 MiB limit is per frame, not a process-wide budget.

## Suggested remediation order

1. **P1:** Enforce response serialization bounds and cap active connections / incomplete-frame lifetime (IPC-01, IPC-02).
2. **P2:** Bound request serialization; harden socket directory/mode and socket lifecycle; document timeout outcome semantics (IPC-03, IPC-04, IPC-05).
3. **P3:** Validate JSON-RPC IDs and explicitly define notification support (IPC-06).

## Out of scope

No source changes, test changes, dependency changes, or runtime configuration changes were made as part of this audit. Findings should be addressed in a separate implementation task with targeted regression tests.
