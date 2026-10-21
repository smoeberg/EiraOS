# Ubuntu PC API Coverage Matrix for EiraOS

Status: **planning and verification baseline — not implementation evidence**  
Branch target: `feature/system-api-terminal-foundation`  
Primary platform: Ubuntu Desktop 26.04 LTS (Resolute Raccoon). Verify package versions, D-Bus introspection, permissions and desktop-session behavior on the exact image used by CI.

This matrix turns the initial catalog into capability-level work items. Every row starts as **Not investigated** until evidence is attached. Do not change a row to Implemented or Verified based on documentation alone.

## Status vocabulary

- **Not investigated** — no interface/behavior evidence collected for the target image.
- **Investigated** — interface, dependencies, authorization and test design documented; no complete EiraOS integration proven.
- **Implemented** — adapter, typed contract, UI and automated tests exist.
- **Verified on target Ubuntu** — implementation also passed integration tests on the supported Ubuntu image, with evidence linked.
- **Blocked** — dependency, API, permissions or UX decision prevents safe implementation; record the reason.

## Priority and profile

- **P0**: foundational PC capability or a security-critical path.
- **P1**: expected PC settings/maintenance capability.
- **P2**: optional feature; product decision or hardware-specific support may be needed.
- **PC Core / PC Optional / Server-Enterprise** are product scope labels, not claims of support by Ubuntu or EiraOS.

## Coverage matrix

