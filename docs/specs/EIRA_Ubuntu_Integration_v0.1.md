# EIRA Ubuntu Integration � Blind spots & svar v0.1

**Status:** Kritisk review � obligatorisk supplement til Platform Principles  
**Dato:** 26. juni 2026  
**Relateret:** EIRA_Platform_Principles_v1.0.md

---

## Konklusion p� den kritiske analyse

Grundtanken ("EIRA orkestrerer, erstatter ikke") er **korrekt og salgbar**. Analysen identificerer **reelle enterprise-huller** � ikke argumenter mod strategien, men **obligatorisk dokumentation** f�r IT-chef siger ja.

> Hvis EIRA ikke beskriver hvad der sker n�r ting g�r galt eller skal opdateres, er "usynligt Linux" bare et marketingord.

---

## 1. Support � "Who ya gonna call?"

### Relevans: **KRITISK** � blocker for indk�b uden klar matrix.

### Blindt punkt (bekr�ftet)

Printer virker ikke ? EIRA eller Canonical?

### EIRA's svar: Support Matrix (3 niveauer)

| Lag | Eksempel | F�rste linje | Eskalering |
|-----|----------|--------------|------------|
| **L0 Ubuntu** | CUPS, driver, kernel, VPN-klient | Kunde Ubuntu Pro / Canonical / intern Linux-drft | Community + LTS support |
| **L1 EIRA Platform** | Policy, Intent, adapter, Identity, Explorer | EIRA Support (Premium SLA) | EIRA engineering |
| **L2 Gr�zone** | "Printer virker i Ubuntu test page, men ikke fra EIRA" | EIRA L1 triagerer | Root-cause: CUPS config vs EIRA print-policy |

**Regel:** EIRA support **ejer ikke** CUPS/driver-debugging. EIRA support **ejer** at afg�re om EIRA-policy blokerer.

### Tilbudsmodeller

| Model | Beskrivelse |
|-------|-------------|
| **A � Kunde ejer Ubuntu** | Kommune har Ubuntu Pro; EIRA Enterprise Support d�kker L1 |
| **B � Bundtet (anbefalet pilot)** | EIRA PC inkl. Ubuntu Pro + EIRA Premium � �n faktura, klar matrix |
| **C � Managed** | EIRA-partner ejer begge |

**Dokumentkrav:** `EIRA_Support_Matrix_v1.0.pdf` til indk�b � �n side, ingen tvetydighed.

---

## 2. OS-livscyklus og opdateringer

### Relevans: **KRITISK** � uden dette �del�gger IT EIRA ved `do-release-upgrade`.

### Blindt punkt (bekr�ftet)

Ubuntu 28.04 udkommer ? IT opgraderer ? EIRA Runtime ikke certificeret ? brud.

### EIRA's svar: Lifecycle Management

```
???????????????????????????????????????????
?  EIRA OS Release Train                   ?
?  EIRA 2.x certificeret p� Ubuntu 24.04   ?
?  EIRA 3.x certificeret p� Ubuntu 26.04   ?
???????????????????????????????????????????
```

| Mekanisme | Beskrivelse |
|-----------|-------------|
| **APT hold / pinning** | Governance agent holder `ubuntu-release-upgrader` indtil EIRA gr�nt lys |
| **EIRA OS version = (EIRA x.y + Ubuntu LTS)** | F.eks. `EIRA 2.4 @ Ubuntu 24.04` � ikke "EIRA 2.4 alene" |
| **Certificeret matrix** | Publiceret: hvilke EIRA-versioner p� hvilke Ubuntu LTS |
| **Migration path** | Staged: test ring ? 5% ? 100% OS+migration toolkit |
| **Support overlap** | Minimum 6 m�neder overlap mellem EIRA p� gammel og ny LTS |

**IT-budskab:** "I opgraderer ikke Ubuntu � I opgraderer **EIRA OS release**, som inkluderer certificeret Ubuntu-baseline."

**Anti-pattern:** Fri `apt dist-upgrade` uden EIRA-godkendelse p� managed endpoints.

