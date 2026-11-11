# EIRA � Glue Layer: ingeni�r-risici og arkitekt-beslutninger v0.1

**Status:** Normativ � implementation  
**Dato:** 26. juni 2026  
**Form�l:** De 5 blinde punkter i OSS-integrationsstrategien � med **beslutninger**, ikke bare risici  
**Relateret:** [EIRA_OSS_Integration_Manifest_v0.1.md](EIRA_OSS_Integration_Manifest_v0.1.md), [EIRA_Windows_Parity_Architecture_v0.1.md](EIRA_Windows_Parity_Architecture_v0.1.md)

---

## Konklusion (�verst)

> **Den reelle risiko er "limen"** � Policy Compiler + Governance Agent der binder fragmenterede OSS-komponenter sammen uden konfigurationskonflikter.

Strategien (Ubuntu + OSS + EIRA orkestrering) er **korrekt**. Dette dokument definerer **hvordan limen bygges** s� den kan matche Windows uden at kn�kke endpoints.

---

## Risiko 1 � Policy Compiler (det sv�reste stykke kode)

### Problemet

�n YAML-regel (fx *"Bloker USB hvis ikke p� VPN"*) skal overs�ttes til korrekte, ikke-konfliktende konfigurationer i:

- udev rules  
- NetworkManager dispatcher  
- AppArmor-profiler  
- systemd units  
- Flatpak permissions  
- step-up policy (identityd)

Fejl ? brick, sikkerhedshul, eller falsk gr�n status i Fleet.

### Arkitekt-beslutning: **Ikke �n monolitisk compiler fra dag �t**

```
policy.yaml
    ?
???????????????????????????????????????
?  eira-policy-engine (Rust)          ?
?  ??? parse + JSON Schema validate   ?
?  ??? dependency graph (cross-rules) ?
?  ??? dispatch til backends          ?
???????????????????????????????????????
    ?           ?           ?
 backend-    backend-    backend-
 apparmor    network     udev
 (pure)      (pure)      (pure)
```

| Princip | Beskrivelse |
|---------|-------------|
| **�n backend per subsystem** | Hver backend genererer kun sit dom�ne � testbar isoleret |
| **Ingen cross-rules i Sprint 0�1** | Kun simple 1:1 mappings (fx `usb.allow` ? udev) |
| **Cross-rules fra P2** | Kr�ver explicit `requires:` i YAML + constraint validation |
| **Compile ? validate ? stage ? apply** | Aldrig direkte skriv til `/etc` |

### Apply-pipeline (normativ)

```
1. COMPILE    policy.yaml ? staged/ (per backend output)
2. VALIDATE   syntaks: apparmor_parser -Q, nmcli con validate, systemd-analyze
3. DRY-RUN    optional Fleet "preview diff" for IT
4. SNAPSHOT   /var/lib/eira/policy-snapshots/<id>/  (rollback)
5. APPLY      atomisk per backend-r�kkef�lge (se nedenfor)
6. PROBE      health checks ? Fleet (gr�n/gul/r�d)
7. ROLLBACK   ved probe-fail ? restore snapshot + alert
```

**Apply-r�kkef�lge (undg�r lockout):**

```
network (VPN f�rst) ? identity/sssd ? apparmor ? udev ? flatpak ? falco ? systemd
```

### Fejl = aldrig silent

| Fejltype | Adf�rd |
|----------|--------|
| Compile error | **Ingen apply** � Fleet r�d, forrige policy aktiv |
| Validate error | **Ingen apply** � log + IT alert |
| Apply partial fail | **Auto-rollback** til snapshot |
| Runtime probe fail | Gul ? r�d efter grace; rollback hvis kritisk (VPN/login) |

### Sprint 0�1 scope (bevidst lille)

| Policy-n�gle | Backend | Cross-rule? |
|--------------|---------|-------------|
| `vpn.profiles` | network | Nej |
| `apps.flatpak_whitelist` | flatpak | Nej |
| `usb.allow` | udev | Nej |
| `security.falco_rules` | falco | Nej |
| `identity.entra` | identityd | Nej |

**Udskudt:** `usb.requires_vpn`, composite firewall+USB, dynamic step-up chains.

**Dokument:** [EIRA_Policy_Compiler_Architecture_v0.1.md](EIRA_Policy_Compiler_Architecture_v0.1.md) (detaljer).

---

## Risiko 2 � Wayland, global shortcuts og eira-shell

### Problemet

Global shortcuts (`Ctrl+K`) er compositor-afh�ngige under Wayland. Dybt compositor-indgreb = vedligeholdelsesbyrde.

### Arkitekt-beslutning: **Explorer ejer tastaturet � compositor ejer ikke UX**

Standardbruger (Explorer) k�rer **kun** `eira-shell` fullscreen. Der er ingen anden app med fokus i normal drift.

```
Explorer (95%):
  eira-shell = eneste interaktive lag
  Ctrl+K h�ndteres INDE i Tauri/WebView
  ? INGEN compositor global shortcut n�dvendig

Legacy app (whitelist, sj�ldent):
  Fokus i LibreOffice/XWayland
  ? Bruger vender tilbage til shell for intentioner
  ? ELLER: compositor-binding kun for Super+E (fokus eira-shell)

Builder / IT:
  labwc config: Super+B ? Builder
  Global shortcuts via labwc/rc.xml (wlroots)
```

| Tilstand | Ctrl+K | Compositor-indgreb |
|----------|--------|---------------------|
| Explorer fullscreen | eira-shell internt | **Ingen** |
| Legacy XWayland app | Ikke global � shell via Super+E | Minimal labwc binding |
| Builder | Terminal/shell shortcuts | Standard labwc |

