# EIRA OS � Windows teknisk paritet (�rlig vurdering) v0.1

**Status:** Normativ � salg, IT, arkitektur  
**Dato:** 26. juni 2026  
**Form�l:** Dokumentere hvor Windows er **teknisk st�rkere** end EIRA OS � uden UX, uden marketing  
**Relateret:** [EIRA_Platform_Principles_v1.0.md](EIRA_Platform_Principles_v1.0.md), [EIRA_Ubuntu_Integration_v0.1.md](EIRA_Ubuntu_Integration_v0.1.md), [EIRA_Enterprise_IT_Requirements_v0.1.md](EIRA_Enterprise_IT_Requirements_v0.1.md)

---

## Det vi siger h�jt

> **Windows vinder p� modenhed, bredde og inerti � ikke p� bedre arkitektur.**

EIRA bygger oven p� Ubuntu og **arver Ubuntus tekniske begr�nsninger** i forhold til Windows-�kosystemet. Vi foregiver ikke paritet. Vi dokumenterer gaps og kompenserer hvor det er realistisk.

**Hybrid-fl�de er ikke en undskyldning � det er den teknisk korrekte strategi.**

---

## Oversigt

| # | Omr�de | Windows | EIRA | EIRA-kompensation | Pilot-impact |
|---|--------|---------|------|-------------------|--------------|
| 1 | Drivere / hardware | WDM/WDF, Windows Update | Ubuntu kernel + community/OEM | Support Matrix, reference-PC | Medium |
| 2 | AD / GPO | Dyb GPO til registry, UI, services | SSSD/realmd � login, begr�nset GPO | Governance Agent + YAML policy | H�j |
| 3 | FUSE / I/O legacy | NTFS kernel-mode | eira-fuse user-space overhead | Legacy Bridge kun ved behov; Builder = r� POSIX | Lav�medium |
| 4 | EDR | ETW, kernel hooks, modent | eBPF, auditd, AppArmor � anderledes | EDR-partner + Intent Audit ? SIEM | H�j |
| 5 | Win32 / backward compat | 20+ �rs Win32/COM/ActiveX | POSIX; WINE/VM for Windows-only | Whitelist; VM break-glass; hybrid | H�j |
| 6 | Enterprise VPN | NDIS, pre-login, Always On | NetworkManager, WireGuard/OpenVPN | VPN policy matrix; test f�r pilot | H�j |
| 7 | Imaging / MDM | Intune/SCCM, PXE, deep inventory | Fleet Control (bygges); Foreman/custom | EIRA bundles + governance-agent | Kritisk |
| 8 | Display / Wayland | DWM, uniform | Wayland + XWayland transition | Chrome-shell; legacy i XWayland/Builder | Medium |

---

## 1. Driver- og hardwareunderst�ttelse (Plug-and-Play Gap)

### Windows

- Universal drivermodel (WDM/WDF)
- OEM skriver Windows-drivere f�rst
- Windows Update leverer drivere centralt

### EIRA (Ubuntu)

- Standard hardware (USB, netv�rk, moderne GPU): **glimrende**
- Niche enterprise: biometri, signaturpuder, �ldre printere, proprietary NIC � **ofte manglende Linux-driver**
- EIRA kan **ikke** bygge manglende drivere

### EIRA's svar (allerede i Platform Principles)

| Handling | Dokument |
|----------|----------|
| Ubuntu ejer drivere � EIRA ejer **politik** | Platform Principles �1�2 |
| Support Matrix med godkendt reference-hardware | [Support Matrix v0.1](EIRA_Support_Matrix_v0.1.md) (pilot); v1.0 efter bred hardware |
| Niveau 1 driver-debug ? Ubuntu/Canonical | Platform Principles support-model |

### Pilot-krav

- **Kun godkendt hardware** i fase 1 � ingen "bring your own PC"
- IT tester periferi **f�r** rollout (printer, smartcard, scanner)

### Salg til IT-chef

