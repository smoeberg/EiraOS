# EIRA Platform Principles v1.0

**Status:** Grundl�ggende � m� aldrig brydes  
**Dato:** 26. juni 2026  
**Kategori:** Arkitektur + positionering + salg til IT

---

## Det vi aldrig m� glemme

> **Vi er dem, der g�r det muligt at skifte Windows ud med Ubuntu � uden at det f�les som en GUI fra 2000.**

EIRA erstatter ikke Linux. EIRA g�r Linux **brugbar for vidensarbejdere og administr�rbart for IT** � uden at genopfinde det, der allerede virker.

---

## Grundfejlen nye operativsystemer beg�r

> De opf�rer sig som om de er et nyt operativsystem.

**EIRA m� ikke g�re det.**

---

## Princip 1: EIRA er "det usynlige Linux"

N�r IT k�ber Windows, k�ber de ikke printerdrivere. HP, Canon og Brother skriver driverne. Windows stiller en **driver-model** til r�dighed.

**Det samme g�lder EIRA og Ubuntu.**

| Lag | Ejer | Ansvar |
|-----|------|--------|
| Hardware | OEM | PC, firmware |
| **Ubuntu LTS** | Canonical + community | Kernel, drivere, CUPS, NetworkManager, systemd, � |
| **EIRA Platform** | EIRA | Identity, Intent, Governance, Adaptere, Desktop-oplevelse |

```
Hardware
    ?
Firmware (UEFI)
    ?
Ubuntu LTS
    ?
Linux Kernel
    ?
???????????????????????????????????????????
?  Enterprise Services (Ubuntu � ikke EIRA) ?
?  CUPS � NetworkManager � systemd        ?
?  PipeWire � Samba � OpenSSH � SSSD      ?
?  Docker � Flatpak � BlueZ � pcscd       ?
?  WireGuard � OpenVPN � auditd           ?
???????????????????????????????????????????
    ?
???????????????????????????????????????????
?  EIRA Platform                          ?
?  Identity � Object Graph � Intent        ?
?  Capability � Adapters � Governance       ?
?  Explorer � Builder � Agents              ?
???????????????????????????????????????????
```

**For IT-afdelingen:**

> EIRA er ikke et nyt operativsystem.  
> **EIRA er en enterprise-platform ovenp� Ubuntu LTS.**

---

## Princip 2: EIRA erstatter aldrig moden Linux-infrastruktur � EIRA orkestrerer den

Samme filosofi som Adapter Specification:

| Eksternt | Internt (Ubuntu) |
|----------|------------------|
| EIRA erstatter ikke Public360 | EIRA erstatter ikke CUPS |
| EIRA erstatter ikke SharePoint | EIRA erstatter ikke systemd |
| EIRA erstatter ikke KMD OPUS | EIRA erstatter ikke NetworkManager |
| | EIRA erstatter ikke Docker |

**EIRA binder sammen, styrer og g�r administr�rbart.**

---

## Hvad Ubuntu leverer (EIRA r�rer det ikke)

| Omr�de | Ubuntu / Linux stack | EIRA's rolle |
|--------|---------------------|--------------|
| **Printere** | CUPS, IPP Everywhere, Gutenprint, prod.driver | Printer**politikker** (hvem m� hvor) |
| **Scannere** | SANE, TWAIN bridge | Ingen � Ubuntu |
| **Grafik** | NVIDIA, AMD, Intel drivere | Ingen � Ubuntu |
| **USB** | udev | USB-**politikker** |
| **Bluetooth** | BlueZ | Politik via Governance |
| **Smartcards** | pcscd, OpenSC, PKCS#11 | Identity Bridge bruger dem |
| **VPN** | WireGuard, OpenVPN, StrongSwan, � | Central VPN-**konfiguration** |
| **Certifikater** | OpenSSL, ca-certificates | Trust Framework orkestrerer |
| **Filsystem** | ext4, btrfs, ZFS | Kryptering**politik** |
| **Containere** | Docker, Podman, LXC | Godkendte images / Flatpak |
| **Virtualisering** | KVM, QEMU, libvirt | Builder Mode adgang |
| **Filshare** | Samba | Mount-politik |
| **Directory** | SSSD, realmd, Kerberos | Identity connector |
| **Active Directory** | realmd + SSSD | Entra/AD IdP connector |

### IT-sp�rgsm�let om printere

**Forkert svar:**  
> "Ja, EIRA underst�tter printere."

**Korrekt svar:**  
> **"Ubuntu LTS underst�tter dem. EIRA �ndrer ikke printstakken."**

- Eksisterende printerserver virker  
- Eksisterende k�er virker  
- Eksisterende Linux-drivere virker  
- **Nul printer-migration**

---

## Hvad EIRA leverer (enterprise governance)

| Ubuntu leverer | EIRA leverer |
|----------------|--------------|
| Printerdrivere | Printerpolitikker + print-compliance |
| USB (udev) | USB-politikker |
| WiFi (NetworkManager) | WiFi-profiler og udrulning |
| VPN-klienter | Central VPN-konfiguration |
| CUPS | Print-overv�gning (audit) |
| Flatpak / apt | Godkendte applikationer (whitelist) |
| systemd | Service-politik via Governance |
| apt repositories | Godkendte repos |
| auditd | **Intent Audit** + tv�rg�ende revisionsspor |
| � | Identity Bridge, step-up, delegation |
| � | Intent Engine, Adapter Layer |
| � | Explorer / Builder oplevelse |

