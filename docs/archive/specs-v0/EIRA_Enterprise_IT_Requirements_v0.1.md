# EIRA Enterprise IT Requirements v0.1

**Status:** Udkast � strategisk specifikation  
**Dato:** 26. juni 2026  
**Projekt:** EIRA OS  
**M�lgruppe:** IT-chefer, driftsledere, informationssikkerhed, indk�b (kommuner og offentlig sektor)  
**Relateret:** EIRA OS Whitepaper kap. 18, EIRA Identity Strategy v0.2

---

## 1. Form�l

Dette dokument besvarer to sp�rgsm�l:

1. **Hvilke krav stiller en stor IT-afdeling** til udrulning, rettigheder, monitorering og compliance?
2. **Hvordan bliver EIRA OS det foretrukne styresystem** � ikke bare det brugervenligste?

Kernebeslutning:

> IT-afdelingen er **prim�r k�ber og gatekeeper**. EIRA OS skal vindes p� **kontrol, dokumentation og lavere drift** � ikke kun p� brugeroplevelse.

---

## 2. Hvem er IT-afdelingen?

| Rolle | Bekymring | Succeskriterium |
|-------|-----------|-----------------|
| **IT-chef** | Risiko, budget, politisk ansvar | F�rre incidents, forudsigelig TCO |
| **Drift / endpoint** | Udrulning, patches, support | Intune-lignende kontrol uden kaos |
| **Informationssikkerhed (CISO/ISB)** | NIS2, GDPR, audit | Dokumenterbar efterlevelse |
| **Identitetsadministrator** | AD/Entra, roller | SSO uden dobbelt-login |
| **Indk�b / juridisk** | Udbud, DPA, exit | Ingen ny vendor lock-in |
| **DPO** | Persondata, Schrems II | Data i EU, minimal indsamling |

---

## 3. Kravkatalog � hvad IT forventer

Kravene er grupperet efter **KL's tekniske minimumskrav**, **NIS2** og erfaring fra **Microsoft Intune/Entra**-milj�er (de facto standard i kommuner).

### 3.1 Udrulning og livscyklus (Endpoint Management)

| ID | Krav | Hvorfor | EIRA-svar |
|----|------|---------|-----------|
| U1 | Golden image / PXE / netv�rksboot | Massedeployment uden manuel ops�tning | EIRA PC pre-provisioned + `eira-deploy` PXE/USB |
| U2 | Zero-touch enrollment | IT skal ikke bes�ge 1.000 skriveborde | Auto-enrollment ved f�rste Entra-login |
| U3 | Remote wipe / re-provision | Tabt/stj�let PC, offboarding | `eira-identityd` + fuld disk-kryptering n�gle-escrow |
| U4 | Staged rollout | Test f�r fuld udrulning | 5% ? 20% ? 50% ? 100% (whitepaper) |
| U5 | Rollback | Fejlslagen opdatering | Snapshot + rollback til godkendt version |
| U6 | Maintenance windows | Ingen opdatering i arbejdstid | Planlagte vinduer per OU/afdeling |
| U7 | Hardware inventory | Asset management | Automatisk rapport: serienr, OS-version, compliance |
| U8 | Offline / air-gapped | S�rlige milj�er | USB-baseret opdatering uden internet |

**Benchmark:** Microsoft Intune + Autopilot. EIRA skal matche **80% af Intune-funktionalitet** relevant for kommuner � ikke alle enterprise-features.

### 3.2 Software og applikationer

| ID | Krav | Hvorfor | EIRA-svar |
|----|------|---------|-----------|
| S1 | App whitelist (allowlist) | Forhindre malware, shadow IT | EIRA Enterprise Portal � godkendte apps |
| S2 | App blacklist | Blok�r Tor, torrent, u�nskede messengers | Policy engine |
| S3 | Central app-katalog | �n sandhed for "hvad m� installeres" | Kurateret App Store + enterprise-pakker |
| S4 | Pakkeformat | Reproducerbar installation | Flatpak / deb + EIRA-signerede pakker |
| S5 | Adapter-godkendelse | Public360, KMD OPUS m.fl. | EIRA Adapter Standard + test suite |
| S6 | Sikkerhedsopdateringer ? 30 dage | KL tekniske minimumskrav | Automatisk patch-kanal + compliance-rapport |
| S7 | Feature updates kontrolleret | IT godkender major versions | Optional efter IT-godkendelse |
| S8 | Custom software | Kommune-specifikke apps | Builder Mode + signeret side-loading |

