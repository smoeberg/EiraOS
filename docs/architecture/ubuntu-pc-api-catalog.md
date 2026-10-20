# Ubuntu PC API Catalog for EiraOS

Status: **initial inventory / research required**  
Target: **Ubuntu Desktop 26.04 LTS (Resolute Raccoon)**. Use the latest available 26.04.x point release for development and integration testing; at the time this decision was recorded, the current point release is **26.04.1 LTS**.  
This catalog is a planning artifact, not evidence that EiraOS has implemented these integrations.

## Target platform decision

- **Primary compatibility target:** Ubuntu Desktop 26.04 LTS (Resolute Raccoon).
- **Development / CI / integration baseline:** latest available Ubuntu 26.04.x point release, currently 26.04.1 LTS; do not pin testing to the original 26.04.0 image if a later point release is available.
- **Release policy:** validate all supported interfaces against the actual 26.04 package versions, D-Bus introspection data, permissions/Polkit policy, and desktop session. Do not assume an interface is available just because it exists in another Ubuntu release.
- **Compatibility policy:** Ubuntu 24.04 LTS may be added as a secondary compatibility target only through an explicit decision and separate CI/integration coverage. Ubuntu 26.10 is not the primary target because it is an interim release with a shorter support window.
- **Support lifecycle:** Ubuntu 26.04 LTS standard security maintenance is currently listed through May 2031; re-check official lifecycle dates as part of release planning.

## Design decisions

1. Ubuntu's supported interfaces are the system source of truth; EiraSystemAPI is EiraOS's stable, versioned contract above them.
2. Cockpit is an optional reuse/integration candidate, not a required foundation and not the source of truth for system capability.
3. Prefer documented D-Bus APIs and native service interfaces where available. Use command-line tools only behind narrow, validated adapters when no suitable stable API exists.
4. Never expose a generic privileged shell or `run(command)` operation through EiraSystemAPI. Use service-specific operations, native authorization and PolicyKit.
5. The EiraOS GUI and terminal run as the logged-in user, never as root by default. The terminal is separate from typed system-management APIs.
6. Classify each capability as **PC Core**, **PC Optional**, or **Server/Enterprise**. Do not exclude a shared Linux component merely because servers also use it.
7. No capability is marked implemented until the adapter, UI, automated tests and real Ubuntu integration evidence are available.

## Initial capability inventory

The component/interface names below are candidates to verify against the chosen Ubuntu release and EiraOS session architecture. Package availability, D-Bus methods, permissions and desktop integration must be confirmed before implementation.

| Capability | Initial Ubuntu interface / component | Profile | Cockpit role to investigate | Validation required |
|---|---|---|---|---|
| Network and Wi-Fi | NetworkManager D-Bus; `nmcli` only as a narrow fallback | PC Core | Cockpit NetworkManager page uses NetworkManager/D-Bus when available | Confirm Ubuntu networking backend and permissions; read/write tests |
| VPN connections | NetworkManager connection APIs and installed VPN plugins | PC Core | Reuse only if the relevant page/module and plugins fit desktop UX | Test supported VPN types, secrets and Polkit |
| Bluetooth | BlueZ D-Bus | PC Core | No assumed coverage; investigate modules | Device discovery, pairing, authorization and missing-adapter tests |
| Audio and microphones | PipeWire / WirePlumber; desktop session APIs | PC Core | Usually direct desktop integration, not assumed Cockpit coverage | Device enumeration, default-device changes, session permissions |
| Displays and scaling | Wayland compositor / desktop settings; DRM/KMS underneath | PC Core | Not assumed Cockpit coverage | Identify EiraOS compositor and supported settings API; multi-monitor tests |
| Power and battery | UPower; systemd-logind for relevant session/power operations | PC Core | Cockpit may expose host-oriented information; verify exact feature | Battery/no-battery cases, suspend authorization, laptop vs desktop |
| Storage and removable media | UDisks2 D-Bus; udev for device events | PC Core | Investigate Cockpit storage module and dependency footprint | Read-only discovery first; mount/eject/format authorization and destructive-operation safeguards |
| Package installation | APT/dpkg; PackageKit only where compatible and present | PC Core | Investigate Cockpit package/software-update module | Transaction locks, offline state, cancellation, errors, repository policy |
| OS updates | Ubuntu-supported APT and release-specific update mechanisms | PC Core | Cockpit software-update integration is a candidate, not presumed compatible | Test on target Ubuntu release; avoid assuming PackageKit works with every network backend |
| System services | systemd D-Bus / systemctl via a constrained adapter | PC Optional | Cockpit services page is a strong reuse candidate | Unit discovery, start/stop/restart authorization and failure handling |
| Logs and diagnostics | systemd journal; journalctl as a constrained query fallback | PC Core | Cockpit journal page is a reuse candidate | Pagination, filtering, privacy and permission handling |
| Printers | CUPS APIs; SANE for scanning | PC Optional | Verify available Cockpit modules; likely direct desktop integration for printers | Discover/configure/remove printer; missing service and permission tests |
| Users and accounts | AccountsService, systemd-logind and PAM-related system interfaces | PC Optional | Investigate Cockpit users module; avoid exposing server-only assumptions | Account privilege boundaries, authentication and destructive-action tests |
| Drivers and firmware | Ubuntu package metadata, DKMS packaging, fwupd where supported | PC Optional | No assumed Cockpit coverage | Hardware detection, signed packages, firmware applicability and reboot requirements |
| Input devices | libinput and compositor/desktop settings | PC Core | Not assumed Cockpit coverage | Keyboard, mouse, touchpad and device-specific settings |
| Locale, time and keyboard layout | systemd-timedated where applicable; desktop settings and locale tooling | PC Core | Cockpit host-time settings are a candidate only where appropriate | Locale/layout switching, authorization and session restart behavior |
| Accessibility | AT-SPI, Orca and compositor/desktop integration | PC Core | Not assumed Cockpit coverage | Screen-reader, keyboard-only and high-contrast workflows |
| Camera and media devices | PipeWire and V4L2, with session-level permissions | PC Core | Not assumed Cockpit coverage | Permissions, device disappearance and privacy indicator behavior |
| Firewall | UFW/nftables, depending on the supported Ubuntu configuration | PC Optional | Cockpit coverage must be proven before reuse | Do not allow competing firewall managers; rules validation and rollback |
| Virtualization / containers / remote host management | libvirt/KVM, container runtimes, SSH and related packages | Server/Enterprise or PC Optional by product decision | Cockpit has relevant server-oriented features; do not install by default | Explicit product scope, package footprint and isolation tests |

