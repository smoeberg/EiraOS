# Sprint 7 · Task 7.1 — Tauri IPC security review

**Branch:** `audit/s7-tauri-ipc`  
**Target:** `ui/src-tauri/src/ipc.rs` (newline-framed JSON-RPC 2.0 over AF_UNIX)  
**Base:** `main` @ `0251f12`  
**Reviewer:** Sprint 7 Agent 1  

## Executive summary

The bridge is **largely fail-closed** and suitable as the sole UI→daemon path. Daemon names are **allowlisted** before path construction, responses are **size-capped**, and timeouts **drop the connection**. No path-traversal into arbitrary sockets was found via the public `send_ipc_request` API.

Residual risks are **operational / depth-of-defense**: env-controlled socket roots, lack of client-side rate limiting, and possible leakage of daemon JSON-RPC error bodies into the UI error string.

---

## 1. Path-traversal (`socket_path` / `canonical_daemon`)

### Finding: **Mitigated (P0 path-traversal blocked)**

```text
send_ipc_request(daemon, …)
  → canonical = canonical_daemon(&daemon)?   // allowlist only
  → path = socket_path(canonical)            // "{canonical}.sock"
```

- User-supplied `daemon` is **never** concatenated into a path until it matches a fixed set (`stated`, `identityd`, `fleetd`, `veritasd`, `intentd`, `graphd`, `walletd`, `presenced`, `contextd`).
- Inputs such as `../../tmp/evil`, `/run/foo`, `stated/../fleetd` return `kind: invalid_daemon`.
- `socket_path` only joins `"{daemon}.sock"` onto `socket_root()`; the daemon segment contains no `/` or `..` after canonicalisation.

### Residual

| Risk | Severity | Notes |
|------|----------|--------|
| `EIRA_SOCKET_DIR` / `EIRA_RUN_DIR` can redirect the entire root | Low (local env) | Attacker who already controls process environment can point the bridge at another directory of sockets. Not UI-controlled. |
| Symlink races on the socket file | Low | `symlink_metadata` + `is_socket()` reject non-socket endpoints; TOCTOU between check and `connect` remains theoretically possible. |

**Recommendation:** Keep the allowlist as the sole path authority. Optionally `canonicalize` the socket root at startup and reject roots that are world-writable.

---

## 2. Timeout path (partial frames)

### Finding: **Correct fail-closed behaviour**

- Entire `exchange` is wrapped in `tokio::time::timeout(request_timeout(), …)`.
- Default **5 s**, clamped to **100 ms … 30 s** via `EIRA_UI_IPC_TIMEOUT_MS`.
- On timeout the future is **dropped** → `UnixStream` is dropped → OS closes the FD. Partial bytes in the local `response_bytes` buffer are **not** returned to React.
- Caller receives structured `kind: "timeout"` only.

### Residual

| Risk | Severity | Notes |
|------|----------|--------|
| Server-side half-open connection until daemon read times out | Info | Expected for one-shot request/response; no client leak. |
| Timeout error string recomputes `request_timeout()` | Info | Harmless; value is stable for the process unless env changes mid-flight. |

**Recommendation:** None required for correctness. Optional: cancel-friendly daemon timeouts aligned with the UI clamp.

---

## 3. Connection lifecycle / reconnect

### Finding: **No connection pool; errors are structured; UI cannot hang beyond timeout**

| Failure mode | `kind` | Behaviour |
|--------------|--------|-----------|
| Unknown daemon | `invalid_daemon` | Immediate `Err`, no connect |
| Socket path missing | `socket_unavailable` | `symlink_metadata` error |
| Path exists but is not a socket | `invalid_endpoint` | Rejected before connect |
| Connect refused / EPERM | `connect_failed` | Mapped from `UnixStream::connect` |
| Write failure | `write_failed` | Mapped |
| Peer closes without body | `empty_response` | `read == 0` |
| Read I/O error | `read_failed` | Mapped |
| Timeout | `timeout` | See §2 |

