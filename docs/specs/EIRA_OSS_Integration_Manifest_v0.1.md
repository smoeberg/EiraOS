# EIRA OSS Integration Manifest v0.1

**Status:** Normativ � indhold i EIRA OS Bundle  
**Dato:** 26. juni 2026  
**Baseline:** Ubuntu 24.04 LTS (Noble)  
**Relateret:** [EIRA_Windows_Parity_Architecture_v0.1.md](EIRA_Windows_Parity_Architecture_v0.1.md), [EIRA_Update_Release_Train_v0.1.md](EIRA_Update_Release_Train_v0.1.md), [EIRA_OSS_Operations_Model_v0.1.md](EIRA_OSS_Operations_Model_v0.1.md), [EIRA_EDR_Partner_Requirements_v0.1.md](EIRA_EDR_Partner_Requirements_v0.1.md)

---

## 1. Form�l

Dette manifest definerer **pr�cis hvilke open source- og tredjepartskomponenter** der indg�r i en certificeret **EIRA OS Bundle** � med pakkenavne, EIRA-integration API og Windows-paritetspunkt.

> **EIRA signerer og tester hele stacken som �n enhed** � som Windows Imaging g�r for WDM + Defender + Intune agent.

---

## 2. Bundle-lag (udvidet)

```
eira-bundle-<version>-<channel>/
??? manifest.json                 # master � se �3
??? ubuntu/
?   ??? package-list.lock         # alle deb-pakker med pr�cis version
?   ??? apt-sources.pin
?   ??? oss-integration.yaml      # dette dokument som maskinl�sbar liste
??? eira/                         # EIRA-native binaries (.deb)
??? oss-config/                   # kuraterede configs per komponent
?   ??? wazuh-agent/
?   ??? falco/
?   ??? sssd/
?   ??? ...
??? signatures/
```

---

## 3. `manifest.json` � OSS-sektion (normativ skema)

```json
{
  "bundle_id": "eira-bundle-2026.06.26-stable",
  "ubuntu_base": "24.04.2",
  "eira_platform": "2.4.1",
  "oss_stack_version": "1.0.0",
  "parity_matrix": {
    "drivers": "green",
    "ad_gpo": "yellow",
    "legacy_io": "yellow",
    "edr": "green",
    "win32": "red",
    "vpn": "green",
    "mdm": "yellow",
    "display": "green"
  },
  "components": [
    {
      "id": "sssd",
      "tier": "core",
      "parity_point": 2,
      "packages": ["sssd", "sssd-ad", "sssd-tools", "realmd", "adcli"],
      "eira_interface": "eira-identityd ? sssd.conf D-Bus/socket",
      "health_probe": "sssd --version && systemctl is-active sssd"
    }
  ]
}
```

---

## 4. Integrations-tiers

| Tier | Indhold | M�lgruppe |
|------|---------|-----------|
| **CORE** | P0 � pilot-minimum | Alle managed EIRA PC |
| **STANDARD** | CORE + sikkerhed + legacy + provisioning | Kommune production |
| **PREMIUM** | STANDARD + kommerciel EDR-slot + MAAS hooks + AWX | Enterprise / stor kommune |

---

## 5. CORE bundle � komponentliste

### 5.1 Basis-platform (Ubuntu � ikke EIRA, men l�st i bundle)

| Komponent | Ubuntu-pakker (24.04) | Windows-paritet | EIRA-interface |
|-----------|----------------------|-----------------|----------------|
| Kernel + firmware | `linux-image-generic`, `linux-firmware`, `fwupd` | Windows Update (drivers) | `eira-hardware-agent` ? D-Bus `org.freedesktop.fwupd` |
| udev / PnP | `udev`, `systemd` | PnP | Inventory via osquery |
| Netv�rk | `network-manager`, `network-manager-openconnect`, `wireguard` | NDIS / NIC | governance ? `keyfile` i `/etc/NetworkManager/` |
| TLS | `ca-certificates`, `openssl` | Schannel roots | Trust Framework |
| Audit kernel | `auditd`, `audispd-plugins` | Security log | Intent Audit correlation ID |

---

### 5.2 Identity & AD (paritetspunkt 2)

