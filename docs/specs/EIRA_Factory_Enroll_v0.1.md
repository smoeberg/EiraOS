# EIRA Factory Enroll v0.1

**Status:** Normativ � provisioning og zero-touch  
**Dato:** 26. juni 2026  
**M�l:** **Autopilot-paritet** � PC fra fabrik til managed EIRA endpoint uden IT-fysisk touch  
**Relateret:** [EIRA_Glue_Layer_Engineering_v0.1.md](EIRA_Glue_Layer_Engineering_v0.1.md), [EIRA_Fleet_Agent_Protocol_v0.1.md](EIRA_Fleet_Agent_Protocol_v0.1.md), [EIRA_OSS_Integration_Manifest_v0.1.md](EIRA_OSS_Integration_Manifest_v0.1.md)

---

## 1. Form�l

**EIRA Factory Enroll** er provisioning-modellen der binder:

- OEM / golden image  
- Hardware-identitet (serial + TPM)  
- Fleet Control pre-registration  
- F�rste boot ? managed endpoint  

> **Bruger pakker PC ud, t�nder � EIRA enroll sker automatisk. IT r�rer ikke enheden.**

Dette matcher [Enterprise IT Requirements](EIRA_Enterprise_IT_Requirements_v0.1.md) **U2 Zero-touch enrollment** og Windows **Autopilot**.

---

## 2. Tre enroll-kanaler

| Kanal | Hvorn�r | IT touch | Autopilot-paritet |
|-------|---------|----------|-------------------|
| **A � Factory Enroll** | Production, EIRA Certified PC | **Ingen** | Fuld |
| **B � Pilot Enroll** | Pilot 50 PC, lab, refurb | USB / �n gang netv�rk | Delvis |
| **C � MAAS Enroll** | Datacenter, PXE-lab | Ja (netv�rk boot) | Nej � fallback |

**Nordstjerne:** Kanal A. Kanal B er acceptabel i Sprint 1. Kanal C er ikke kommune-primary.

---

## 3. Hardware-identitet (device fingerprint)

Hver enhed har en **stabil hardware-id** brugt til pre-registration og enroll-binding:

```
hardware_id = SHA256(
  DMI_SYSTEM_SERIAL +
  DMI_PRODUCT_UUID +
  TPM_EK_PUB (hvis tilg�ngelig)
)
```

| Felt | Kilde | Krav |
|------|-------|------|
| `system_serial` | `/sys/class/dmi/id/product_serial` | Obligatorisk |
| `product_uuid` | DMI | Obligatorisk |
| `tpm_ek_pub` | `tpm2_readpublic` EK | Anbefalet � **P1 production** |
| `manufacturer` | DMI | Inventory |
| `model` | DMI | EIRA Certified PC match |

**Uden TPM:** enroll tilladt i pilot � med reduceret assurance (policy flag `enroll_requires_tpm: true` i production).

---

## 4. Pre-registration (Fleet Control � f�r first boot)

OEM eller IT registrerer enheden **f�r** den t�ndes p� kundens netv�rk:

```json
POST /v1/devices/preregister
{
  "tenant_id": "kommune-kk",
  "hardware_id": "sha256:�",
  "system_serial": "PF3XXXX",
  "manufacturer": "Lenovo",
  "model": "ThinkPad T14 Gen 5",
  "ou": "OU=Skoleforvaltning,DC=kk,DC=dk",
  "bundle_pin": "2026.06.26-stable",
  "policy_revision": "git:skolefv-1.3",
  "ring": 2,
  "enroll_token_one_time": "opaque-�",
  "expires_at": "2026-12-31T23:59:59Z"
}
```

| Felt | Beskrivelse |
|------|-------------|
| `enroll_token_one_time` | Single-use � forbr�ndes ved successful enroll |
| `bundle_pin` | Bundle l�st ved first boot |
| `ring` | Staged rollout ring |

**OEM-flow:** Lenovo/Dell sender CSV/API med serials ? Fleet bulk pre-register ved shipment.

---

## 5. Golden image (hvad der er p� disken ved leverance)

### 5.1 Factory image indhold

```
Ubuntu 24.04 LTS (minimal)
??? EIRA OS Bundle (CORE minimum)
?   ??? eira-shell, eira-identityd, eira-governance-agent
?   ??? OSS stack per OSS Integration Manifest
??? cloud-init
??? eira-firstboot.service (enabled)
??? /boot/firmware/eira/          # nocloud seed (kanal A)
?   ??? meta-data
?   ??? user-data.template
??? /etc/eira/factory.conf        # tenant hint, Fleet URL (ikke secret)
```

**Secrets p� disken:** **Ingen** long-lived tokens. Kun `factory.conf` med Fleet URL + tenant slug. One-time token leveres via pre-registration match p� hardware_id.

