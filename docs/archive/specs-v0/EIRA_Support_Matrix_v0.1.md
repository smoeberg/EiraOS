# EIRA Support Matrix v0.1

**Status:** Normativ — pilot / reference-PC  
**Dato:** 4. juli 2026  
**Formål:** Én godkendt hardware-profil, klar L0/L1/L2-eskalering, kendte begrænsninger — til IT-review og Fase 0 gate  
**Relateret:**
- [EIRA_Strategic_Reality_Check_v0.1.md](EIRA_Strategic_Reality_Check_v0.1.md)
- [EIRA_Windows_Technical_Parity_v0.1.md](EIRA_Windows_Technical_Parity_v0.1.md) §1, §8
- [EIRA_Ubuntu_Integration_v0.1.md](EIRA_Ubuntu_Integration_v0.1.md) §1
- [EIRA_Platform_Principles_v1.0.md](EIRA_Platform_Principles_v1.0.md)
- [EIRA_Pilot_Validation_Plan_v0.1.md](EIRA_Pilot_Validation_Plan_v0.1.md)
- [EIRA_BCP_Endpoint_Fallback_v0.1.md](EIRA_BCP_Endpoint_Fallback_v0.1.md)

> **v0.1 = én reference-PC.** Bred hardware-katalog (`v1.0`) kommer efter succesfuld pilot.

---

## 1. Reference-PC (EIRA Certified — pilot)

| Felt | Værdi |
|------|-------|
| **Model** | Lenovo ThinkPad T14 Gen 5 (AMD) — *eller* Dell Latitude 5450 |
| **Certificering** | Ubuntu 24.04 LTS Certified |
| **CPU / RAM** | AMD Ryzen 7 PRO / 16 GB (minimum) |
| **Storage** | 512 GB NVMe, **btrfs** (snapshot til bundle rollback) |
| **Firmware** | UEFI + Secure Boot enabled; **fwupd** / LVFS |
| **GPU** | Integreret AMD — **Mesa** (ingen proprietær driver nødvendig) |
| **Wi-Fi** | In-tree `iwlwifi` / `mt76` — verificér mod konkret SKU |
| **Docking** | USB-C dock med DisplayPort Alt Mode — 1× 4K + laptop-skærm testet |
| **BIOS** | Opdateret via LVFS før pilot-start |

**Bundle-baseline:** `EIRA 2.4 @ Ubuntu 24.04.2` — se [OSS Integration Manifest](EIRA_OSS_Integration_Manifest_v0.1.md).

---

## 2. Periferi — testet på reference-PC

| Kategori | Enhed / protokol | Status | Noter |
|----------|------------------|--------|-------|
| **Print** | IPP Everywhere / CUPS | ✅ Godkendt | Foretrukket — ingen proprietær driver |
| **Print** | HP LaserJet (HPLIP) | ⚠️ Test før rollout | Kun hvis IPP ikke tilgængelig |
| **Scanner** | eSCL / AirScan (SANE) | ✅ Godkendt | Network scanner |
| **Smartcard** | MitID Erhverv (pcscd + OpenSC) | ✅ Pilot-krav | PKCS#11 via Identity Bridge |
| **USB** | Standard HID, storage | ✅ Godkendt | Policy kan begrænse via governance |
| **Webcam** | Integreret / USB UVC | ✅ Godkendt | PipeWire + portal til møder |
| **Audio** | PipeWire default | ✅ Godkendt | Teams/Zoom via browser eller Flatpak |
| **Biometri** | fprintd (hvis hardware) | ⚠️ Valgfri | Ikke pilot-krav |
| **Signaturpude** | — | ❌ Ikke godkendt v0.1 | Kræver vendor-driver — hybrid eller undgå |
| **Proprietær NIC** | — | ❌ Ikke godkendt | Kun standard Ethernet/Wi-Fi |

**Regel:** Hvis enhed ikke står som ✅ — **test før pilot** eller udelad fra pilot-afdeling.

---

## 3. Software-profil (pilot-bruger)

| Komponent | Version / kanal | Support-lag |
|-----------|-----------------|-------------|
| **eira-shell** (Explorer) | Bundle `stable` | L1 EIRA |
| **Entra OIDC** | `eira-identityd` | L1 EIRA |
| **NetworkManager + OpenConnect** | Ubuntu LTS + bundle pin | L0 → L2 ved policy-konflikt |
| **Wazuh + Falco + EDR** | OSS CORE + valgfri partner jf. [EDR Requirements](EIRA_EDR_Partner_Requirements_v0.1.md) | L0 vendor/Wazuh / L1 EIRA triage |
| **Microsoft Teams** | Browser (Edge/Chromium Flatpak) | L0 browser / L1 EIRA policy |
| **M365** | Web + reference-adapter | L1 EIRA adapter |

---