**Compositor-valg:** `labwc` (ikke `cage`) � underst�tter `rc.xml` keybindings uden fork. **cage** er for rene kiosk-scenarier uden legacy.

**Risiko reduceret:** Intent Engine lytter ikke globalt p� tastaturet � den lytter via **eira-shell UI**. Det matcher manifestet: brugeren handler i �t system.

---

## Risiko 3 � WINE i enterprise

### Problemet

WINE kn�kker ved Windows-opdateringer; Excel-makroer fejler subtilt � forkerte data uden fejl.

### Arkitekt-beslutning: **WINE droppes for enterprise EIRA OS**

| Milj� | Win32-strategi |
|-------|----------------|
| **Enterprise (kommune)** | Kun **EIRA Legacy Runtime** (KVM) eller **RDS / Windows 365 / AVD** (FreeRDP) |
| **Consumer / Builder** | WINE valgfri i Builder Mode � **ikke** supporteret af EIRA SLA |

```
Intention kr�ver Win32
        ?
Capability check
        ?
??? Linux-native app (Flatpak)
??? Adapter (M365 Web)
??? Legacy Runtime (KVM/RDP) � ALDRIG WINE i Explorer
```

**Opdateret i:** [EIRA_OSS_Integration_Manifest_v0.1.md](EIRA_OSS_Integration_Manifest_v0.1.md) � Wine fjernet fra STANDARD enterprise bundle.

**QA-besparelse:** Ingen uforholdsm�ssig WINE-certificering per kommune-app.

---

## Risiko 4 � Provisioning: MAAS vs. Autopilot Zero-Touch

### Problemet

MAAS kr�ver PXE/netv�rk. Autopilot = OEM registrerer i cloud, bruger pakker ud og t�nder.

### Arkitekt-beslutning: **EIRA Factory Enroll** (Autopilot-paritet)

```
???????????????????????????????????????????????????????????????
?  OEM (Lenovo/Dell) � factory eller refurb                     ?
?  1. Ubuntu + EIRA golden image pre-flashed                   ?
?  2. DMI serial + TPM EK pub ? pre-registered i Fleet         ?
?  3. cloud-init nocloud seed ELLER USB-partition (first boot) ?
???????????????????????????????????????????????????????????????
                          ? first power-on
???????????????????????????????????????????????????????????????
?  eira-firstboot.service                                      ?
?  ? cloud-init: enroll token (hardware-bound)                 ?
?  ? mTLS til Fleet Control                                    ?
?  ? bundle apply                                              ?
?  ? Explorer klar � ingen IT touch                           ?
???????????????????????????????????????????????????????????????
```

| Fase | Metode |
|------|--------|
| **Pilot** | IT pre-provisionerer USB/autoinstall (manuel) � acceptabelt for 50 PC |
| **Production** | **OEM-partnerskab** � EIRA Certified PC med Factory Enroll |
| **Fallback** | MAAS PXE for datacenter/lab � ikke prim�r kommune-model |

**Paritet med Autopilot:** Hardware hash (serial + TPM) ? Fleet pre-registration ? self-enroll ved first boot.

**Dokument:** [EIRA_Factory_Enroll_v0.1.md](EIRA_Factory_Enroll_v0.1.md)

---

## Risiko 5 � Pre-login VPN og maskincertifikater

### Problemet

Cisco/Forti pre-login kr�ver maskincertifikater. Cert udl�b/rotation uden login = brick. Hardware-�ndring = cert mismatch.

### Arkitekt-beslutning: **Provisioneret livscyklus + break-glass � ikke "bare systemd"**

```
Provisioning (Factory Enroll / imaging):
  Fleet issuer ? SCEP/EST eller manuel CSR
  ? maskincert i /etc/eira/certs/machine/
  ? NM OpenConnect profile refererer cert
  ? backup escrow i Fleet (krypteret)

Drift:
  governance-agent overv�ger cert expiry (osquery + openssl)
  ? auto-renew via SCEP 30 dage f�r udl�b (online)
  ? Fleet alert hvis renewal fejler

Break-glass (policy-gated):
  Local recovery OU i AD
  ? policy: allow_offline_login_without_vpn: true (kun recovery)
  ? IT JIT elevation med audit
  ? ELLER: wired onboarding VLAN uden VPN (factory only)
```

| Risiko | Mitigation |
|--------|------------|
| Cert udl�b, ingen net | Factory re-enroll USB; Fleet remote wipe + re-image |
| Hardware swap | Ny cert via Fleet re-provision; gammel cert revoked |
| Always On VPN + cert fail | **Fail-open til recovery login** � policy, ikke hard lock |

**Probe:** Fleet viser `vpn.machine_cert_days_remaining` � gul < 30, r�d < 7.

---

## Prioritering � hvad bygges f�rst

| # | Komponent | Sprint | Kritikalitet |
|---|-----------|--------|--------------|
| 1 | Policy engine + 3 backends (vpn, flatpak, falco) | 0�1 | **H�jest** |
| 2 | Apply pipeline + snapshot rollback | 0�1 | **H�jest** |
| 3 | eira-shell (Ctrl+K intern) | 0�1 | H�j |
| 4 | Factory Enroll spec + pilot USB flow | 1 | H�j |
| 5 | Machine cert lifecycle | 1�2 | H�j |
| 6 | Legacy Runtime (KVM/RDP) � uden WINE | 1�2 | Medium |
| 7 | Cross-rule compiler | 2+ | Medium |

---

## �n s�tning

> **Windows vandt p� �n GPO. EIRA vinder ved en compiler der er sikker nok til at fejle � og en shell der ejer tastaturet s� compositor-politikken ikke skal.**

---

*EIRA Glue Layer � ingeni�r-risici v0.1*