Each call opens a **fresh** connection and closes it when `exchange` returns or the timeout drops the future. There is no shared mutable connection that could leave the UI blocked waiting on a dead peer beyond the timeout budget.

**Recommendation:** Document for React that every IPC call is independent; retry policy belongs in the UI layer with backoff.

---

## 4. Error classification for React

### Finding: **Adequate and parseable**

Errors are JSON strings:

```json
{ "kind": "<machine_code>", "message": "<human>", "daemon": "<name>", "method": "<rpc>" }
```

Distinct kinds cover allowlist, params, size, transport, protocol, and daemon-side JSON-RPC errors (`daemon_error`).

### Residual

| Risk | Severity | Notes |
|------|----------|--------|
| `daemon_error` embeds `error.to_string()` from the JSON-RPC error object | Medium | May surface internal rule IDs / paths to the UI. Prefer mapping to a stable `user_message` field when present. |
| `response_too_large` used both for oversize **and** for missing trailing newline | Low | Message always says “exceeds N bytes”; slightly imprecise for truncated lines. |

**Recommendation:** When `envelope.error` contains `data.user_message`, prefer that string for `BridgeError.message` (aligns with UX rule 5).

---

## 5. DoS / protocol / async hazards

### Mitigations present

| Control | Implementation |
|---------|----------------|
| Request size cap | `MAX_REQUEST_BYTES = 4 MiB` before write |
| Response size cap | `AsyncReadExt::take(MAX_RESPONSE_BYTES + 1)` + length check after `read_until` |
| Method length | 1…256 characters |
| Params shape | Object or null only |
| Async I/O | `tokio` `UnixStream` + `BufReader`; no blocking std I/O on the hot path after connect metadata |
| Request id correlation | Response `id` must match; mismatch → `response_mismatch` |

### Residual risks

| Risk | Severity | Notes |
|------|----------|--------|
| No client-side rate limit | Medium | A compromised or buggy UI can open many sockets and stress daemons. Rely on daemon/systemd limits. |
| Large legitimate responses near 16 MiB | Low | Allocates up to the cap; acceptable for desktop. |
| JSON parser on untrusted daemon output | Low | `serde_json` on size-capped buffer; fail-closed to `invalid_response`. |
| IPC token injection via `EIRA_IPC_TOKEN` | Info | Token only sent if env set; ensure UI process env is not attacker-writable. |

### Not observed

- Blocking `std::net` calls inside the async command path.
- Unbounded `Vec` growth without `take`.
- Path construction from raw daemon strings after the allowlist.

---

## 6. Contrast tests added

Under `#[cfg(test)]` in `ipc.rs`:

1. **Allowlist rejects path-like daemon names** (strengthened cases).
2. **Oversized / non-terminated response** → `response_too_large` (mock daemon).
3. **Response id mismatch** → `response_mismatch`.
4. **Non-socket endpoint** → `invalid_endpoint` (regular file at expected path).

These document the security contract; they are expected to **pass** (controls already in place). No `xfail` required for P0 path-traversal.

---

## 7. Verdict

| Question | Verdict |
|----------|---------|
| Path-traversal to arbitrary sockets via `daemon`? | **No** (allowlist) |
| Partial frame leak on timeout? | **No** |
| Hang without timeout? | **No** (hard timeout) |
| Structured errors for UI? | **Yes** (minor `daemon_error` hygiene) |
| Critical unfixed vulnerability? | **None identified** |

**Merge readiness:** Documentation + tests only; no production code change required for P0. Follow-ups (rate limit, `user_message` mapping) can be separate `fix/` PRs.

---

## Appendix — error `kind` catalogue

`invalid_daemon`, `invalid_method`, `invalid_params`, `encode_failed`, `request_too_large`, `timeout`, `socket_unavailable`, `invalid_endpoint`, `connect_failed`, `write_failed`, `read_failed`, `empty_response`, `response_too_large`, `invalid_response`, `response_mismatch`, `daemon_error`, `unsupported_platform`.
