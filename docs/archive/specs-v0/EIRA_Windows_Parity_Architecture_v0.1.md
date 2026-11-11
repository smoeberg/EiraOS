# EIRA OS � Windows-paritet: integrationsarkitektur v0.1

**Status:** Arkitektur � normativ retning  
**Dato:** 26. juni 2026  
**Filosofi:** Vi skal **matche Windows p� alle enterprise-punkter** � ikke acceptere permanent underlegenhed  
**Metode:** Samme som printere og VPN: **Ubuntu + moden open source + EIRA orkestrering**  
**Relateret:** [EIRA_Platform_Principles_v1.0.md](EIRA_Platform_Principles_v1.0.md), [EIRA_Windows_Technical_Parity_v0.1.md](EIRA_Windows_Technical_Parity_v0.1.md) (gap-input), [EIRA_Strategic_Reality_Check_v0.1.md](EIRA_Strategic_Reality_Check_v0.1.md) (hybrid vs. paritet)

---

## 1. Arkitektonisk princip

> **EIRA genopfinder ikke Windows. EIRA integrerer Linux-�kosystemets svar p� Windows � og orkestrerer dem til �n IT-oplevelse.**

Det er **samme m�nster** som:

| Windows | EIRA tilgang |
|---------|--------------|
| Printer-driver (HP) | CUPS + producent-driver � EIRA styrer politik |
| VPN-klient | NetworkManager + OpenConnect/WireGuard � EIRA udruller profil |
| Windows Update | Ubuntu LTS + EIRA bundles � EIRA styrer release train |
| Intune | Fleet Control + integrerede OSS-komponenter � EIRA er kontrolplanet |

**Nordstjerne:** IT-chefen skal kunne sige *"EIRA PC'en kan det samme som Windows PC'en i vores milj�"* � med samme Entra, samme SIEM, samme udrulningsmodel.

---

## 2. Integrationsmodel (gentaget for alle 8 punkter)

```
???????????????????????????????????????????????????????????????
?  EIRA Fleet Control + Portal     ? IT's ene rude (Intune-paritet) ?
???????????????????????????????????????????????????????????????
?  eira-governance-agent           ? policy push, compliance, audit  ?
???????????????????????????????????????????????????????????????
?  EIRA Platform (Intent, Identity, Explorer, Object Graph)   ?
???????????????????????????????????????????????????????????????
?  INTEGRATIONSLAG � moden OSS / certificeret 3. part         ?
?  (sssd, MAAS, Wazuh, Falco, OpenConnect, KVM, osquery�)   ?
???????????????????????????????????????????????????????????????
?  Ubuntu LTS + linux-firmware + kernel                       ?
???????????????????????????????????????????????????????????????
```

**EIRA bygger:** orkestrering, policy-kompilering, Intent Audit, brugeroplevelse.  
**EIRA integrerer:** alt der allerede findes og er battle-tested p� Linux.

---

## 3. De 8 punkter � Windows-funktion ? Linux-stack ? EIRA-lag

### 3.1 Drivere og hardware (Plug-and-Play-paritet)

| Windows | Integr�r (OSS / etableret) | EIRA-lag |
|---------|---------------------------|----------|
| Windows Update drivers | **linux-firmware**, **fwupd**, **LVFS** | `eira-hardware-agent` ? Fleet inventory |
| Plug-and-play | **udev**, **modprobe**, kernel in-tree | Auto-probe ved f�rste boot |
| Printere | **CUPS**, **IPP Everywhere**, Gutenprint, HPLIP | Print-politik via governance |
| Scannere | **SANE**, **escl** (AirScan) | Whitelist i app-policy |
| Smartcard / MitID | **pcscd**, **OpenSC**, PKCS#11 | Identity Bridge bruger dem |
| Biometri | **libfprint**, **fprintd** | Login via Identity |
| GPU | **Mesa**, NVIDIA/AMD officielle drivere | Ingen EIRA-indblanding |
| Hardware-certificering | **Ubuntu Certified**, **Canonical OEM** | **EIRA Certified PC**-program (reference-liste) |

**Paritetsm�l:** Reference-PC med fuld fwupd/LVFS-pipeline; Fleet viser driver/firmware-status per enhed som Intune hardware inventory.

**EIRA bygger ikke:** drivere. **EIRA certificerer** hardware-kombinationer og eksponerer status til IT.

---

### 3.2 Active Directory og Group Policy (GPO-paritet)