| Komponent | Pakker | Version (pin i lock) | API / integration |
|-----------|--------|----------------------|-------------------|
| **SSSD** | `sssd`, `sssd-ad`, `sssd-krb5`, `sssd-ldap`, `sssd-tools` | LTS security | `systemctl`, `/var/lib/sss/`; `eira-identityd` skriver `sssd.conf` |
| **realmd** | `realmd`, `adcli` | LTS | `realm join`, `realm list` � governance preseed |
| **Kerberos** | `krb5-user`, `krb5-config` | LTS | keytab via identityd |
| **Entra OIDC** | � (EIRA native) | `eira-identityd` | OAuth2/OIDC mod `login.microsoftonline.com` |
| **Smartcard** | `pcscd`, `opensc` | LTS | PKCS#11 ? identityd |
| **Biometri** | `fprintd`, `libpam-fprintd` | LTS | PAM stack � policy-gated |

**EIRA daemon:** `eira-identityd`  
**Kontrakt:** Unix socket `/run/eira/identity.sock` � JSON-RPC: `session`, `assurance`, `step_up_status`

---

### 5.3 VPN (paritetspunkt 6)

| Komponent | Pakker | Protokol | EIRA-interface |
|-----------|--------|----------|----------------|
| **OpenConnect** | `openconnect`, `network-manager-openconnect` | Cisco AnyConnect, GlobalProtect (delvis) | governance push `*.nmconnection` |
| **openfortivpn** | `openfortivpn`, `network-manager-fortisslvpn` | Fortinet SSL VPN | samme |
| **WireGuard** | `wireguard`, `wireguard-tools` | WireGuard | `wg-quick@` systemd units |
| **strongSwan** | `strongswan`, `network-manager-strongswan` | IKEv2/IPsec | NM profiles |
| **Pre-login VPN** | `systemd` units + `NetworkManager-wait-online` | Always On | `eira-vpn@.service` template � governance |

**EIRA daemon:** `eira-governance-agent` (VPN profile compiler)  
**Kontrakt:** Policy YAML `vpn:` ? `/etc/NetworkManager/system-connections/` + optional `/etc/systemd/system/eira-vpn-prelogin.service`

---

### 5.4 Endpoint security (paritetspunkt 4)

| Komponent | Pakker / install | Rolle | EIRA-interface |
|-----------|------------------|-------|----------------|
| **Falco** | Falco `.deb` (CNCF) eller `falco` repo | eBPF runtime detection | governance ? `/etc/falco/falco_rules.local.yaml`; events ? syslog |
| **Wazuh agent** | `wazuh-agent` (Wazuh repo) | HIDS + log forward | manager IP via governance; Intent Audit ? `localfile` |
| **AppArmor** | `apparmor`, `apparmor-utils` | MAC | EIRA-profiler i `/etc/apparmor.d/eira-*` |
| **ClamAV** | `clamav`, `clamav-daemon`, `clamdscan` | AV baseline | on-access via policy (optional daemon) |
| **OpenSCAP** | `libopenscap8`, `oscap` | compliance scan | `oscap xccdf eval` � Fleet scheduled job |

**EIRA daemons:** `eira-governance-agent` + Intent Audit emitter  
**Event flow:**

```
Intent Audit (JSON Lines) ???
Falco (syslog) ????????????????? Wazuh agent ??? SIEM / Fleet
auditd ??????????????????????
```

**CEF export:** `eira-governance-agent` ? `/var/log/eira/audit.cef` (STANDARD tier)

---

### 5.5 Fleet & inventory (paritetspunkt 7)

| Komponent | Pakker | Rolle | EIRA-interface |
|-----------|--------|-------|----------------|
| **osquery** | `osquery` (osquery.io repo) | Hardware/software inventory | `osqueryi` config i `/etc/osquery/`; queries fra Fleet |
| **cloud-init** | `cloud-init` | First-boot provisioning | `user-data` med EIRA enroll token |
| **Flatpak** | `flatpak` | App distribution | governance whitelist remotes |

**EIRA daemon:** `eira-governance-agent` + Fleet Agent Protocol  
**Kontrakt:** [EIRA_Fleet_Agent_Protocol_v0.1.md](EIRA_Fleet_Agent_Protocol_v0.1.md) � mTLS til Fleet Control

**osquery � obligatoriske queries (CORE):**

| Query | Windows-paritet |
|-------|-----------------|
| `system_info` | Device inventory |
| `os_version` | OS build |
| `rpm_packages` / `deb_packages` | Installed software |
| `usb_devices` | USB inventory |
| `disk_encryption` (via extensions) | BitLocker-status |
| `logged_in_users` | Current session |

---

### 5.6 Hardware & periferi (paritetspunkt 1)

| Komponent | Pakker | Rolle | EIRA-interface |
|-----------|--------|-------|----------------|
| **fwupd** | `fwupd`, `fwupd-signed` | Firmware update | D-Bus; Fleet rapporterer `fwupdmgr get-devices` |
| **CUPS** | `cups`, `cups-client`, `cups-browsed` | Print | governance printer allow-list |
| **SANE** | `sane`, `sane-utils` | Scanner | app whitelist |
| **Mesa/GPU** | `mesa-utils` + vendor driver pakker | Graphics | Support Matrix |