---

## 3. Desktop- og GUI-arkitektur

### Relevans: **KRITISK** � dit sp�rgsm�l om "chrome clone" h�rer her.

### Blindt punkt (bekr�ftet)

Hvad er EIRA Desktop teknisk? Custom compositor? GNOME fork?

### EIRA's svar: **Chrome-shell model — ikke compositor fra bunden**

> **Fuld spec:** [EIRA_Desktop_Architecture_v1.0.md](EIRA_Desktop_Architecture_v1.0.md)

```
Ubuntu LTS
  ??? Wayland session (minimal)
        ??? labwc / cage / eller GNOME shell (skjult)
              ??? eira-shell (Tauri, fullscreen)  ? Explorer Mode
              ??? optional: Builder f�r panel/terminal
```

| Valg | Beslutning | Begrundelse |
|------|------------|-------------|
| Custom compositor (COSMIC-lignende) | **NEJ** | Accessibility, skaler, vedligehold � bryder "usynligt Linux" |
| GNOME/KDE som bruger-UI | **NEJ** (Explorer) | F�les som "Linux desktop 2000" |
| **Tauri + system WebView (WebKitGTK)** | **JA** (Explorer) | "Chrome OS for enterprise" � �n app-shell, lokal Rust-backend |
| Underliggende WM | Minimal (labwc/cage) | Vinduer kun i Builder Mode |

### Er det "rent chrome-clone drevet"?

**Ja � i Explorer Mode er det pr�cis rigtigt:**

> EIRA Explorer er en **fullscreen application shell** (Tauri), ikke et desktop-milj�.  
> Som Chrome OS: browseren *er* skrivebordet � men her er det **Intent + Actions**, ikke faner.

| Chrome OS | EIRA Explorer |
|-----------|---------------|
| Chrome browser = UI | Tauri shell = UI |
| Web apps | Intent-driven actions + embedded views |
| Linux kernel under | Ubuntu LTS under |
| Crostini (Linux apps) | **Builder Mode** (bevidst eksponeret) |

**Builder Mode** er bevidst undtagelsen � terminal, filer, Docker � for udviklere og IT. Ikke standardbrugeren.

### Accessibility

- Explorer: WCAG via WebView/HTML � testbar med standardv�rkt�jer
- System: arv Ubuntu accessibility services (Orca) i Builder Mode
- **Ikke** genopfind sk�rml�ser i custom compositor

---

## 4. AppArmor / sandbox vs EIRA Capability

### Relevans: **H�J** � sikkerhedsarkitekter vil sp�rge.

### Blindt punkt (bekr�ftet)

EIRA tillader handling ? AppArmor blokerer ? hvad nu?

### EIRA's svar: Lag-r�kkef�lge

```
1. Ubuntu MAC (AppArmor)     ? hard ceiling � kan IKKE overskrives af EIRA
2. EIRA Capability Layer     ? hvad m� fors�ges
3. EIRA Intent / Agent         ? hvad brugeren �nsker
```

| Konflikt | Adf�rd |
|----------|--------|
| EIRA tillader, AppArmor blokerer | **AppArmor vinder** � log begge, vis rationale til bruger |
| EIRA blokerer, AppArmor tillader | **EIRA vinder** � policy (fx USB, app whitelist) |

**EIRA genererer AppArmor-profiler** for `eira-*` daemons ved install � **overskriver ikke** systemprofiler.

Capability Layer ? MAC. Capability = "m� Public360 godkende?" � ikke kernel-sandbox.

---

## 5. Snap vs Flatpak

### Relevans: **H�J** i Ubuntu-verden � politisk minefelt.

### Blindt punkt (bekr�ftet)

Canonical presser Snap; Firefox er Snap p� Ubuntu.

### EIRA's svar: Pragmatisk enterprise-billede