### 3.3 Identitet og rettigheder

| ID | Krav | Hvorfor | EIRA-svar |
|----|------|---------|-----------|
| I1 | Entra ID / AD federation | Eksisterende brugerbase | IdP connector (Identity Strategy v0.2) |
| I2 | Gruppebaseret policy | "IT afdeling" ? "sagsbehandling" | AD/Entra-grupper ? EIRA policies |
| I3 | RBAC for IT-portal | Kun autoriserede �ndrer policies | Roller: viewer, operator, admin |
| I4 | Ingen lokal admin (default) | Reduc�r angrebsflade | Standardbruger uden sudo; Builder Mode via rolle |
| I5 | Privileged access | N�dadgang til drift | JIT elevation med audit |
| I6 | Step-up ved sensitive handlinger | Compliance, ikke kun login | MitID Erhverv / EUDI (Identity Strategy) |
| I7 | Offboarding | Medarbejder stopper | Deaktiver i Entra ? EIRA revoker session + wipe tokens |

### 3.4 Sikkerhed (endpoint)

| ID | Krav | Hvorfor | EIRA-svar |
|----|------|---------|-----------|
| E1 | Fuld disk-kryptering | Tabt enhed | LUKS2 mandatory, n�gle i escrow |
| E2 | Secure Boot | Bootkit-beskyttelse | Verificeret boot-k�de |
| E3 | Endpoint protection (EDR) | Malware | Integration med ClamAV + kommerciel EDR (evalueres) |
| E4 | USB-politik | Databrud via USB | Block / allowlist per policy |
| E5 | Firewall | Netv�rkssegmentering | `nftables` + central policy |
| E6 | VPN kun godkendte endpoints | Remote access | Policy: kun godkendte VPN-profiler |
| E7 | Sk�rml�s ved inaktivitet | Ubemandet PC | Automatisk l�s (KL: f� minutter) |
| E8 | Root/jailbreak detection | Compromised devices | Integritetscheck ved boot |

### 3.5 Monitorering, logging og audit

| ID | Krav | Hvorfor | EIRA-svar |
|----|------|---------|-----------|
| M1 | Central log-samling | Incident response | Syslog/CEF til SIEM |
| M2 | SIEM-integration | Sentinel, Splunk, QRadar | Webhook + standardformater |
| M3 | Audit trail � login | Hvem loggede ind hvorn�r | Identity layer audit |
| M4 | Audit trail � handlinger | Compliance, efterforskning | **Intent log** � EIRA-unik differentiator |
| M5 | Audit trail � filadgang | GDPR, intern kontrol | Adapter-niveau logging |
| M6 | Compliance dashboard | "Er vi compliant?" | Enterprise Portal: % compliant PC'er |
| M7 | Alerting | Proaktiv drift | Email, webhook, Teams ved afvigelser |
| M8 | Anomaly detection | Us�dvanlig adf�rd | Baseline + afvigelsesalarmer (V2) |
| M9 | Log retention | Juridisk krav | Konfigurerbar (typisk 365 dage) |
| M10 | Revision-eksport | Revisor, Datatilsynet | �n-klik compliance-rapport (PDF/CSV) |

### 3.6 Compliance og lovgivning

| Ramme | Relevans | EIRA-krav |
|-------|----------|-----------|
| **NIS2** (DK fra juli 2025) | Kommuner er omfattet | Dokumenterbar risikostyring, leverand�rkrav, h�ndelseslog |
| **GDPR** | Altid | DPA, dataminimering, rettigheder |
| **KL tekniske minimumskrav** | De facto standard | Endpoint-beskyttelse, opdateringer ? 30 dage, MDM-principper |
| **ISO 27001** | Ofte krav i udbud | ISMS-dokumentation, kontroller |
| **Offentlig informationssikkerhed (DK)** | Kommuner | Tilsvarende statslige krav |
| **Schrems II** | Cloud-suver�nitet | EU-hosting, ingen US-identitetsdata som default |
| **EU AI Act** | EIRA's lokale AI | AI audit log (whitepaper kap. 6) |

### 3.7 Drift, support og leverand�r

