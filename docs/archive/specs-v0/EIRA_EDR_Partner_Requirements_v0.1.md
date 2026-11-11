# EIRA EDR Partner Requirements v0.1

**Status:** Normativ — indkøb, CISO, arkitektur  
**Dato:** 4. juli 2026  
**Formål:** Definér krav til endpoint detection & response på EIRA OS — inkl. pilot-beslutning (Wazuh-only vs. kommerciel partner)  
**Relateret:**
- [EIRA_Windows_Technical_Parity_v0.1.md](EIRA_Windows_Technical_Parity_v0.1.md) §4
- [EIRA_Windows_Parity_Architecture_v0.1.md](EIRA_Windows_Parity_Architecture_v0.1.md) §3.4
- [EIRA_OSS_Integration_Manifest_v0.1.md](EIRA_OSS_Integration_Manifest_v0.1.md) §5.4
- [EIRA_Support_Matrix_v0.1.md](EIRA_Support_Matrix_v0.1.md)
- [EIRA_Strategic_Reality_Check_v0.1.md](EIRA_Strategic_Reality_Check_v0.1.md) §6, §11
- [EIRA_OSS_Operations_Model_v0.1.md](EIRA_OSS_Operations_Model_v0.1.md)

---

## 1. Kernebeslutning

> **Intent Audit supplerer EDR — det erstatter ikke kommerciel EDR-dybde i enterprise-indkøb.**

EIRA OS leverer et **lagdelt sikkerhedsstack**:

```
Lag 4  Intent Audit          ← unik (intention + rationale)
Lag 3  Kommerciel EDR        ← krav i de fleste kommuner (valgbar partner)
Lag 2  OSS detection         ← Falco (eBPF) + auditd + AppArmor
Lag 1  Wazuh agent            ← HIDS, log forward, SIEM-korrelation
Lag 0  Ubuntu kernel         ← audit subsystem, namespaces
```

**Pilot-default (beslutning uge 4):** Wazuh + Falco + AppArmor + Intent Audit er **tilstrækkeligt til Fase 0** hvis CISO accepterer skriftligt. Kommerciel EDR-slot forberedes i bundle alligevel.

---

## 2. Pilot vs. produktion

| Fase | Minimum stack | Kommerciel EDR |
|------|---------------|----------------|
| **Fase 0** (reference-PC) | Wazuh + Falco + auditd + AppArmor + Intent Audit → SIEM | Valgfri — anbefalet hvis kunden allerede har MDE/CrowdStrike |
| **Fase 1** (~50 PC) | Samme + dokumenteret go/no-go | **Påkrævet** hvis eksisterende kontrakt kræver samme agent på alle endpoints |
| **Fase 3+** (skalering) | Certificeret partner-agent i EIRA bundle | **Påkrævet** for de fleste enterprise-indkøb |

---

## 3. Funktionelle krav (alle kandidater)

### 3.1 Must-have (blokerer godkendelse)

| ID | Krav | Verifikation |
|----|------|--------------|
| E1 | **Linux-agent** til Ubuntu 24.04 LTS (amd64) | Installer fra bundle; health probe grøn |
| E2 | **Real-time detection** (proces, fil, netværk) | Test med `atomic red team` eller vendor test script |
| E3 | **Central management** — samme console som Windows-flåde **eller** API til SIEM | Demo for IT/CISO |
| E4 | **SIEM-export** — syslog, CEF eller JSON | Event i kundens SIEM inden 15 min |
| E5 | **Tamper protection** — agent ikke stopbar af standardbruger | Policy test |
| E6 | **Coexistence** med Wazuh + Falco uden konflikt | 72t soak test på reference-PC |
| E7 | **Coexistence** med Intent Audit — ingen blokeret audit-pipeline | Intent event + EDR event samme incident-id |
| E8 | **Managed update** via EIRA bundle — ikke løs vendor `apt` | Bundle QA inkluderer agent-version |
| E9 | **Offline/degraded** — agent bufferer events lokalt (min. 24t) | Netværk cut test |
| E10 | **Remote isolate** (valgfri men anbefalet) | Network quarantine via policy |

### 3.2 Should-have (enterprise-paritet)

| ID | Krav |
|----|------|
| E11 | eBPF-baseret detection (eller tilsvarende lav overhead) |
| E12 | Memory/script scanning for Linux threats |
| E13 | USB/device control integration med governance policy |
| E14 | M-of-N eller IT-godkendt remote wipe koordinering med Fleet |
| E15 | EU data residency for cloud console (Schrems II) |
| E16 | NIS2-relevant audit trail (hvem, hvad, hvornår) |