| ID | Priority / profile | User-visible function | Candidate Ubuntu interface(s) to verify | Read operations | Mutations / side effects | Authorization and safety gate | Minimum verification evidence | Initial state |
|---|---|---|---|---|---|---|---|---|
| SYS-NET-01 | P0 / PC Core | Ethernet, Wi-Fi and network status | NetworkManager D-Bus; inspect active backend | Devices, state, IP/DNS, connections, signal | Scan, connect/disconnect, edit connection | Native NetworkManager/Polkit; protect connection secrets; confirm before disconnecting active link | D-Bus introspection; read/write tests; denied permission; no adapter/device; active-link warning | Not investigated |
| SYS-NET-02 | P1 / PC Core | VPN profiles and status | NetworkManager D-Bus plus installed VPN plugins | Profile metadata, active tunnel, plugin availability | Connect/disconnect, add/edit/remove profile | Never expose secrets in logs/UI; validate supported plugin/type | Per-plugin availability matrix; secrets redaction; denied/cancelled cases | Not investigated |
| SYS-BT-01 | P1 / PC Core | Bluetooth devices and pairing | BlueZ D-Bus; desktop agent/session integration | Adapter state, discovery, paired devices, battery where exposed | Power adapter, pair, trust, connect/disconnect, remove | Explicit pairing/trust; confirm removal; session agent requirements | No adapter, pairing rejected, device disappears, authorization tests | Not investigated |
| SYS-AUD-01 | P0 / PC Core | Speakers, headphones, microphones, volume | PipeWire / WirePlumber and supported session APIs | Nodes, default sink/source, mute/volume, route | Set default, volume/mute, route | Respect per-user session; avoid logging audio/device secrets | Hot-plug, device switch, no-device, permission and volume-boundary tests | Not investigated |
| SYS-DSP-01 | P0 / PC Core | Monitors, resolution, scale and layout | EiraOS compositor / Wayland protocols; DRM/KMS only where appropriate | Outputs, modes, current layout | Change scale/resolution/layout only if compositor supports it | Do not write directly to kernel interfaces as a shortcut; recover safely from invalid mode | Single/multi-monitor, hot-plug, unsupported mode, rollback and session tests | Not investigated |
| SYS-PWR-01 | P0 / PC Core | Battery and power state | UPower; systemd-logind; power-profiles-daemon if present | Battery, AC state, supported actions/profile | Profile change, suspend, shutdown, restart | Explicit confirmation for shutdown/restart; native authorization; avoid unsupported hardware assumptions | Laptop/desktop/no battery; suspend denied; cancellation; action result from service | Not investigated |
| SYS-STO-01 | P0 / PC Core | Disks, removable media, mount/eject | UDisks2 D-Bus; udev events; filesystem tools only behind adapter | Devices, mount state, capacity, filesystem, health where available | Mount, unmount, eject; format only as a separately gated destructive flow | Formatting must show exact target and data-loss warning; never infer target from display name alone | Hot-plug, busy device, permission denial, read-only media, safe eject and destructive confirmation | Not investigated |
| SYS-PKG-01 | P1 / PC Core | Install/remove applications and package details | APT/dpkg; evaluate PackageKit compatibility on 26.04 | Installed packages, candidates, repositories, transaction state | Install/remove/update | Explicit user consent; package lock handling; show origin and dependencies; no arbitrary package command | Lock contention, offline, repository error, cancellation, partial transaction and rollback behavior | Not investigated |
| SYS-UPD-01 | P0 / PC Core | OS update availability and installation | Ubuntu-supported APT/update mechanisms; exact 26.04 services/tools | Update list, security classification if available, reboot-required status | Refresh metadata, apply updates, reboot | Explain impact; explicit consent; never report success before package manager confirms | Clean VM, stale metadata, network failure, interrupted update, pending reboot | Not investigated |
| SYS-SVC-01 | P2 / PC Optional | Manage selected system services | systemd D-Bus; systemctl only via constrained adapter | Allowlisted unit status and properties | Start/stop/restart/enable only approved units | Strict unit/action allowlist; Polkit/native authorization; never expose generic service or shell control | Unknown unit, protected unit, failed transition, authorization denied | Not investigated |
| SYS-LOG-01 | P1 / PC Core | Logs and diagnostics | systemd journal API; journalctl as constrained fallback | Bounded, paginated, filtered journal queries | Export diagnostic bundle only with user review | Redact secrets and personal data; bound query/output size | Permission denied, huge result, pagination, redaction and export-consent tests | Not investigated |
| SYS-PRN-01 | P2 / PC Optional | Printers, queues and scanning | CUPS API; SANE and discovery services where available | Printers, queue state, scanner availability | Add/remove printer, queue action, test page | Confirm removal; do not assume scanner service is installed | Missing CUPS/SANE, network printer unavailable, denied operation, queue failure | Not investigated |
| SYS-USER-01 | P2 / PC Optional | Local users and sessions | AccountsService, systemd-logind, PAM and Polkit as applicable | User/session metadata permitted to current actor | Account or session changes only after explicit product/security design | High-risk administrative boundary; never expose password material; require authorized flow | Non-admin denial, logged-in user protection, malformed input and audit tests | Not investigated |
| SYS-DRV-01 | P2 / PC Optional | Driver and firmware status | Ubuntu driver tooling/package metadata; fwupd where supported; DKMS metadata | Hardware inventory, candidate driver/firmware, applicability | Install driver/firmware through supported package/service flow | Show vendor/source, compatibility and reboot implications; no unsupported downloads | Unsupported hardware, unsigned/unavailable package, failed update, reboot-required | Not investigated |
| SYS-INP-01 | P0 / PC Core | Keyboard, mouse, touchpad and input settings | libinput plus compositor/desktop settings APIs | Devices and supported settings | Change supported per-user settings | Do not assume universal writable libinput API; separate device inventory from settings | Touchpad absent, hot-plug, unsupported option, user-session test | Not investigated |
| SYS-TIME-01 | P1 / PC Core | Date, time, timezone and time sync | systemd-timedated; actual time-sync service; desktop settings | Timezone, sync state, locale | Set timezone/time sync where supported | Time changes affect schedules/security; require authorization and confirmation | Permission denial, invalid timezone, sync service absent, session behavior | Not investigated |
| SYS-LANG-01 | P0 / PC Core | Language, locale and keyboard layout | Desktop settings/session APIs; locale tooling behind adapter | Available locales/layouts and current selection | Change locale/layout | Distinguish system-wide from per-user settings; avoid silently restarting apps | Unsupported locale, layout change, persistence after login, accessibility checks | Not investigated |
| SYS-ACC-01 | P0 / PC Core | Screen reader, contrast, text size and accessibility | AT-SPI, Orca, compositor and desktop settings | Available assistive capabilities and state | Toggle supported settings | Accessibility controls must be usable without pointer; preserve keyboard access | Keyboard-only end-to-end; screen-reader flow; settings persist across session | Not investigated |
| SYS-CAM-01 | P1 / PC Core | Camera and media-device privacy | PipeWire, V4L2 and session permission mechanisms | Device availability and active state where exposed | Change permissions only through supported portal/session controls | No covert activation; visible status; honor session permissions | Device missing, app permission denied, hot-unplug and privacy-state tests | Not investigated |
| SYS-FS-01 | P1 / PC Core | File-system and removable-device information | Standard filesystem APIs; UDisks2/udev for device events | Capacity, mount point, free space, removable status | No general file mutation in this system API; device operations remain in SYS-STO-01 | Prevent path traversal; avoid duplicate ownership of mount actions | Permission boundaries, disappeared mount, special files and bounded output | Not investigated |
| SYS-FW-01 | P2 / PC Optional | Firewall status and narrow rule management | UFW or nftables based on declared supported configuration | Active backend, status and known rules | Validated rule changes only through one selected manager | Never run competing managers; preview changes and provide rollback; no arbitrary rules text | Backend conflict, invalid rule, remote-lockout warning, rollback and denial tests | Not investigated |
| SYS-TERM-01 | P0 / PC Core | Real interactive Linux terminal | PTY via Tauri/Rust backend; configured user shell | Process/session status | User-shell commands with normal user permissions | Not an EiraSystemAPI privileged-command path; no root by default; safe PTY ownership, bounded output and cleanup | Unicode/TUI, resize, Ctrl-C/D, exit, multiple sessions, child cleanup, secret-log policy | Not investigated |
| SYS-SEC-01 | P0 / PC Core | Security and permission status | Ubuntu security interfaces and narrowly scoped service APIs; exact scope TBD | Firewall/security-update/encryption status only where reliable APIs exist | Changes routed to dedicated capability with authorization | No single opaque “security score”; show source, freshness and unknown states | Missing source, stale data, denied access, contradictory states | Not investigated |
| SYS-VIRT-01 | P2 / Server-Enterprise or PC Optional | Virtual machines and containers | libvirt/KVM and explicitly selected container runtime | Installed runtime and workload status | Create/start/stop/delete workloads | Off by default until product scope chosen; isolation and resource limits | Runtime absent, permission denial, resource exhaustion, isolation tests | Not investigated |
| SYS-REMOTE-01 | P2 / Server-Enterprise or PC Optional | Remote host administration | SSH and separately evaluated Cockpit modules/APIs | Remote host status with explicit connection | Remote changes only through a separate trust/session flow | No default remote listener or server stack; host identity and consent required | Host-key mismatch, expired credentials, disconnect/partial failure, audit | Not investigated |