> *"EIRA �ndrer ikke jeres printerstak. Hvis Ubuntu LTS underst�tter enheden, underst�tter EIRA den. Hvis ikke � beholder I Windows p� den arbejdsstation."*

---

## 2. Active Directory og Group Policy (GPO-paritet)

### Windows

- Native AD + GPO: registry, filrettigheder, services, firewall, UI � centralt og granul�rt

### EIRA (Ubuntu)

- `sssd` + `realmd`: **autentificering** og basis AD-join
- Linux er **ikke** GPO-native � SSSD tolker kun udvalgte GPO'er
- IT kan **ikke** presse vilk�rlige OS-indstillinger ud via standard GPO

### EIRA's svar

| Mekanisme | Rolle |
|-----------|-------|
| **eira-governance-agent** | EIRA's GPO-�kvivalent � YAML policy push |
| **Fleet Control / Portal** | Intune-lignende administration |
| **Entra ID** | Samme identitet som Windows-fl�den (hybrid) |

**Vigtigt:** IT administrerer EIRA **anderledes** end Windows � via EIRA policies, ikke GPO. Begge kan v�re i samme AD/Entra.

### Gap

- Ingen 1:1 GPO-import � IT skal l�re EIRA policy-sprog
- Se [Enterprise IT Requirements](EIRA_Enterprise_IT_Requirements_v0.1.md) �7 (policy som kode)

### Pilot-krav

- Dedikeret test-OU med EIRA YAML policies � **spejl ikke GPO forventning**
- IT-tr�ning: "EIRA policy ? GPO"

---

## 3. FUSE-overhead og I/O for legacy apps

### Windows

- NTFS og fil-kald i kernel-mode � lav latenje ved massiv I/O

### EIRA

- **Legacy Filesystem Bridge** (`eira-fuse`) mapper Object Graph ? virtuel mappe
- FUSE: context switch kernel ? user-space **per filoperation**
- Tung lokal DB-klient eller massiv disk-I/O: **m�lbar overhead** vs. r� NTFS

### EIRA's svar

| Strategi | Hvorn�r |
|----------|---------|
| Explorer uden legacy fil-dialog | Standard � ingen FUSE i hot path |
| Legacy Bridge (FUSE) | Kun whitelisted apps der kr�ver "Gem som" |
| **Builder Mode** | R� `/home` � ingen FUSE |
| Undg� tunge legacy apps i Explorer | Pilot-selektion |

### Arkitekturbeslutning

> FUSE er **kompatibilitetslag** � ikke performance-path. Tunge Windows-only eller I/O-tunge apps h�rer til **Windows eller Builder/VM** � ikke Explorer.

Se [Paradigm Bridging Analysis](EIRA_Paradigm_Bridging_Analysis_v0.1.md) �5.A.

---

## 4. Endpoint Security og EDR-integration

### Windows

- CrowdStrike, MDE, SentinelOne: dybe kernel hooks (ETW, callbacks)
- Realtid: proces, netv�rk, DLL injection � modent �kosystem

### EIRA (Ubuntu)

- Linux-EDR findes (CrowdStrike for Linux, m.fl.) � **anderledes** mekanisme (eBPF, `auditd`, AppArmor)
- Agenter ofte **mindre funktionelle** eller kr�ver anden konfiguration
- Intent Audit + AppArmor **supplerer** � erstatter ikke EDR-dybde p� Windows

### EIRA's svar

| Lag | Funktion |
|-----|----------|
| **Kommerciel EDR** (partner � P0 beslutning) | Malware, IOC, standard IT-krav |
| **Intent Audit** | Intention + rationale � **unik** vs. Windows |
| **AppArmor** | Hard ceiling for EIRA-daemons |
| **CEF/syslog ? SIEM** | Samlet visning med Windows-fl�de |

### Gap

- EDR-partner **ikke valgt endnu** — se [EDR Partner Requirements](EIRA_EDR_Partner_Requirements_v0.1.md) � blokerer mange enterprise-indk�b
- SIEM-korrelation EIRA + Windows = mere kompleks end ren Windows