| Komponent | Valg |
|-----------|------|
| **EIRA apps + adaptere** | Flatpak (primary) � kurateret remote, OSTree, enterprise-kendt |
| **Base OS** | Ubuntu LTS **uden** at fjerne snapd i v1 (undg� breakage) |
| **Firefox** | Snap (Ubuntu default) ELLER deb/firefox ESR via policy � **IT v�lger** |
| **EIRA Shell (Tauri)** | `.deb` eller static binary � **ikke** Snap/Flatpak (boot-critical) |

**Princip:** EIRA **anbefaler ikke** snap-only strategi, men **�del�gger ikke** Ubuntu ved at fjerne snapd.

**Enterprise golden image:** `eira-desktop` preinstalled; snapd disabled **kun** hvis IT eksplicit v�lger det og tester Firefox-alternativ.

**Dokument�r:** `EIRA_Packaging_Policy_v1.0` � Flatpak for apps, deb for platform, Snap tolerance on base.

---

## 6. Offline og fallback

### Relevans: **KRITISK** � rejse, tunnel, server-nede.

### Blindt punkt (delvist d�kket i Identity Spec �3)

EIRA Core utilg�ngelig ? kan bruger arbejde?

### EIRA's svar: Local-first med defineret degradation

| Komponent | Offline-adf�rd |
|-----------|----------------|
| **Login** | SSSD cache + passkey � **Ubuntu overtager** |
| **Explorer UI** | K�rer lokalt (Tauri) |
| **Object graph** | Lokal SQLite cache � read degraded |
| **Intent (rule-based)** | Fungerer offline for cached entities |
| **Intent (LLM)** | Lokal model ELLER rule-only fallback |
| **Adapters** | Kr�ver netv�rk � vis "offline, handling k�et" |
| **Governance policy** | Cached; �ndringer venter |
| **Step-up / wallet** | Blokeret (Identity Spec) |

**Princip:** EIRA **tr�der ikke i vejen** for Ubuntu SSO-cache. EIRA **degraderer gracefully** � banner: "Begr�nset tilstand � nogle handlinger utilg�ngelige."

**Ikke:** Central server required for at logge ind (det ville v�re Chromebook-fejl).

---

## 7. Telemetri og log-korrelation

### Relevans: **H�J** � SIEM er CISO's sprog.

### Blindt punkt (bekr�ftet)

journald + auditd + Intent Audit � samme h�ndelse?

### EIRA's svar: Correlation ID p� tv�rs

```json
{
  "correlation_id": "uuid",
  "sources": [
    { "system": "ubuntu", "subsystem": "udev", "event": "usb_insert" },
    { "system": "eira", "subsystem": "governance", "event": "usb_blocked" },
    { "system": "eira", "subsystem": "intent_audit", "event": "policy_denied" }
  ]
}
```

| Lag | Format | Transport |
|-----|--------|-----------|
| Ubuntu auditd/journald | native | forward til SIEM |
| EIRA Intent Audit | JSON Lines + **CEF** | samme SIEM endpoint |
| **Correlation** | `correlation_id` i alle EIRA events; `auditd` timestamp link |

**SIEM playbooks:** "USB blocked" = join udev + eira-governance p� `correlation_id` + `device_id`.

---

## 8. GUI-beslutning � opsummering (chrome-shell)

| Sp�rgsm�l | Anbefaling |
|-----------|------------|
| Rent chrome-clone drevet? | **Ja for Explorer** � Tauri fullscreen shell |
| Custom compositor? | **Nej** |
| GNOME som bruger-UI? | **Nej** (kun skjult session infrastructure) |
| Wayland? | **Ja** |
| Builder Mode? | Eksponeret Ubuntu-v�rkt�jer � bevidst undtagelse |

```
Standard medarbejder:  ser kun EIRA Explorer (chrome-shell)
IT / udvikler:         Builder Mode ? terminal, Docker, systemv�rkt�jer
```

Det er pr�cis "skift Windows ud med Ubuntu uden 2000-GUI" � Ubuntu er under motorhjelmen, brugeren ser ikke GNOME.

---

## 9. Dokumentstatus (opdateret juli 2026)