| Windows | Integr�r (OSS / etableret) | EIRA-lag |
|---------|---------------------------|----------|
| AD join | **sssd**, **realmd**, **adcli**, **krb5** | Identity IdP-connector |
| GPO (begr�nset p� Linux) | **Samba gpupdate**, SSSD GPO extensions | **Policy compiler** (YAML ? OS) |
| Entra / hybrid | **Microsoft Entra OIDC**, **Intune for Linux** | `eira-identityd` |
| Compliance scan | **OpenSCAP**, **Ubuntu Security Guide (USG)** | Compliance Engine (Lag 0) |
| Konfiguration i skala | **Ansible** / **AWX** (valgfri enterprise) | Governance agent kan trigge playbooks |
| State visibility | **osquery** + **FleetDM** (Kolide, OSS-kernen) | Fleet compliance probes |
| Central policy store | EIRA YAML (git-venlig) | Erstatter GPO for **EIRA-styrede** endpoints |

**Paritetsm�l (faser):**

| Fase | M�l |
|------|-----|
| **1** | AD-join + Entra SSO = Windows-paritet for login |
| **2** | EIRA YAML policy d�kker 80% af typiske GPO (USB, apps, VPN, firewall, step-up) |
| **3** | **GPO-translator** (l�s udvalgte AD GPO ? kompiler til EIRA policy) for mixed fleet |
| **4** | Fuld Intune Linux enrollment hvor kunden allerede bruger Intune |

**EIRA bygger:** policy compiler + governance-agent. **EIRA integrerer:** sssd, OpenSCAP, osquery, Intune API.

---

### 3.3 FUSE / I/O og legacy filadgang

| Windows | Integr�r (OSS / etableret) | EIRA-lag |
|---------|---------------------------|----------|
| NTFS kernel I/O | **ext4/btrfs** direkte i Builder; adapter-API i Explorer | Ingen FUSE i hot path |
| Fil-dialoger | **xdg-desktop-portal**, **GTK/Qt portals** | Legacy Bridge v2 (portal-first) |
| N�r FUSE n�dvendigt | **fuse3**, **libfuse** | `eira-fuse` � kun whitelisted apps |
| H�j I/O legacy | **KVM + virtio-fs** eller r� POSIX i Builder | Performance path uden FUSE |
| Async I/O | **io_uring** (kernel) | Fremtidig optimering i adapter-lag |

**Paritetsm�l:** Almindelig kontorbrug = **ingen m�lbar forskel**. Tung I/O = **Builder** eller **Legacy Runtime** (VM), ikke FUSE.

**Arkitektbeslutning:** FUSE er **fallback** � portal og direkte adapter-API er **prim�r**.

---

### 3.4 Endpoint Security og EDR (sikkerheds-paritet)

| Windows | Integr�r (OSS / etableret) | EIRA-lag |
|---------|---------------------------|----------|
| ETW / kernel callbacks | **eBPF**: **Falco**, **Tetragon** (Cilium) | EIRA genererer Falco-regler fra policy |
| Audit trail | **auditd**, **audispd-plugins** | Intent Audit + auditd korrelation |
| SIEM / HIDS | **Wazuh** (fuld OSS stack) | Native integration � CEF/syslog |
| Inventory + compliance | **osquery** + **FleetDM** | Fleet agent udvider osquery |
| MAC | **AppArmor** (Ubuntu default) | EIRA-profiler for `eira-*` |
| Antivirus (baseline) | **ClamAV** + **clamd** | Policy: scan ved download |
| Kommerciel EDR (krav) | **CrowdStrike**, **MDE for Linux**, SentinelOne | **Certificeret partner-lag** � agent som del af EIRA bundle |
| Svagheds-scan | **OpenSCAP**, **Lynis** | Compliance Engine |

**Paritetsm�l:** Samme SIEM som Windows � **plus** Intent Audit som Windows ikke har. EDR-dybde via **Falco/eBPF + Wazuh + kommerciel agent** � ikke kun Intent Audit alene.

```
Endpoint event flow:
  Falco / auditd / EDR agent / Intent Audit
              ?
         Wazuh (eller kundens SIEM)
              ?
         Fleet Control dashboard
```

---

### 3.5 Win32 / backward compatibility