**EIRA dokumenterer ikke hardware-kompatibilitet.**  
**EIRA dokumenterer enterprise governance ovenp� Ubuntu.**

---

## Princip 3: Gratis arv fra Ubuntu-opgraderinger

N�r Ubuntu 28.04 f�r ny printerdriver, NVIDIA-driver, WiFi eller Bluetooth-stack � **arver EIRA det gratis**.

- Ingen EIRA-udvikling  
- Ingen EIRA-QA p� drivere  
- Ingen EIRA-vedligehold af CUPS  

**Baseline:** Ubuntu LTS hardware compatibility matrix = EIRA hardware compatibility.

---

## Princip 4: Samme samtale med IT som med leverand�rer

| Sp�rgsm�l | Svar |
|-----------|------|
| "Underst�tter EIRA printer X?" | "Underst�tter **Ubuntu LTS** printer X? Hvis ja � virker den." |
| "Underst�tter EIRA VPN Y?" | "Underst�tter **Ubuntu** klient Y? EIRA udruller konfigurationen." |
| "Skal vi l�re nyt OS?" | "**Nej.** Det er Ubuntu under motorhjelmen. EIRA tilf�jer arbejdsmilj� og governance." |

### Salgsbudskab til IT-chef

> **Det er Ubuntu LTS under motorhjelmen. Alt jeres Linux-kendskab, drivere og v�rkt�jer virker stadig. EIRA tilf�jer moderne arbejdsmilj�, identitet, governance og integration � ikke en ny hardwareplatform.**

Det reducerer oplevet risiko. EIRA konkurrerer ikke med Linux-�kosystemet � det bygger ovenp�.

---

## Princip 5: Windows-udskiftning uden 2000-GUI

Ubuntu alene i kommunal drift fejler ofte fordi:

- Brugeren m�der r� desktop, terminal, mappestruktur  
- IT mangler Intune-lignende styring  
- Fagsystemer kr�ver stadig 10 login  

**EIRA l�ser oplevelse + governance � ikke kernel.**

```
Windows 11          ?  Ubuntu LTS (kernel, drivere, stabilitet)
                     + EIRA (oplevelse, intent, governance, adaptere)
```

Brugeren ser **EIRA Explorer** � ikke "Ubuntu med GNOME fra 2004".  
IT administrerer via **EIRA Enterprise Portal** � ikke kun `apt` og shell scripts.

---

## Anti-patterns (forbudt)

| ? M� aldrig ske | ? Korrekt |
|-----------------|-----------|
| EIRA skriver egen printerstack | Brug CUPS |
| EIRA forkker NetworkManager | Policy + profiles |
| EIRA genopfinder VPN-protokol | Udrul WireGuard/OpenVPN config |
| "EIRA OS er et nyt OS" i marketing | "Enterprise platform p� Ubuntu LTS" |
| Hardware-compat matrix i EIRA-docs | Henvis til Ubuntu LTS + Canonical HCL |
| Erstatte Flatpak med eget pakkeformat | Kur�r Flatpak + signerede repos |

---

## Konsekvenser for dokumentation

| Dokument | �ndring |
|----------|---------|
| Whitepaper | Ubuntu-stack diagram; fjern "EIRA OS = nyt OS" sprog |
| Enterprise IT Requirements | Hardware ? Ubuntu HCL; EIRA ? governance matrix |
| Open Architecture | EIRA Platform ? operating system |
| Salgsmateriale | "Ubuntu LTS + EIRA" ikke "skift til EIRA OS" |
| Support | Niveau 1 printer/VPN ? Ubuntu/community; Niveau 2 governance ? EIRA |

---

## Konsekvenser for produkt

| Komponent | Bygger p� |
|-----------|-----------|
| EIRA Desktop | Tauri p� Ubuntu, ikke custom display server |
| Governance agent | systemd integration, ikke egen init |
| App distribution | Flatpak primary |
| Print audit | CUPS log + EIRA Intent Audit |
| MDM-lignende | Portal policies ? `/etc/eira/` + Ubuntu tools |

**Reference platform:** Ubuntu 24.04 LTS (opgraderbar til 26.04/28.04 med EIRA QA p� platform-lag kun).

---

## �n s�tning (h�ng i kontoret)

> **Ubuntu er OS'et. EIRA er det, der g�r Ubuntu til noget, en kommune t�r rulle ud til 2.000 medarbejdere.**

---

## Relaterede dokumenter

- EIRA_Open_Architecture_v1.0.md
- EIRA_Enterprise_IT_Requirements_v0.1.md
- EIRA_OS_Architecture_Overview_v1.0.md
- EIRA Adapter Specification (ekstern filosofi � samme m�nster)

---

*EIRA Platform Principles v1.0 � Grundl�ggende � m� aldrig brydes*