| Dokument | Prioritet | Status |
|----------|-----------|--------|
| [EIRA_Support_Matrix_v0.1](EIRA_Support_Matrix_v0.1.md) | P0 pilot | ✅ Skrevet |
| [EIRA_Strategic_Reality_Check_v0.1](EIRA_Strategic_Reality_Check_v0.1.md) | P0 | ✅ Skrevet |
| [EIRA_Desktop_Architecture_v1.0](EIRA_Desktop_Architecture_v1.0.md) | P0 | ✅ Skrevet |
| [EIRA_VPN_Compatibility_Matrix_v0.1](EIRA_VPN_Compatibility_Matrix_v0.1.md) | P0 | ◐ Skabelon |
| [EIRA_EDR_Partner_Requirements_v0.1](EIRA_EDR_Partner_Requirements_v0.1.md) | P0 | ✅ Skrevet |
| [EIRA_OSS_Operations_Model_v0.1](EIRA_OSS_Operations_Model_v0.1.md) | P0 | ✅ Skrevet |
| [EIRA_Pilot_Validation_Plan_v0.1](EIRA_Pilot_Validation_Plan_v0.1.md) | P0 | ✅ Skrevet |
| [EIRA_BCP_Endpoint_Fallback_v0.1](EIRA_BCP_Endpoint_Fallback_v0.1.md) | P0 | ✅ Skrevet |
| [EIRA_Change_Management_Pilot_v0.1](EIRA_Change_Management_Pilot_v0.1.md) | P0 | ✅ Skrevet |
| [EIRA_Performance_Acceptance_v0.1](EIRA_Performance_Acceptance_v0.1.md) | P1 | ✅ Skrevet |
| EIRA_Support_Matrix_v1.0 | P1 | ⬜ Efter pilot |
| EIRA_OS_Lifecycle_Policy_v1.0 | P0 | Delvist i [Release Train](../../eira-fleet-control/docs/specs/EIRA_Update_Release_Train_v0.1.md) |
| EIRA_Packaging_Policy_v1.0 (Snap/Flatpak) | P1 | ⬜ |
| EIRA_SIEM_Integration_Guide_v1.0 | P1 | ⬜ |
| EIRA_MAC_Integration_v1.0 (AppArmor) | P1 | ⬜ |

---

## 10. Vurdering af analysens relevans

| Punkt | Relevans | Allerede d�kket? | Handling |
|-------|----------|------------------|----------|
| 1 Support | Kritisk | Delvist | [Support Matrix v0.1](EIRA_Support_Matrix_v0.1.md) — v1.0 til indkøb |
| 2 Lifecycle | Kritisk | Delvist (staged rollout) | OS pinning + release train |
| 3 GUI | Kritisk | Delvist (Tauri n�vnt) | Chrome-shell beslutning dokument�r |
| 4 AppArmor | H�j | Nej | MAC integration doc |
| 5 Snap/Flatpak | H�j | Delvist | Packaging policy |
| 6 Offline | Kritisk | Identity Spec �3 | EIRA-wide degradation model |
| 7 SIEM | H�j | Delvist (CEF n�vnt) | Correlation ID spec |

**Analysen er relevant og korrekt.** Den g�r Platform Principles **enterprise-klar** � ikke obsolete.

---

## Relaterede dokumenter (operationalisering)

| Spørgsmål | Dokument |
|-----------|----------|
| Support og eskalering | [Support Matrix v0.1](EIRA_Support_Matrix_v0.1.md) |
| Patching og CVE | [OSS Operations Model](EIRA_OSS_Operations_Model_v0.1.md) |
| VPN før pilot | [VPN Compatibility Matrix](EIRA_VPN_Compatibility_Matrix_v0.1.md) |
| Fallback | [BCP Endpoint Fallback](EIRA_BCP_Endpoint_Fallback_v0.1.md) |
| Navigation | [Document Map](../EIRA_Document_Map_v0.1.md) |

---

*EIRA Ubuntu Integration � Blind spots & svar v0.1*