| ID | Krav | Hvorfor | EIRA-svar |
|----|------|---------|-----------|
| L1 | SLA med responstid | Kritisk infrastruktur | Premium: 4t responstid (whitepaper) |
| L2 | Support-kanal | IT skal have direkte linje | Dedikeret kontakt, ikke kun bruger-hotline |
| L3 | Dokumentation | Driftschef skal kunne overtage | Runbooks, API-docs, policy-reference |
| L4 | Tr�ning af IT | Kompetenceopbygning | Onboarding-pakke til IT (ikke kun brugere) |
| L5 | Databehandleraftale | GDPR | Standard DPA |
| L6 | Exitklausul | Ingen ny lock-in | Eksport af policies, logs; standard Linux under EIRA |
| L7 | Coexistence med Windows | Big bang er urealistisk | Hybrid-fl�de: EIRA + Windows parallelt |
| L8 | Integration M365 | SharePoint, Outlook, Teams | Entra + adaptere � ikke erstatning |

---

## 4. EIRA Enterprise Platform � produktarkitektur for IT

Whitepaper kap. 18 beskriver visionen. Her konkretiseres den som **fire produktmoduler** IT kan k�be og evaluere:

```
???????????????????????????????????????????????????????????????????
?                    EIRA ENTERPRISE PLATFORM                      ?
???????????????????????????????????????????????????????????????????
?   CONTROL    ?   IDENTITY   ?   COMPLY     ?    OPERATIONS      ?
?   (Portal)   ?   (Bridge)   ?   (Audit)    ?    (Deploy)        ?
???????????????????????????????????????????????????????????????????
? Policy mgmt  ? Entra/AD     ? SIEM export  ? Golden image       ?
? App whitelist? MitID/EUDI   ? Intent audit ? PXE / enrollment   ?
? Updates      ? Step-up      ? Compliance % ? Remote wipe        ?
? Focus states ? RBAC         ? NIS2 reports ? Inventory          ?
? AI policies  ? Org-IdP      ? GDPR export  ? Staged rollout     ?
???????????????????????????????????????????????????????????????????
                              ?
                    EIRA PC (endpoint agent)
```

### 4.1 EIRA Enterprise Portal (CONTROL)

Web-baseret � svarer til **Intune Admin Center** + **policy**-delen af Group Policy.

IT-chefen skal kunne:

- Se alle enrolled PC'er og compliance-status
- Godkende/blokere apps og opdateringer
- Udrulle policies til grupper (via Entra/AD)
- Trigger n�d-patch inden for 4 timer
- Eksportere audit til revisor

### 4.2 EIRA Identity Bridge (IDENTITY)

Se `EIRA_Identity_Strategy_v0.2.md`. IT's perspektiv:

- Federation med eksisterende Entra � **ingen ny brugerbase**
- Hybrid: Entra til daglig login, eID til step-up
- Central styring af step-up-regler per rolle/afdeling

### 4.3 EIRA Compliance Engine (COMPLY)

**EIRA's st�rkeste IT-argument** � det Windows ikke har out-of-the-box:

| Funktion | Windows + Intune | EIRA OS |
|----------|------------------|---------|
| "Hvem �bnede filen" | Delvist (M365 audit) | Ja, via adaptere |
| "Hvad fors�gte brugeren" | Nej | **Intent audit** � unikt |
| "Hvorfor blev handling blokeret" | Sj�ldent | Policy + forklaring (UX regel 5) |
| AI-beslutninger logget | Copilot � uklart | AI metadata + audit (whitepaper) |
| �n rapport til revisor | Manuel sammenstilling | Compliance dashboard |

### 4.4 EIRA Deploy (OPERATIONS)

| Funktion | Beskrivelse |
|----------|-------------|
| Golden image | EIRA PC med kommune-policies pre-konfigureret |
| Enrollment | QR / Entra-token ved f�rste boot |
| OTA updates | Staged kanaler: stable, beta, emergency |
| Remote actions | Wipe, lock, force policy refresh |
| Inventory | Hardware, OS, adapter-versioner, compliance |

---

## 5. Hvordan EIRA OS bliver IT's foretrukne valg

### 5.1 Beslutningsmatrix � hvad IT optimerer efter

