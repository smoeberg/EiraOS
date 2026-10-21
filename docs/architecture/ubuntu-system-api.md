# Ubuntu System API — coverage and implementation contract

## Goal

EiraOS must expose Ubuntu/Linux system capabilities through a small, typed, auditable API used by the GUI. Ubuntu remains the source of truth for system state and policy. This document is the implementation contract and coverage checklist; a row marked **planned** or **unverified** is not a claim that integration exists.

## Architecture

1. **GUI** — renders state and requests explicit actions; it does not run privileged commands.
2. **EiraSystemAPI** — versioned typed operations, input validation, capability discovery, structured errors, request correlation, and audit events.
3. **Adapters** — use the supported system service/API first (usually D-Bus); use command-line tools only where no suitable stable API exists and their output/exit codes are tested.
4. **Ubuntu services / kernel** — own actual state and authorization. Use Polkit or the service's native authorization model for privileged operations. Never grant the GUI blanket root access.

The existing Tauri bridge in `ui/src-tauri/src/ipc.rs` speaks to EiraOS daemons over Unix sockets. It is not by itself an Ubuntu system API. Keep the system API logically separate from the existing domain-daemon IPC, and document any bridge between them.

## API contract

Every capability should provide, where applicable:

- `get_status` / `list` for read-only state;
- explicit `validate` and `apply` operations for mutations;
- a typed result and stable error code (unsupported, unavailable, permission_denied, invalid_argument, conflict, timeout, operation_failed);
- capability discovery, so the UI can distinguish unsupported hardware from a broken service;
- cancellation / progress for long-running actions;
- event subscription or polling with bounded resource use;
- audit records for changes, including actor, requested operation, result, and timestamp (never secrets);
- unit tests with mocked adapters and integration tests against real services in a disposable Ubuntu environment.

Never report success before the underlying service confirms it. Never silently fall back to a weaker authorization path.

## Coverage matrix

Status meanings: **Existing substrate** means Ubuntu provides the service/API; **EiraOS integration unverified** means repository inspection has not established a working adapter and GUI flow. This is a planning baseline, not an exhaustive statement about every possible Ubuntu installation.

| Area | Ubuntu/Linux interface to evaluate | Required EiraOS operations | Initial status |
|---|---|---|---|
| Network / Wi-Fi / Ethernet / VPN | NetworkManager D-Bus | list devices and connections, scan, connect/disconnect, configure, VPN status | EiraOS integration unverified |
| Bluetooth | BlueZ D-Bus | adapter/device discovery, pair, connect/disconnect, trust, remove | EiraOS integration unverified |
| Display / monitors | Wayland compositor protocols; DRM/KMS where appropriate | enumerate outputs, resolution/scale/layout where compositor permits | EiraOS integration unverified |
| Audio | PipeWire / WirePlumber | devices, default sink/source, volume, mute, route | EiraOS integration unverified |
| Power / battery | UPower; logind for supported actions | battery state, power profile where supported, suspend/reboot/shutdown through authorized service | EiraOS integration unverified |
| Storage / removable media | UDisks2, udev, filesystem tools | enumerate, mount/unmount/eject, SMART where available, safe error reporting | EiraOS integration unverified |
| Users / sessions | AccountsService, systemd-logind, PAM and Polkit as applicable | list users/sessions; privileged account/session operations via approved policy | EiraOS integration unverified |
| Packages / OS updates | APT and supported package-management services/tools | check updates, show details, apply updates with explicit consent and progress | EiraOS integration unverified |
| Drivers / firmware | kernel, udev, Ubuntu driver tooling, fwupd where supported | inventory hardware/driver/firmware, explain recommendations, controlled install/update | EiraOS integration unverified |
| Printers / scanners | CUPS and relevant discovery services | enumerate, add/remove, queue status, test page where supported | EiraOS integration unverified |
| Date / time / locale | systemd timedated, locale configuration interfaces | read/change timezone, time sync status, locale and keyboard layout | EiraOS integration unverified |
| Accessibility | desktop/system accessibility services; compositor capabilities | discover and expose available assistive settings | EiraOS integration unverified |
| Files / removable devices | UDisks2, udev, standard filesystem interfaces | device events, safe mount state, capacity and health where available | EiraOS integration unverified |
| Firewall / security status | ufw/nftables and system security interfaces | read status; changes only through narrowly authorized operations | EiraOS integration unverified |
| Terminal / shell | PTY, user's configured shell, Unix process APIs | true interactive shell, resize/signals, lifecycle, history policy | Not implemented/verified as a GUI terminal |

## Security requirements

- Do not run the Tauri GUI or terminal as root.
- Do not expose a generic privileged `run(command)` system API.
- Validate operation names, typed arguments, lengths, and state transitions at the backend boundary.
- Privileged operations must use Polkit/native service authorization and fail closed when authorization is unavailable.
- Do not log passwords, tokens, Wi-Fi secrets, private command input, or sensitive command output.
- Shell access is intentionally powerful: it runs as the logged-in user, with normal Linux permissions. Clearly distinguish it from structured system settings operations.
- Use allowlisted environment setup, correct PTY ownership/permissions, process-group signal handling, bounded output buffering, and reliable child cleanup.
- Audit and test denial paths, missing services, unavailable hardware, timeout, cancellation, and partial failures.

## Definition of done

A capability is **implemented** only when all are present:

1. Backend adapter and typed API contract.
2. Real GUI control and visible loading/error/permission states.
3. Tests for normal, denied, unavailable, invalid, and failure cases.
4. Integration test on supported Ubuntu image/service version.
5. Documentation of package/service dependencies and limitations.

Until those checks pass, display the capability as unavailable or unverified rather than implying that it works.