## Cross-cutting requirements for every row

1. **Evidence:** attach the exact target-image version, package versions, interface documentation/introspection output, and test run.
2. **Contract:** define typed request/response, versioning, stable errors, timeouts, cancellation and idempotency where relevant.
3. **Authorization:** identify the real service authorization/Polkit action. Fail closed; never silently switch to a weaker path.
4. **Truthful UI:** distinguish unsupported hardware, missing service, permission denial, transient failure and success confirmed by the underlying service.
5. **Testing:** cover normal, invalid input, permission denied, service missing, device absent, timeout/cancellation and partial failure where applicable.
6. **Audit/privacy:** record actor, operation, outcome and timestamp; never log credentials, tokens, Wi-Fi secrets or private terminal input/output by default.
7. **Architecture:** UI is presentation; EiraSystemAPI is a stable typed contract; adapters own Ubuntu-specific details. Existing daemon IPC is not itself the Ubuntu system API.
8. **Cockpit:** decide feature by feature. Record exact module/package/version, dependencies, privileges, stable integration surface, local desktop fit, maintenance/license and native-adapter replacement path. Do not embed undocumented internal UI components.
9. **No false completion:** source documentation or a mock test alone cannot mark a capability implemented or verified on Ubuntu.

## Ubuntu 26.04 verification notes

The official Ubuntu 26.04 release notes must be used as the release-specific baseline. In particular, verify package/tool assumptions against 26.04 rather than copying instructions from older LTS versions. The official notes state that `pkcon` was removed in 26.04 and a PackageKit `pkgcli` utility is available; removable media mount locations also changed to `/run/media`. Treat these as test prompts, not as proof that a specific EiraOS integration is complete.

Official starting source: https://documentation.ubuntu.com/release-notes/26.04/summary-for-lts-users/

## Definition of done for this matrix

- Every PC Core row has a selected interface, package/dependency list, permission model, EiraSystemAPI contract and test plan.
- All claims of implementation point to code, UI and automated tests.
- Every “Verified on target Ubuntu” claim links to reproducible integration evidence from the supported image.
- PC Optional and Server-Enterprise scope is explicit; server/remote-management packages are not installed by default.
- The product can display unsupported/unverified states honestly without implying the whole PC is integrated.