| Faktor | V�gt for IT | EIRA-position |
|--------|-------------|---------------|
| Sikkerhed & compliance | H�j | NIS2-ready, intent audit, EU-suver�nitet |
| Driftsomkostning | H�j | F�rre support tickets (m�l: -50%) |
| Kontrol | H�j | Portal = Intune-lignende |
| Integration | H�j | Entra + M365 � ikke rip-and-replace |
| Brugeraccept | Medium | Slutbruger-UX er bonus, ikke hovedsalg |
| Politisk risiko | Medium | Gradvis pilot, hybrid med Windows |
| Leverand�rrisiko | Medium | Open source kerne, exitklausul |

### 5.2 Salgsargumenter til IT-chefen (ikke slutbrugeren)

| # | Budskab | Bevis |
|---|---------|-------|
| 1 | **"I beholder Entra og M365"** | IdP connector, SharePoint/Outlook-adaptere |
| 2 | **"I f�r bedre audit end i dag"** | Intent log + compliance dashboard |
| 3 | **"NIS2-dokumentation med �t klik"** | Compliance-rapporter, ikke manuelle Excel-ark |
| 4 | **"F�rre supporthenvendelser"** | Pilot-KPI: -50% tickets |
| 5 | **"Ingen US-cloud til kerneidentitet"** | Local-first, EU-hosting |
| 6 | **"Gradvis udrulning � ikke big bang"** | 50 PC pilot ? 500 ? 5.000 |
| 7 | **"I kan altid vende tilbage"** | Standard Linux under EIRA, policy-eksport |

### 5.3 Hvad der IKKE s�lger til IT

| Svagt budskab | Hvorfor |
|---------------|---------|
| "Revolutionerende ny computeroplevelse" | IT h�rer risiko |
| "Erstat Windows overalt" | Politisk og teknisk urealistisk kort sigt |
| "AI g�r alt" | Governance-bekymring |
| "Billigere licens" alene | TCO er drift + support, ikke kun licens |

### 5.4 Konkurrence: EIRA vs. status quo