## 4. Support-eskalering (L0 / L1 / L2)

| Lag | Dækker | Første linje | Eksempler |
|-----|--------|--------------|-----------|
| **L0 — Platform (Ubuntu/OSS)** | Kernel, CUPS, driver, VPN-klient, fwupd, NM | Kunde Ubuntu Pro / Canonical **eller** kommunal Linux-drift | "Printer driver mangler", "Wi-Fi drop", "OpenConnect fejl" |
| **L1 — EIRA Platform** | Policy, Intent, Identity, Explorer, adaptere, governance-agent | **EIRA Enterprise Support** (Premium SLA) | "MitID step-up blokerer", "Adapter timeout", "Policy push fejler" |
| **L2 — Gråzone** | Root-cause på tværs | EIRA L1 triagerer → engineering eller L0 | "Printer virker i Ubuntu test page, men ikke fra EIRA" |

### Eskaleringsregler

1. **EIRA ejer ikke CUPS/driver-debug** — men ejer at afgøre om **EIRA print-policy** blokerer.  
2. **EIRA ejer ikke VPN-gateway** — men ejer **VPN-profil push** og dokumenteret matrix.  
3. Alle sager logges med: `device_id`, `bundle_version`, `parity_point` (1–8), `intent_audit_id` (hvis relevant).  
4. P1 SLA (pilot): respons 4t arbejdstid; P2: 1 arbejdsdag.

### Tilbudsmodeller

| Model | Beskrivelse | Anbefaling |
|-------|-------------|------------|
| **A** | Kunde ejer Ubuntu Pro; EIRA dækker L1 | Større kommuner med Linux-drift |
| **B** | Bundtet: EIRA PC inkl. Ubuntu Pro + EIRA Premium — én faktura | **Pilot (anbefalet)** |
| **C** | Managed via EIRA-partner | SMB / kommuner uden Linux-kompetence |

---

## 5. Kendte begrænsninger (v0.1)

| Område | Begrænsning | Workaround |
|--------|-------------|------------|
| **Display** | XWayland-apps: skærmoptagelse kan fejle | Whitelist; test per app |
| **FUSE / Legacy Bridge** | I/O-overhead ved tung fil-dialog | Builder Mode (rå POSIX) eller VM |
| **Win32 / VBA** | Ikke native | Legacy session / hybrid PC |
| **GPO** | Ingen 1:1 GPO | EIRA YAML policy |
| **Pre-login VPN** | Afhænger af VPN-klient — se VPN matrix | Test før commit |
| **Signaturpude** | Ingen driver v0.1 | Hybrid arbejdsstation |

---

## 6. Fase 0 acceptkriterier (reference-PC)

Alle skal være **grønne** før IT-chef skriver under på paritet for pilot-profil:

| # | Test | Metode |
|---|------|--------|
| 1 | Entra login + session | Manuel + Intent Audit event |
| 2 | MitID Erhverv step-up | Blokér → step-up → confirm |
| 3 | Print til IPP-printer | Testside + dokument fra Explorer |
| 4 | VPN forbundet (Always On) | Se [VPN Compatibility Matrix](EIRA_VPN_Compatibility_Matrix_v0.1.md) |
| 5 | Smartcard læst | `pcsc_scan` + Identity session |
| 6 | Fleet enroll + heartbeat | Portal viser enhed online |
| 7 | Bundle version rapporteret | governance-agent compliance |
| 8 | Wazuh / SIEM event modtaget | Intent Audit CEF + Falco alert |
| 9 | Docking 1× 4K | Hot-desk test |
| 10 | Reboot efter bundle apply | Health check grøn |

---

## 7. Fleet inventory-felter (minimum)

```json
{
  "device_id": "uuid",
  "hardware_model": "ThinkPad T14 Gen 5",
  "ubuntu_version": "24.04.2",
  "eira_bundle": "2026.07.04-stable",
  "parity_matrix": {
    "drivers": "green",
    "display": "green",
    "vpn": "yellow",
    "edr": "green"
  },
  "support_tier": "B",
  "certified": true
}
```

---

## 8. Vej til v1.0

| Milestone | Indhold |
|-----------|---------|
| **v0.1** (nu) | Én reference-PC + periferi-test + eskalering |
| **v0.2** | + VPN matrix godkendt for pilot-kommune |
| **v1.0** | 3–5 PC-modeller; printerliste; scannerliste; signaturpude hvis krævet |

---

## 9. Salg til IT-chef (30 sekunder)

> *"Pilot kører kun på godkendt reference-hardware. Ubuntu ejer drivere — EIRA ejer politik, support-triage og certificering. Hvis en enhed ikke er på matrixen, beholder I legacy-endpoint på den arbejdsstation."*

---

*EIRA Support Matrix v0.1 — opdater når reference-PC hardware eller VPN matrix ændres.*