### Pilot-krav

- �n godkendt EDR med **dokumenteret Linux-agent** p� reference-hardware
- Intent Audit events i samme SIEM som Windows-endpoints

---

## 5. Backward compatibility (Win32 vs. POSIX)

### Windows

- Win32/COM/ActiveX: 20+ �rs bagudkompatibilitet p� Windows 11

### EIRA

- POSIX + Linux-native
- Windows-only legacy: **WINE** (ufuldst�ndig) eller **VM** (fungerer, men ikke "EIRA-oplevelse")
- Apps med egen Windows-driver-DLL + hardware: **fejler** p� EIRA

### EIRA's svar

| Tilgang | Anvendelse |
|---------|------------|
| **Hybrid-fl�de** | Makro-tung Excel, Access, Win32-only � Windows PC |
| **App whitelist** (Governance) | Kun godkendte Linux/Flatpak apps |
| **VM break-glass** (Builder/IT) | Sidste udvej � ikke standardbruger |
| **EIRA adaptere** | Erstat manuel Win32-app med intention over API |

### Vi lover ikke

- WINE som generel Win32-l�sning
- COM/ActiveX i Explorer

---

## 6. Enterprise VPN og netv�rkssikkerhed

### Windows

- NDIS, Cisco AnyConnect, GlobalProtect, FortiClient
- Always On VPN, **pre-login machine tunnel**

### EIRA (Ubuntu)

- NetworkManager + WireGuard/OpenVPN/StrongSwan � **st�rkt** for �bne standarder
- Propriet�re VPN-klienter: ofte **ustabile** eller mangler pre-login p� Linux
- Klassisk enterprise-blocker for Linux-desktop

### EIRA's svar

| Handling | Status |
|----------|--------|
| WireGuard/OpenVPN som **foretrukken** strategi | Platform Principles |
| Central VPN-konfiguration via Governance | Fleet policy |
| **VPN Compatibility Matrix** (hvilken klient, hvilken funktion) | **Skal skrives** � P0 for pilot |
| Pre-login tunnel | Ofte **ikke** muligt med propriet�r klient � test f�r commit |

### Pilot-krav

- Kommunens VPN **testet p� Ubuntu 24.04** f�r 50 PC
- Hvis kun GlobalProtect med pre-login: **pilot aflyses eller hybrid**

---

## 7. Systems Management og Imaging (SCCM/Intune)

### Windows

- Intune/Autopilot, SCCM, PXE, deep inventory, remote wipe � **modent**

### EIRA

- Ubuntu kan registreres i Intune � **begr�nset dybde** vs. Windows
- EIRA **bygger** Fleet Control + governance-agent + bundles
- Golden image: Foreman / custom scripting � **anden kompetence** end SCCM

### EIRA's svar

| Komponent | M�l |
|-----------|-----|
| [EIRA Fleet Control](EIRA_Fleet_Control_v0.1.md) | Intune-paritet for **EIRA-relevante** 80% |
| [Update Release Train](EIRA_Update_Release_Train_v0.1.md) | Bundles = certificeret Ubuntu + EIRA |
| [Fleet Agent Protocol](EIRA_Fleet_Agent_Protocol_v0.1.md) | Compliance, wipe, staged rollout |

### Gap (kritisk)

- Fleet Control er **design** � ikke produkt endnu
- IT siger ofte nej uden MDM-paritet ([Enterprise IT](EIRA_Enterprise_IT_Requirements_v0.1.md) �5.5)

### Pilot-krav

- Minimum Fleet MVP: enrollment, bundle version, compliance %, remote wipe
- **Ikke** fuld SCCM-paritet i fase 1 � v�re �rlig

---

## 8. Display Server (Wayland/X11)

### Windows

- DWM: lukket, uniform, hardware-accelereret, stabil

### EIRA (Ubuntu)

- Overgang X11 ? Wayland
- EIRA Explorer: **Wayland chrome-shell** (Tauri + WebKitGTK)
- Legacy apps: XWayland � mulige glitches (sk�rmoptagelse, globale genveje, nested windows)