### 5.2 cloud-init user-data (first boot)

```yaml
#cloud-config
hostname: eira-${serial}
package_update: false
package_upgrade: false
write_files:
  - path: /etc/eira/factory-enroll.json
    content: |
      {
        "fleet_url": "https://fleet.kommune.dk",
        "tenant": "kommune-kk",
        "channel": "factory"
      }
runcmd:
  - systemctl enable --now eira-firstboot.service
```

---

## 6. First boot � `eira-firstboot.service`

K�rer **�n gang** ved f�rste opstart (f�r bruger-login):

```
eira-firstboot.service
  ?
  ??1. Collect hardware_id (DMI + TPM)
  ??2. POST /v1/enroll ? Fleet Control
  ?      payload: hardware_id, serial, tpm_ek_pub, bundle_version_installed
  ??3. Fleet validates pre-registration + one-time token
  ??4. Fleet returns:
  ?      - device_id (UUID)
  ?      - device_mtls_cert + key (ny)
  ?      - desired_state (bundle, policy)
  ??5. governance-agent stores mTLS identity
  ??6. Apply bundle (if drift from golden)
  ??7. Apply base policy
  ??8. Optional: machine VPN cert (SCEP) � se �8
  ??9. Mark enrolled: /var/lib/eira/enrolled
  ??10. Disable eira-firstboot � reboot til Explorer
```

**Timeout:** 10 min � ved fejl: retry med exponential backoff; efter 3 fejl ? **enroll failure UI** (IT kontakt + error code).

---

## 7. Enroll API (normativ)

Udvider [Fleet Agent Protocol](EIRA_Fleet_Agent_Protocol_v0.1.md):

### POST `/v1/enroll`

**Request:**

```json
{
  "hardware_id": "sha256:�",
  "system_serial": "PF3XXXX",
  "product_uuid": "�",
  "tpm_ek_pub": "base64�",
  "manufacturer": "Lenovo",
  "model": "ThinkPad T14 Gen 5",
  "firmware_versions": {
    "ubuntu": "24.04.2",
    "eira_os": "2.4.1",
    "bundle": "2026.06.26-stable"
  },
  "enroll_channel": "factory | pilot | maas",
  "pilot_token": "optional-for-channel-B"
}
```

**Response (201):**

```json
{
  "device_id": "uuid",
  "device_certificate": "-----BEGIN CERTIFICATE-----�",
  "device_private_key": "�",
  "fleet_ca": "-----BEGIN CERTIFICATE-----�",
  "desired_state": {
    "bundle_to_apply": "2026.06.26-stable",
    "policy_revision": "git:skolefv-1.3",
    "ring": 2
  },
  "machine_cert_scep_url": "optional"
}
```

**Fejl:**

| HTTP | Betydning | UI |
|------|-----------|-----|
| 404 | Ikke pre-registered | "Kontakt IT � enhed ukendt" |
| 409 | Allerede enrolled | Normal boot (skip firstboot) |
| 403 | Token expired / hardware mismatch | "Kontakt IT � enroll afvist" |
| 503 | Fleet utilg�ngelig | Offline retry (72t buffer ikke aktiv f�r enroll) |

---

## 8. Maskincertifikater (pre-login VPN)

Ved Factory Enroll kan Fleet udstede eller trigger SCEP for **machine VPN cert**:

```
Enroll success
  ? governance-agent henter SCEP URL fra Fleet
  ? CSR med device_id + hardware_id
  ? cert i /etc/eira/certs/machine/
  ? NM OpenConnect profile aktiveres (pre-login unit)
```

Se [Glue Layer Engineering](EIRA_Glue_Layer_Engineering_v0.1.md) �5.

**Pilot (kanal B):** maskincert kan uds�ttes � VPN kun efter user login indtil cert-livscyklus er p� plads.

---

## 9. Kanal B � Pilot Enroll (50 PC)

Til Sprint 1 n�r OEM-partnerskab ikke er p� plads:

```
IT i Portal:
  [+ Enroll PC] ? bulk 50 tokens ELLER CSV serials pre-register

Metode 1 � USB:
  IT skriver autoinstall USB med cloud-init + pilot_token
  Bruger booter �n gang fra USB ? image p� disk ? first boot enroll

Metode 2 � Pre-imaged:
  IT modtager PC, flasher golden image (�n gang)
  Sender til afdeling � herefter kanal A flow
```

| vs. Factory | Pilot |
|-------------|-------|
| IT flasher eller USB �n gang | OEM flasher |
| `pilot_token` i stedet for OEM bulk | `enroll_token_one_time` per serial |
| TPM valgfrit | TPM p�kr�vet i production policy |

**Pilot er ikke Autopilot � men end-state efter f�rste flash er identisk.**