### 3.3 Nice-to-have

| ID | Krav |
|----|------|
| E17 | MITRE ATT&CK mapping i dashboard |
| E18 | Automated response playbooks |
| E19 | Integration med Entra ID for device compliance |

---

## 4. Kandidat-partnere (evalueringsmatrix)

| Partner | Linux-modenhed | Typisk kommune-status | EIRA-vurdering |
|---------|----------------|----------------------|----------------|
| **Wazuh-only (OSS)** | HIDS + SIEM — ikke fuld EDR | Acceptabel Fase 0 med CISO-signatur | ✅ Pilot-default |
| **Microsoft Defender for Endpoint (Linux)** | Voksende; dyb M365-integration | Mange kommuner har allerede M365 E5 | ⭐ Førstevalg hvis licens findes |
| **CrowdStrike Falcon** | Moden Linux-agent | Enterprise-standard | ⭐ Stærk kandidat |
| **SentinelOne** | Linux-agent tilgængelig | Mindre udbredt i DK kommune | Vurder ved konkret kunde |
| **Elastic Defend** | Del af Elastic Stack | Hvis kunden har Elastic SIEM | Niche |

**Beslutningsregel:**

```
Har kunden allerede MDE/CrowdStrike på Windows?
  JA → samme vendor på EIRA PC (hvis Linux-agent opfylder §3.1)
  NEJ → Wazuh+Falco til pilot; indkøb kommerciel EDR før Fase 3
```

---

## 5. Wazuh-only pilot — acceptkriterier

Hvis CISO godkender Wazuh-only til Fase 0–1, skal følgende være dokumenteret:

| # | Kriterie | Bevis |
|---|----------|-------|
| 1 | Wazuh manager (on-prem eller EU cloud) modtager events | Dashboard screenshot + retention policy |
| 2 | Falco regler aktiv — min. 10 EIRA-specifikke regler | `falco_rules.local.yaml` i bundle |
| 3 | auditd kører med EIRA ruleset | `auditctl -l` export |
| 4 | AppArmor enforcing på `eira-*` daemons | `aa-status` |
| 5 | Intent Audit CEF i samme SIEM som Wazuh | Korreleret incident demo |
| 6 | **Skriftlig CISO-accept** | "Wazuh-stack tilstrækkelig til pilot; kommerciel EDR inden Fase 3" |
| 7 | **Gap-dokumentation** | Hvad Wazuh ikke dækker vs. MDE (memory, managed response, etc.) |

**Skabelon CISO-accept (1 sætning):**

> *"EIRA pilot godkendes med Wazuh+Falco+Intent Audit som endpoint-sikkerhedsstack. Kommerciel EDR evalueres og implementeres senest ved overgang til Fase 3 eller ved kontraktkrav."*

---

## 6. Bundle-integration (normativ)

### 6.1 OSS CORE (altid i bundle)

Per [OSS Manifest](EIRA_OSS_Integration_Manifest_v0.1.md) §5.4:

- `wazuh-agent` — manager IP via governance
- `falco` — rules fra policy compiler
- `auditd` + `audispd-plugins`
- `apparmor` + EIRA-profiler
- `clamav` (optional on-access)

### 6.2 Kommerciel EDR-slot (STANDARD/PREMIUM tier)

```json
{
  "id": "edr-commercial",
  "tier": "standard",
  "slot": true,
  "packages": ["<vendor-agent-deb>"],
  "eira_interface": "eira-governance-agent ? vendor API",
  "health_probe": "systemctl is-active <vendor-agent>",
  "conflicts_with": []
}
```

**Regel:** Kun **én** kommerciel EDR-agent per endpoint. Wazuh forbliver HIDS/log-forward.

### 6.3 Event flow (obligatorisk)

```
Intent Audit (JSON Lines + CEF)
Falco (syslog PRI)
auditd (audit.log)
EDR agent (vendor format)
        │
        ▼
Wazuh agent (localfile + active response)
        │
        ▼
Kundens SIEM / Wazuh manager / M365 Defender portal
        │
        ▼
Fleet Control (compliance: edr_ok, wazuh_ok, intent_audit_ok)
```

**Korrelations-ID:** `eira_correlation_id` i Intent Audit **skal** sendes som custom field til Wazuh/EDR hvor muligt.