### EIRA's svar

| Beslutning | Kilde |
|------------|-------|
| Wayland primary for Explorer | Ubuntu Integration �3 |
| XWayland for legacy whitelisted apps | Ubuntu Integration |
| Builder Mode: fuld Ubuntu desktop-adgang | UX Logic |
| Ingen custom compositor | Platform Principles � "usynligt Linux" |

### Pilot-krav

- Test whitelisted legacy apps under XWayland p� reference-PC
- Dokument�r kendte begr�nsninger i Support Matrix

---

## Positionering � hvad vi siger til kunden

### Sig ikke

> "EIRA er bedre end Windows p� alle punkter."

### Sig

> *"EIRA er bedre p� suver�nitet, samlet oplevelse og intention-audit. Windows er bedre p� driver-bredde, GPO-dybde, Win32-legacy og moden MDM. Derfor anbefaler vi hybrid-fl�de: EIRA hvor oplevelsen og audit giver v�rdi � Windows hvor teknisk legacy kr�ver det � samme Entra, samme SIEM."*

Det matcher [Enterprise IT Requirements](EIRA_Enterprise_IT_Requirements_v0.1.md) Fase 2 og [Strategic Reality Check](EIRA_Strategic_Reality_Check_v0.1.md).

---

## P0-dokumenter — status (juli 2026)

| Dokument | Status | Dækker punkt |
|----------|--------|--------------|
| [EIRA_Support_Matrix_v0.1](EIRA_Support_Matrix_v0.1.md) | ✅ Skrevet | 1, 8 (pilot) |
| [EIRA_VPN_Compatibility_Matrix_v0.1](EIRA_VPN_Compatibility_Matrix_v0.1.md) | ◐ Skabelon — udfyld ved test | 6 |
| [EIRA_Strategic_Reality_Check_v0.1](EIRA_Strategic_Reality_Check_v0.1.md) | ✅ Skrevet | Meta, R1, hybrid |
| **EIRA_EDR_Partner_Requirements_v0.1** | ✅ Skrevet | 4 — partner-beslutning uge 4 |
| [Fleet MVP Scope](../../eira-fleet-control/docs/MVP_SCOPE_v0.1.md) | ✅ I fleet-control | 7 |
| [EIRA_OSS_Operations_Model_v0.1](EIRA_OSS_Operations_Model_v0.1.md) | ✅ Skrevet | Vedligehold, CVE |
| [EIRA_Pilot_Validation_Plan_v0.1](EIRA_Pilot_Validation_Plan_v0.1.md) | ✅ Skrevet | Test, gates |
| [EIRA_BCP_Endpoint_Fallback_v0.1](EIRA_BCP_Endpoint_Fallback_v0.1.md) | ✅ Skrevet | Fallback, BCP |
| `EIRA_Support_Matrix_v1.0` | ⬜ Efter pilot | 1, 8 (bred) |

---

## Relation til andre "�rlige" dokumenter

| Dokument | Fokus |
|----------|-------|
| **Dette dokument** | Teknisk infrastruktur vs. Windows |
| [Strategic Reality Check](EIRA_Strategic_Reality_Check_v0.1.md) | Kommerciel risiko, adaptere, identity scope |
| [Enterprise IT Requirements](EIRA_Enterprise_IT_Requirements_v0.1.md) | IT-krav og hybrid-model |
| [Lineage](../EIRA_v2_0_Lineage.md) | Vision 2025 ? specs 2026 |

**Tillæg ikke i Windows-sammenligningen (men reelt):** VBA/Access-migration, vendor support-garanti, omstillingsomkostning — se [Strategic Reality Check](EIRA_Strategic_Reality_Check_v0.1.md) §8–9 og [Business Plan Sprint](../../../company/EIRA_Business_Plan_Sprint_v0.1.md) pilot-selektion.

---

*EIRA OS — Windows teknisk paritet v0.1 — opdateres når VPN matrix er testet og EDR-partner er valgt.*