## Cockpit reuse and maintenance policy

Cockpit is a Linux administration console made of separate packages and features. Evaluate each candidate independently rather than treating Cockpit as one universal API.

For each proposed reuse, record:

- Exact upstream module/package and upstream documentation URL.
- Ubuntu package name and version available in the selected release and updates/backports policy.
- Runtime dependencies, services, ports/sockets and privileges required.
- Whether integration is through a documented stable API, a supported embeddable page, or a private/internal component.
- Whether the module fits a local desktop session without introducing unnecessary web-server or remote-administration exposure.
- Upstream activity, release cadence, security process, license and fork/build instructions.
- A replacement path using Ubuntu-native interfaces behind the same EiraSystemAPI contract.

**Important:** Cockpit's own developer guide says only explicitly documented components/APIs should be integrated; undocumented behavior may change. Do not couple EiraOS to internal Cockpit UI components as if they were stable APIs.

## Required record for every capability

Each inventory item must eventually include:

- Capability ID and user-visible purpose.
- Target Ubuntu release and required packages.
- Exact API/interface, methods/properties and official documentation.
- Read operations and write operations.
- Authorization model, Polkit actions and least-privilege boundaries.
- EiraSystemAPI contract/version and structured error mapping.
- Cockpit reuse decision: reuse / optional integration / native adapter / not applicable.
- Automated unit and integration tests, including missing service/hardware and permission denial.
- Implementation state: **Not investigated**, **Investigated**, **Implemented**, or **Verified on target Ubuntu**.
- Evidence link to test output or review.

## Official starting references

- Ubuntu documentation: https://documentation.ubuntu.com/
- Cockpit source repository: https://github.com/cockpit-project/cockpit
- Cockpit documentation: https://cockpit-project.org/documentation
- Cockpit developer guide: https://docs.cockpit-project.org/cockpit-guide/latest/guide/development.html
- Cockpit NetworkManager internals: https://docs.cockpit-project.org/cockpit-guide/latest/guide/feature-networkmanager.html
- NetworkManager D-Bus API: https://networkmanager.dev/docs/api/latest/
- BlueZ documentation: https://bluez.readthedocs.io/
- UDisks documentation: https://storaged.org/doc/udisks2-api/latest/
- systemd D-Bus interfaces: https://www.freedesktop.org/software/systemd/man/latest/org.freedesktop.systemd1.html
- UPower D-Bus API: https://upower.freedesktop.org/docs/

These are starting points, not proof of availability or compatibility on the final EiraOS image. Pin and verify documentation for the chosen Ubuntu release before implementation.

## Definition of done for the catalog

- The supported Ubuntu release is explicitly chosen.
- Every PC Core capability has a verified interface, package/dependency list, authorization model and test plan.
- Cockpit reuse is documented feature by feature, including reasons to avoid it.
- Server/Enterprise items are excluded from the default PC profile unless explicitly approved.
- Unsupported or unverified capabilities remain visibly marked as such.