| Windows | Integr�r (OSS / etableret) | EIRA-lag |
|---------|---------------------------|----------|
| Win32 in-process | **Wine** / **Proton** (let compat � begr�nset) | Whitelist kun simple apps |
| Fuld Win32 + COM + drivers | **KVM**, **QEMU**, **libvirt** | **EIRA Legacy Runtime** (managed VM) |
| Fjernadgang til Windows | **FreeRDP**, **Windows 365**, **AVD** | Explorer: "�bn legacy app" ? session |
| Containeriseret legacy | **Distrobox** / **Toolbox** (Fedora-m�nster) | Builder / avanceret |

**Paritetsm�l:** Brugeren trykker **[�bn]** i Explorer � systemet v�lger **adapter ? Linux app ? VM/RDP** automatisk. Brugeren ser ikke Windows.

**Arkitektur (Crostini-model for enterprise):**

```
Explorer intention: "�bn Budget.xlsm"
        ?
Capability: kr�ver Win32/VBA
        ?
EIRA Legacy Runtime (KVM slice) ELLER RDS/Windows 365
        ?
Resultat tilbage i EIRA (ikke separat Windows desktop)
```

**Langsigt:** Paritet = **managed runtime**, ikke perfekt WINE.

---

### 3.6 Enterprise VPN og netv�rk

| Windows | Integr�r (OSS / etableret) | EIRA-lag |
|---------|---------------------------|----------|
| Cisco AnyConnect | **OpenConnect** (OSS, protokol-kompatibel) | VPN-profil via governance |
| Fortinet | **openfortivpn** | Samme |
| Palo Alto GlobalProtect | **OpenConnect** (delvis) / vendor Linux-klient hvor p�kr�vet | Compatibility matrix |
| IPsec | **strongSwan**, **libreswan** | Central profil |
| Moderne VPN | **WireGuard** + **Headscale** (OSS Tailscale-kontrol) | Foretrukket for nye udrulninger |
| Always On | **NetworkManager** + **systemd** (`network-online.target`) | Pre-login via **systemd unit** + NM |
| NDIS | N/A p� Linux | NetworkManager er standard |

**Paritetsm�l:** Kommunens eksisterende VPN **virker p� Ubuntu** via OpenConnect/openfortivpn � dokumenteret i VPN Compatibility Matrix. Pre-login tunnel via systemd � **ikke** accepteret som "umuligt".

---

### 3.7 Systems Management og Imaging (Intune/SCCM-paritet)

| Windows | Integr�r (OSS / etableret) | EIRA-lag |
|---------|---------------------------|----------|
| PXE / bare metal | **Canonical MAAS** | Fleet trigger MAAS deploy |
| Golden image | **Ubuntu Autoinstall** (subiquity) + **cloud-init** | EIRA bundle baked in |
| Konfig management | **Foreman** + **Katello** (valgfri) | API-integration |
| OTA / staged rollout | **Mender** (eller EIRA bundles) | Release Train |
| MDM (Microsoft-milj�) | **Microsoft Intune** Linux management | Dual enrollment mulig |
| Inventory | **osquery** + **FleetDM** | Fleet agent |
| Remote wipe | **cryptsetup**, **sedutil** (Opal), **NVMe secure erase** | Governance remote command |
| Software inventory | **dpkg** + **Flatpak** + osquery | Fleet dashboard |

**Paritetsm�l:**

```
IT workflow (paritet med Autopilot):
  1. Bestil EIRA Certified PC
  2. MAAS/cloud-init installerer Ubuntu + EIRA bundle
  3. Enhed auto-enroller i Fleet Control
  4. Policies push via governance-agent
  5. Compliance synlig i Portal � som Intune
```

**EIRA Fleet Control** er kontrolplanet � **MAAS + cloud-init + osquery** er motorerne under.

---

### 3.8 Display Server (grafisk stabilitet)

| Windows | Integr�r (OSS / etableret) | EIRA-lag |
|---------|---------------------------|----------|
| DWM (lukket stack) | **Wayland** + minimal compositor (**labwc** / **cage**) | eira-shell fullscreen |
| Legacy X11 | **XWayland** | Whitelisted apps |
| Sk�rmoptagelse | **PipeWire** + **xdg-desktop-portal** | Explorer screen share |
| Input / genveje | Wayland protocols (udvikles) | EIRA global shortcuts via compositor config |
| GPU acceleration | **Mesa**, vendor drivers | Standard Ubuntu |

**Paritetsm�l:** Explorer = �n stabil Wayland-session. Legacy = XWayland isoleret. **Ingen custom compositor fra bunden.**

---

## 4. Samlet OSS-integrationsstack (reference)