**EIRA daemon:** `eira-hardware-agent` (CORE � ny)  
**Kontrakt:** D-Bus `org.freedesktop.fwupd` + periodic report til governance-agent

---

### 5.7 Display & session (paritetspunkt 8)

| Komponent | Pakker | Rolle | EIRA-interface |
|-----------|--------|-------|----------------|
| **Wayland** | Ubuntu session (Wayland default 24.04) | Display server | eira-shell som fullscreen client |
| **Compositor** | `labwc` eller `cage` (STANDARD) | Minimal WM | autostart eira-shell |
| **XWayland** | `xwayland` | Legacy X11 | whitelisted apps only |
| **PipeWire** | `pipewire`, `pipewire-pulse`, `wireplumber` | Audio/video | xdg-desktop-portal |
| **Portals** | `xdg-desktop-portal`, `xdg-desktop-portal-gtk`, `xdg-desktop-portal-wlr` | File picker, screencast | Legacy Bridge primary path |

**EIRA daemon:** `eira-shell` (Tauri)  
**Kontrakt:** Wayland layer-shell eller fullscreen p� labwc

---

## 6. STANDARD bundle � till�g til CORE

| Komponent | Pakker | Paritetspunkt | EIRA-interface |
|-----------|--------|---------------|----------------|
| **Ubuntu Security Guide** | `usg` | CIS hardening | `usg audit` ? Compliance Engine |
| **Lynis** | `lynis` | Security audit | scheduled report |
| **FreeRDP** | `freerdp3-x11` | RDS / Windows 365 client | Legacy Runtime orchestrator |
| **libvirt/KVM** | `qemu-kvm`, `libvirt-daemon-system`, `virt-manager` (Builder) | Hyper-V-lignende | `eira-legacy-runtime` |
| **fuse3** | `fuse3`, `libfuse3-3` | Legacy fil-bridge fallback | `eira-fuse` � whitelist only |
| **Wine** (begr�nset) | `wine64` | Let Win32 | governance app manifest � **ikke** generel l�sning |

---

## 7. PREMIUM bundle � till�g til STANDARD

| Komponent | Type | Rolle |
|-----------|------|-------|
| **Kommerciel EDR** | CrowdStrike / MDE for Linux / SentinelOne | Kundens valg � **certificeret slot** i manifest |
| **MAAS client** | `maas-cli` / cloud-init MAAS | PXE provisioning fra Fleet |
| **Ansible AWX** | ekstern � ikke p� endpoint | governance trigger webhook |
| **Headscale** | WireGuard overlay control | valgfri moderne VPN |
| **Intune agent** | Microsoft | Dual MDM enrollment |

**PREMIUM manifest.json** felt:

```json
{
  "edr_slot": {
    "vendor": "crowdstrike",
    "package": "falcon-sensor",
    "min_version": "7.x",
    "health_probe": "systemctl is-active falcon-sensor"
  }
}
```

---

## 8. EIRA-native komponenter (altid i bundle)

| Pakke | Rolle | Erstatter OSS? |
|-------|-------|---------------|
| `eira-shell` | Explorer + Builder UI | Nej � oplevelseslag |
| `eira-identityd` | Session, Entra, step-up | Orkestrerer sssd |
| `eira-governance-agent` | Policy, compliance, fleet | Orkestrerer hele OSS-stack |
| `eira-intent-engine` | Intent parse + rationale | Nej |
| `eira-object-graphd` | SQLite objektgraf | Nej |
| `eira-hardware-agent` | fwupd inventory | Wrapper |
| `eira-legacy-runtime` | KVM/RDP orchestration | Orkestrerer libvirt/FreeRDP |
| `policy-schema` | YAML JSON Schema | Nej |

---

## 9. Policy compiler � YAML ? OSS (kontrakt)

`eira-governance-agent` kompilerer `/etc/eira/policy.yaml` til:

| Policy-n�gle | M�l-konfiguration |
|--------------|-----------------|
| `identity.entra` | `eira-identityd` + sssd |
| `vpn.profiles[]` | NetworkManager keyfiles |
| `apps.flatpak_whitelist[]` | Flatpak overrides |
| `usb.allow[]` | udev rules + governance block |
| `security.falco_rules[]` | `/etc/falco/falco_rules.local.yaml` |
| `security.apparmor_profiles[]` | `/etc/apparmor.d/` |
| `compliance.oscap_profile` | OpenSCAP job cron |
| `legacy.wine_apps[]` | ~~fjernet~~ � brug `legacy.vm_profiles[]` eller RDP |
| `legacy.vm_profiles[]` | libvirt XML templates |

