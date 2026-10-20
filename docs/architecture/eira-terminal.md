# Eira Terminal — implementation contract

## Product goal

Provide a polished, real Linux terminal inside EiraOS for developers and advanced users. It must execute the user's actual shell, not simulate commands in the web UI. It should feel native to EiraOS while preserving normal Linux behavior and permissions.

## User experience

- Open as a workspace panel or dedicated terminal view; support multiple tabs and split panes in a later phase.
- Display a clear prompt with user, host, current directory, and shell status.
- Use a readable monospace font, restrained syntax colors, accessible contrast, configurable font size, and reduced-motion support.
- Provide keyboard-first navigation, selection, copy/paste, find, scrollback, clear-screen, and a visible running/exit status.
- Support shell history through the user's configured shell; do not build a parallel history store that unexpectedly captures secrets.
- Handle terminal resize, Unicode, colors, interactive prompts, Ctrl+C, Ctrl+D, job control, and full-screen TUI programs.
- Show actionable, non-secret errors if PTY creation or shell startup fails.

## Runtime architecture

1. React terminal component owns presentation and user input only.
2. Tauri Rust backend creates and owns a PTY and child process; use a maintained PTY implementation (evaluate `portable-pty` or equivalent against target platforms and licensing before selecting it).
3. Launch the logged-in user's configured shell as a normal user, with a controlled initial working directory and a documented environment.
4. Stream output and input through bounded channels. Support explicit resize, signal, close, and exit-status events.
5. On close, send a graceful termination signal, wait for a bounded period, then clean up the process group and PTY. Never leave orphaned shells.
6. Keep terminal execution separate from EiraSystemAPI's typed settings operations. The terminal is not a privileged system API.

## Security and privacy

- Never launch the shell as root or silently add `sudo`.
- Do not provide an unrestricted privileged `exec` endpoint to the frontend.
- The shell intentionally has the logged-in user's normal command-execution ability; clearly communicate that terminal commands can modify or delete user data.
- Avoid logging command input and terminal output by default; both may contain passwords, tokens, or private data.
- Validate session ownership for every terminal channel; do not allow one UI session to attach to another user's PTY.
- Bound input frames, output queues, scrollback, number of sessions, and idle resources.
- Use correct PTY permissions, process ownership, environment sanitization, and reliable cleanup.
- Treat clipboard access as a user-facing capability and never auto-exfiltrate clipboard contents.
- Do not implement command-blocking heuristics as the main safety boundary; rely on Linux user permissions and explicit authorization for privileged operations.

## Suggested API

Typed Tauri commands/events, not a generic system-level command runner:

- `terminal.create({ profile? }) -> { sessionId, shell, cwd }`
- `terminal.write({ sessionId, data })`
- `terminal.resize({ sessionId, cols, rows })`
- `terminal.signal({ sessionId, signal })` (allowlisted signals only)
- `terminal.close({ sessionId })`
- Events: `terminal.output`, `terminal.exit`, `terminal.error`

The implementation must confirm the appropriate Tauri event/channel pattern before coding. Enforce ownership and session state in Rust, not only in React.

## Tests and definition of done

- Unit tests for session lifecycle, invalid session IDs, bounds, resize, signal validation, and cleanup.
- Integration tests: run a command, preserve working directory, read environment, Unicode output, long output, exit code, Ctrl+C, Ctrl+D, and an interactive program.
- Security tests: cannot attach across sessions; shell runs as the intended unprivileged user; no shell is launched if PTY setup fails.
- UI tests for keyboard behavior, scrollback, resize, errors, multiple sessions, and accessible focus.
- Manual smoke test on the actual EiraOS Wayland session.

The feature is not complete until these checks pass on the supported Ubuntu build.