Komponenter EIRA **skal** integrere � ikke erstatte:

| Kategori | Projekter | Prioritet |
|----------|-----------|-----------|
| **Identity / AD** | sssd, realmd, adcli, Entra OIDC | P0 |
| **Policy / compliance** | AppArmor, OpenSCAP, USG, auditd | P0 |
| **Fleet / inventory** | osquery, FleetDM, cloud-init | P0 |
| **SIEM / sikkerhed** | Wazuh, Falco, ClamAV | P0 |
| **VPN** | OpenConnect, openfortivpn, WireGuard, NetworkManager | P0 |
| **Provisioning** | MAAS eller Autoinstall, fwupd | P0 |
| **Legacy runtime** | KVM/libvirt, FreeRDP, Wine (begr�nset) | P1 |
| **Config scale** | Ansible AWX (enterprise option) | P2 |
| **Intune coexist** | Microsoft Intune Linux API | P2 |
| **GPO translator** | Samba GPO extensions ? EIRA policy | P3 |

---

## 5. Hvad EIRA selv bygger (minimalt)

| Komponent | Hvorfor ikke kun OSS |
|-----------|---------------------|
| **eira-governance-agent** | Samler alle OSS-agenter til �t endpoint-interface |
| **Fleet Control / Portal** | Intune-lignende UX for hele stacken |
| **Policy compiler** | YAML ? AppArmor + NM + systemd + Flatpak + step-up |
| **Intent Audit** | Unik � findes ikke i Windows |
| **eira-shell (Explorer)** | Oplevelseslaget � produktets kerne |
| **Legacy Runtime orchestrator** | Seamless VM/RDP fra Explorer |
| **EIRA OS Bundle** | Signeret Ubuntu + EIRA + certificerede OSS-agenter |

---

## 6. Paritets-roadmap (arkitekt-faser)

| Fase | Horisont | Leverance |
|------|----------|-----------|
| **P0** | Sprint 0�2 | sssd/Entra, governance-agent, Wazuh+Falco stub, OpenConnect, cloud-init image, osquery |
| **P1** | Pilot | Fleet MVP, fwupd inventory, VPN matrix godkendt, Legacy Runtime alpha |
| **P2** | Post-pilot | Intune dual-enroll, OpenSCAP compliance reports, MAAS integration |
| **P3** | Skalering | GPO-translator, Ansible AWX connector, fuld Legacy Runtime |

**M�ling:** Per punkt (1�8) � **gr�n / gul / r�d** i Fleet dashboard. M�l: **alt gr�nt** inden national skalering.

---

## 7. Relation til tidligere "�rlig gap"-doc

[EIRA_Windows_Technical_Parity_v0.1.md](EIRA_Windows_Technical_Parity_v0.1.md) beskriver **hvor Windows st�r i dag**.  
**Dette dokument** beskriver **hvordan vi matcher det** � via integration, ikke accept.

[EIRA_Strategic_Reality_Check_v0.1.md](EIRA_Strategic_Reality_Check_v0.1.md) afklarer **hybrid-fase vs. paritetsmål** — læs den før salg og arkitektur-beslutninger.


Hybrid-flåde er en **overgangsfase** i udrulning — teknisk korrekt strategi i fase 0–2 (se [Reality Check](EIRA_Strategic_Reality_Check_v0.1.md) §2); paritet er integrationsmålet på længere sigt.

---

## 8. �n s�tning til arkitekten

> **Windows har 30 �rs integration. Linux har modne komponenter til det meste. EIRA's job er at samle dem til �n enterprise-platform � pr�cis som vi samler Public360 og SharePoint for brugeren.**

---

## Relaterede dokumenter (operationalisering)

| Spørgsmål | Dokument |
|-----------|----------|
| Ærlige gaps (kunde) | [Windows Technical Parity](EIRA_Windows_Technical_Parity_v0.1.md) |
| Hybrid fase 0–2 | [Strategic Reality Check](EIRA_Strategic_Reality_Check_v0.1.md) |
| Kunde-roadmap | [Enterprise Endpoint Transition](../../company/EIRA_Enterprise_Endpoint_Transition_v1.0.md) |
| Pilot-test | [Pilot Validation Plan](EIRA_Pilot_Validation_Plan_v0.1.md) |
| Navigation | [Document Map](../EIRA_Document_Map_v0.1.md) |

---

*EIRA Windows-paritet � integrationsarkitektur v0.1*