---

## 10. Health probes � Fleet compliance (alle CORE)

| Komponent | Probe | Fail = |
|-----------|-------|--------|
| sssd | `systemctl is-active sssd` | red � login |
| wazuh-agent | `systemctl is-active wazuh-agent` | red � EDR |
| falco | `systemctl is-active falco` | yellow ? red efter 24h |
| osquery | `systemctl is-active osqueryd` | yellow |
| fwupd | `fwupdmgr get-updates` parse | yellow hvis kritisk firmware |
| eira-governance-agent | mTLS heartbeat | red � unmanaged |
| NetworkManager | `nmcli general` | red hvis VPN required og down |

**Fleet dashboard** aggregerer til parity_matrix (�3).

---

## 11. Reference bundle � CORE l�s (eksempel)

*Pr�cise versioner fastl�ses i `package-list.lock` per bundle � eksempel p� pakkenavne:*

```yaml
# oss-integration.yaml � CORE @ Ubuntu 24.04.2
stack_version: "1.0.0-core"

identity:
  packages: [sssd, sssd-ad, realmd, adcli, krb5-user, pcscd, opensc]

vpn:
  packages: [network-manager, network-manager-openconnect, openfortivpn, wireguard]

security:
  packages: [auditd, apparmor, apparmor-utils, clamav, clamav-daemon]
  external:
    - name: falco
      source: "https://download.falco.org/packages/deb"
    - name: wazuh-agent
      source: "https://packages.wazuh.com/4.x/apt"

inventory:
  packages: [osquery, cloud-init]

hardware:
  packages: [fwupd, fwupd-signed, cups, cups-client, sane-utils]

display:
  packages: [pipewire, pipewire-pulse, wireplumber, xdg-desktop-portal, xdg-desktop-portal-gtk, labwc]

eira:
  packages: [eira-shell, eira-identityd, eira-governance-agent, eira-intent-engine, eira-object-graphd, eira-hardware-agent]
```

---

## 12. Repositories tilladt i bundle (signeret)

| Repo | Indhold | Godkendelse |
|------|---------|-------------|
| Ubuntu Noble main/restricted/universe | Base | Canonical |
| Ubuntu Noble-security | CVE patches | Release Train |
| EIRA signed apt | `eira-*` packages | EIRA |
| Wazuh 4.x apt | wazuh-agent | EIRA QA |
| Falco official deb | falco | EIRA QA |
| osquery official deb | osquery | EIRA QA |
| Flatpak flathub (read-only subset) | Apps | governance whitelist |

**Forbudt p� managed endpoints:** vilk�rlige PPA, snapd-only apps uden policy (medmindre IT eksplicit godkender).

---

## 13. CI-krav per bundle

| Test | Krav |
|------|------|
| Fresh install fra autoinstall + bundle | Boot til Explorer < 60s |
| AD join (test domain) | sssd login OK |
| OpenConnect (test VPN) | tunnel up |
| Falco + test rule | alert i Wazuh |
| osquery inventory | Fleet modtager data |
| fwupd scan | report uden crash |
| Intent Audit ? Wazuh | korrelation ID match |
| Reference hardware matrix | 100% CORE probes green |

---

## 14. Faseopdeling vs. manifest tier

| Fase | Bundle tier | Nye OSS-komponenter |
|------|-------------|---------------------|
| Sprint 0�1 | CORE (subset) | sssd, auditd, osquery stub, OpenConnect, AppArmor |
| Pilot | CORE (fuld) | + Wazuh, Falco, fwupd agent, USG |
| Post-pilot | STANDARD | + libvirt, FreeRDP, fuse3, Lynis |
| Skalering | PREMIUM | + EDR slot, MAAS, Intune |

---

## 15. Dokumentrelation

| Dokument | Rolle |
|----------|-------|
| [Parity Architecture](EIRA_Windows_Parity_Architecture_v0.1.md) | Hvorfor disse komponenter |
| [Release Train](EIRA_Update_Release_Train_v0.1.md) | Hvordan bundles pushes |
| [Fleet Agent Protocol](EIRA_Fleet_Agent_Protocol_v0.1.md) | Endpoint ? Fleet kontrakt |
| Dette manifest | **Hvad** der er i bundlen |

---

*EIRA OSS Integration Manifest v0.1 � `oss_stack_version` bumpes ved hver komponent-�ndring.*