---

## 10. Kanal C � MAAS (fallback)

```
Fleet ? MAAS API: deploy Ubuntu + EIRA autoinstall
MAAS PXE ? maskine
cloud-init ? eira-firstboot (channel: maas)
```

Bruges til: lab, datacenter, re-imaging. **Ikke** standard kommune laptop rollout.

---

## 11. Sikkerhed

| Trussel | Mitigation |
|---------|------------|
| Stj�let PC f�r first boot | Pre-reg kr�ver match hardware_id; uden match ? ingen enroll |
| Replay enroll token | One-time token; invalid efter brug |
| Man-in-the-middle | TLS til Fleet; mTLS efter enroll |
| Klonet disk | TPM EK binding � clone uden TPM match ? 403 |
| Fleet kompromit | Short-lived enroll tokens; audit p� alle enroll events |

**Enrolled mark�r:**

```
/var/lib/eira/enrolled          # JSON: device_id, enrolled_at
/etc/eira/device/               # mTLS cert (0600 root:eira)
```

Re-enroll kr�ver Fleet **admin wipe** + ny pre-registration.

---

## 12. IT Portal � oplevelse

```
Fleet Console ? Enheder ? [+ Factory Enroll]

Bulk import:
  Upload CSV: serial, model, OU
  ? 50 enheder "Afventer first boot" (gr�)

Efter first boot:
  ? "Enrolled" (gr�n) + compliance probes

Fejl:
  ? "Enroll fejlet" (r�d) + hardware_id + fejlkode
```

**Autopilot-paritet:** IT ser **Afventer / Enrolled / Fejl** � ikke "g� fysisk til PC".

---

## 13. OEM-partnerskab (EIRA Certified PC)

| OEM leverer | EIRA leverer |
|-------------|--------------|
| Pre-flashed golden image | Image build + signering |
| Serial list ved shipment | Fleet bulk pre-register API |
| TPM 2.0 p� alle enheder | hardware_id spec |
| Ubuntu Certified hardware | [Support Matrix v0.1](EIRA_Support_Matrix_v0.1.md) |
| Factory warranty | EIRA Premium Support option |

**Certificeringsm�rke:** `EIRA Certified PC` � kun godkendte model + firmware + image-kombination.

---

## 14. Fejl og recovery

| Situation | Handling |
|-----------|----------|
| First boot uden net | Retry; vis "Forbind til netv�rk"; offline enroll **ikke** supported |
| Forkert OU p� pre-reg | Fleet re-assign f�r first boot ELLER wipe + re-enroll |
| Bruger t�nder f�r IT pre-reg | 404 UI � IT pre-registrerer ? bruger genstarter |
| Hardware repareret (nyt board) | Ny serial/TPM ? ny pre-reg; gammel device revoked |
| Wipe | Fleet `wipe` command ? cryptsetup erase ? re-enroll som ny |

---

## 15. Faseplan

| Fase | Kanal | Leverance |
|------|-------|-----------|
| **Sprint 1** | B (Pilot) | `eira-firstboot`, enroll API, USB autoinstall, 50 PC |
| **P1** | A (Factory) | OEM API, TPM binding, EIRA Certified PC program |
| **P2** | A + C | MAAS integration for enterprise |
| **P2** | Dual | Intune enroll **efter** EIRA enroll (coexist) |

---

## 16. Komponenter (implementering)

| Komponent | Pakke / service |
|-----------|-----------------|
| `eira-firstboot.service` | systemd oneshot |
| `eira-enroll` | CLI � bruges af firstboot + debug |
| `eira-governance-agent` | modtager mTLS identitet |
| `cloud-init` | OSS � first boot config |
| Fleet `/v1/enroll` | server |

---

## 17. Successkriterier

| Metrik | Pilot m�l | Production m�l |
|--------|-----------|----------------|
| Tid fra power-on til Explorer | < 15 min (inkl. bundle) | < 10 min |
| IT fysisk touch per PC | ? 1 (kun pilot USB) | **0** |
| Enroll success rate | ? 95% | ? 99% |
| Forkert hardware binding | 0 | 0 |

---

## 18. Dokumentrelation

| Dokument | Rolle |
|----------|-------|
| [Fleet Agent Protocol](EIRA_Fleet_Agent_Protocol_v0.1.md) | Transport + heartbeat efter enroll |
| [Update Release Train](EIRA_Update_Release_Train_v0.1.md) | Bundle ved first boot |
| [OSS Integration Manifest](EIRA_OSS_Integration_Manifest_v0.1.md) | cloud-init i bundle |
| [Glue Layer](EIRA_Glue_Layer_Engineering_v0.1.md) | Arkitekt-beslutning Autopilot-paritet |

---

*EIRA Factory Enroll v0.1*