---

## 7. Governance og policy

| Policy-nøgle | Effekt |
|--------------|--------|
| `security.edr.required` | `true` — endpoint non-compliant uden agent |
| `security.edr.vendor` | `wazuh-only` \| `mde` \| `crowdstrike` \| … |
| `security.falco.ruleset` | `eira-default` \| `strict` \| `custom` |
| `security.intent_audit.siem_forward` | `true` |
| `security.tamper_protection` | Blokér stop af `wazuh-agent`, `falco`, `eira-governance-agent` |

Policy compiler skal generere AppArmor + systemd restart policies for agent-tjenester.

---

## 8. Testprotokol (før pilot-commit)

| Trin | Test | Pass |
|------|------|------|
| 1 | Installer bundle på reference-PC | Alle agenter `active` |
| 2 | Kør `eira-security-smoke` (script) | Grøn rapport |
| 3 | Simuler mistænkelig proces (Falco test rule) | Alert i Wazuh ≤ 5 min |
| 4 | Udfør intention med step-up block | Intent Audit event i SIEM |
| 5 | Forsøg `systemctl stop wazuh-agent` som bruger | Fejler (tamper) |
| 6 | 72t normal brug — ingen konflikt med Explorer | Ingen bruger-klager / CPU spike |
| 7 | (Hvis kommerciel) Vendor console viser Linux endpoint | Inventory match Fleet |

---

## 9. Indkøb og kontrakt

| Emne | Krav til leverandør |
|------|---------------------|
| **Licens** | Per-device eller inkluderet i eksisterende E5 — dokumentér |
| **Data** | EU-region for cloud console; DPA vedlagt |
| **Support** | L0 vendor + L1 EIRA triage (se Support Matrix) |
| **Exit** | Agent kan fjernes uden at ødelægge Ubuntu |
| **Bundle** | `.deb` version pin — EIRA QA før publish |

**Indkøbstekst (copy-paste):**

> *"Leverandøren skal levere Linux endpoint-agent kompatibel med Ubuntu 24.04 LTS, integrerbar i EIRA OS Bundle jf. EIRA_EDR_Partner_Requirements_v0.1, med SIEM-export og coexistence med Wazuh/Falco/Intent Audit."*

---

## 10. Beslutning — deadline uge 4

| Option | Vælg hvis | Næste skridt |
|--------|-----------|--------------|
| **A: Wazuh-only pilot** | Ingen eksisterende EDR-kontrakt; CISO accepterer gap | CISO-signatur §5; ship Fase 0 |
| **B: MDE Linux** | Kunden har M365 E5 / Defender | Test Linux-agent på reference-PC |
| **C: CrowdStrike** | Kunden har Falcon på Windows | Test Falcon Linux sensor |
| **D: Udskyd** | Ingen CISO tilgængelig | **Blokerer ikke** Fase 0 hvis A godkendes |

**Anbefaling:** Start med **A** for intern reference-PC; vælg **B eller C** før første betalende kommune hvis de allerede har vendor.

---

## 11. Relation til Intent Audit (differentiator)

| | Windows EDR | EIRA stack |
|---|-------------|------------|
| Ser proces start/stop | ✅ | ✅ |
| Ser fil-ændring | ✅ | ✅ |
| Ser **hvorfor brugeren handlede** | ❌ | ✅ Intent Audit |
| Ser policy-rationale ved blokering | ❌ | ✅ |
| NIS2 evidens med ét klik | Delvist | ✅ Compliance Engine |

**Salg til CISO:** EDR + Intent Audit — ikke enten/eller.

---

## Relaterede dokumenter (operationalisering)

| Spørgsmål | Dokument |
|-----------|----------|
| Pilot security gates | [Pilot Validation Plan](EIRA_Pilot_Validation_Plan_v0.1.md) |
| Bundle og CVE | [OSS Operations Model](EIRA_OSS_Operations_Model_v0.1.md) |
| Intent Audit (CISO) | [Fleet Control](../../eira-fleet-control/docs/specs/EIRA_Fleet_Control_v0.1.md) |
| Beslutning uge 4 | [Sprint Plan](../Sprint_Plan_v0.1.md) spor 1 |
| Navigation | [Document Map](../EIRA_Document_Map_v0.1.md) |

---

*EIRA EDR Partner Requirements v0.1 — opdater når partner er valgt og certificeret i bundle.*