| | Windows 11 + Intune + M365 | EIRA OS Enterprise |
|---|---------------------------|-------------------|
| Endpoint management | Modent (Intune) | Skal bygges (Portal) � **kritisk gap** |
| Brugeroplevelse | Fragmenteret (mange systemer) | Samlet (EIRA's styrke) |
| Audit p� tv�rs af systemer | Delvist | Intent + adapter audit |
| Suver�nitet | US-cloud afh�ngighed | EU, local-first |
| Kommunal fagsystem-integration | Connectors overalt | Adapter Standard |
| Supportbelastning | H�j (kendt problem) | Lavere (hypotese � skal bevises i pilot) |
| IT-kompetencekrav | Lav (kendt) | Medium (Linux) � **barriere** |

### 5.5 Kritiske gaps EIRA skal lukke for at vinde IT

| Gap | Prioritet | Handling |
|-----|-----------|----------|
| **Enterprise Portal (Intune-paritet)** | P0 | Byg f�r pilot � IT siger nej uden dette |
| **Entra ID integration** | P0 | Identity Strategy Fase 0b |
| **SIEM-eksport** | P0 | CEF/syslog fra dag �t |
| **EDR/antivirus** | P0 | Partner eller integreret l�sning |
| **KL/NIS2 compliance-rapport** | P1 | Skabelon mapping til minimumskrav |
| **Linux drift-dokumentation** | P1 | Runbooks p� dansk/tysk |
| **Printer/peripheral** | P1 | CUPS, driver-strategi |
| **ISO 27001 certificering** | P2 | Langsigtet � whitepaper n�vner det |

---

## 6. Udrulningsmodel IT kan godkende

### Fase 1: Pilot (50 PC'er, 3 m�neder)

```
Uge 1:  IT-chef + sikkerhed � demo af Portal, audit, Entra-integration
Uge 2:  Policies konfigureret i test-OU (spejl af produktion)
Uge 3:  50 PC deployed til �n afdeling (frivillige + IT)
Uge 4-12: Drift, log-indsamling, support-metrics
Uge 12: Go/no-go: tickets, compliance %, bruger-NPS
```

**IT's go/no-go kriterier:**

| Metrik | M�l |
|--------|-----|
| Compliance rate | ? 95% |
| Support tickets vs. kontrolgruppe | ? 50% |
| Kritiske sikkerhedsh�ndelser | 0 |
| SIEM-integration fungerer | Ja |
| Entra SSO til M365 | Ja |

### Fase 2: Hybrid fl�de

- Nye afdelinger: EIRA PC
- Eksisterende: Windows indtil naturlig udskiftning
- Samme Entra tenant � �n identitetsmodel
- F�lles SIEM for begge platforme

### Fase 3: Skalering

- KOMBIT/KL-reference case
- Standard udbudstekst med EIRA-krav
- Tyskland: tilsvarende model med BundID/BSI-orientering

---

## 7. Policy som kode � IT's sprog

IT t�nker i **Group Policy / Intune profiles**. EIRA leverer **YAML policies** � versionerbare, git-venlige, reviewbare:

```yaml
# eira-policy/kk-skoleforvaltning-2026.yaml
version: "1.0"
org_unit: "OU=Skoleforvaltning,DC=kk,DC=dk"
inherits: "kk-base-policy"

apps:
  allowed: [libreoffice, chrome, teams, public360-adapter, kmd-opus-adapter]
  blocked: [telegram, tor-browser]

updates:
  security: mandatory_within_hours: 48
  feature: require_it_approval: true
  channel: stable

security:
  disk_encryption: mandatory
  usb: block_except_whitelist
  local_admin: false
  screen_lock_minutes: 5

identity:
  org_login: entra-primary
  step_up_budget_approve: org_acting

audit:
  log_intents: true
  log_adapter_calls: true
  retention_days: 365
  siem_endpoint: "https://sentinel.kk.dk/eira-ingest"

compliance:
  framework: [nis2, kl-minimumskrav, gdpr]
  report_schedule: monthly
```

IT kan **reviewe policies i git** f�r udrulning � bedre end klik-i-UI for store organisationer.

---

## 8. Tyskland � IT-perspektiv

| DK-krav | DE-�kvivalent | EIRA |
|---------|---------------|------|
| KL minimumskrav | BSI IT-Grundschutz orientering | Policy mapping |
| NIS2 | NIS2 (EU) | Samme compliance engine |
| NemLog-in | BundID | Country pack de |
| KOMBIT | IT-Planungsrat / OZG | Wallet-Adapter integration |
| Datatilsynet | BfDI / Landes-DPA | GDPR DPA |

Tysk IT v�gter **BSI**, **BundID-anbindning** og **f�deral struktur** h�jere. EIRA Deploy skal underst�tte **Landes-policies** (forskellige OU'er per delstat).

---

## 9. Produktpakker til IT (prisreference fra whitepaper)

| Pakke | Indhold | IT-v�rdi |
|-------|---------|----------|
| **EIRA Governance** (499 DKK/PC/�r) | Portal, policies, audit | Kontrol |
| **EIRA Adaptere** (299 DKK/PC/�r) | Public360, KMD, SharePoint | Integration |
| **EIRA Support Premium** (99 DKK/PC/�r) | 4t SLA | Driftstryghed |
| **EIRA Complete** (899 DKK/PC/�r) | Alt ovenst�ende | Samlet |

**Services:** Implementering 50.000�200.000 DKK � inkl. IT-workshops, policy-setup, SIEM-kobling.

---

## 10. N�ste skridt

1. **Priorit�r EIRA Enterprise Portal** � uden dette ingen IT-godkendelse
2. **Map krav U1�M10 til roadmap** � sprintplan for governance
3. **NIS2/KL compliance-matrix** � dokument�r hvilket krav EIRA opfylder hvordan
4. **Pilot-kit til IT** � demo-milj� med Portal + 5 test-PC'er + SIEM-eksport
5. **Opdater whitepaper kap. 18** med dette kravkatalog
6. **Tysk pendant** � BSI-orienteret compliance-sektion

---

## 11. Opsummering

**Store IT-afdelinger kr�ver:** kontrolleret udrulning, whitelist, patches, Entra-integration, disk-kryptering, SIEM, audit, NIS2-dokumentation og hybrid-coexistence med Windows.

**EIRA OS vinder IT'en ved at:**
- Levere **Intune-lignende kontrol** (Portal)
- Give **bedre audit** end Windows (intent log)
- **Integrere med Entra/M365** � ikke konkurrere
- Dokumentere **NIS2/KL-compliance** automatisk
- Tillade **gradvis pilot** med m�lbare KPI'er

**EIRA OS vinder IKKE IT'en kun med brugeroplevelse** � det er indgangen for medarbejderen, men **kontrol og compliance** er indgangen for IT-chefen.

---

*EIRA Enterprise IT Requirements v0.1 � Fortroligt udviklingsdokument*
