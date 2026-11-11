# EIRA Pilot Validation Plan v0.1

**Status:** Normativ — Fase 0 gate + Fase 1 go/no-go  
**Dato:** 4. juli 2026  
**Formål:** Samlet test- og valideringsplan før ~50 PC pilot — sikkerhed, kompatibilitet, performance, rollback, brugeraccept  
**Relateret:**
- [EIRA_Support_Matrix_v0.1.md](EIRA_Support_Matrix_v0.1.md)
- [EIRA_VPN_Compatibility_Matrix_v0.1.md](EIRA_VPN_Compatibility_Matrix_v0.1.md)
- [EIRA_EDR_Partner_Requirements_v0.1.md](EIRA_EDR_Partner_Requirements_v0.1.md)
- [EIRA_BCP_Endpoint_Fallback_v0.1.md](EIRA_BCP_Endpoint_Fallback_v0.1.md)
- [EIRA_Strategic_Reality_Check_v0.1.md](EIRA_Strategic_Reality_Check_v0.1.md)
- [EIRA_Enterprise_Endpoint_Transition_v1.0.md](../../../company/EIRA_Enterprise_Endpoint_Transition_v1.0.md)

---

## 1. Scope

| Fase | PC | Formål | Exit |
|------|-----|--------|------|
| **Fase 0** | 1 reference-PC | Teknisk paritet bevist | IT-chef skriftlig godkendelse |
| **Fase 0b** | 3–5 PC (valgfri) | Soak + edge cases | Ingen røde blockers |
| **Fase 1 gate** | ~50 PC klar | Go/no-go før produktion | Champion + CISO sign-off |

**Uden for scope (Sprint 1+):** Pen-test program fuld, WCAG certificering, national skalering (1000+).

---

## 2. Domæner og ejere

| Domæne | ID | Ejer | Dokument |
|--------|-----|------|----------|
| Identity & session | V-ID | eira-os | Identity Strategy, prototype |
| VPN & netværk | V-NET | eira-os + IT | VPN Compatibility Matrix |
| Print / smartcard | V-HW | eira-os | Support Matrix |
| EDR / SIEM | V-SEC | eira-os + CISO | EDR Partner Requirements |
| Bundle / rollback | V-OPS | fleet-control | Release Train, OSS Ops Model |
| Intent / UX | V-UX | eira-os | UX Logic, Risk Sprint R2 |
| Performance | V-PERF | eira-os | (acceptkriterier nedenfor) |
| Brugeraccept | V-ADOPT | company + champion | [Change Management Pilot](EIRA_Change_Management_Pilot_v0.1.md) |
| Fallback | V-BCP | company + IT | BCP Endpoint Fallback |

---

## 3. Fase 0 — obligatoriske tests (reference-PC)

Alle skal være **grønne** før IT-chef signerer paritet (Support Matrix §6).

### 3.1 V-ID — Identity

| # | Test | Pass-kriterie | Evidens |
|---|------|---------------|---------|
| ID-1 | Entra OIDC login | Session oprettet ≤ 10s | Intent Audit event |
| ID-2 | Session persist reboot | Auto-login eller passkey ≤ 5s | Manuel |
| ID-3 | MitID Erhverv step-up | Blok → step-up → confirm → execute | IPC/API smoke |
| ID-4 | Offboarding simulering | Revoke i Entra → session død ≤ 5 min | Fleet + audit |

### 3.2 V-NET — VPN

| # | Test | Pass-kriterie | Evidens |
|---|------|---------------|---------|
| NET-1 | VPN profil via governance | Ingen manuel GUI-config | governance log |
| NET-2 | Always On efter reboot | Forbundet før bruger-login (hvis krævet) | VPN matrix udfyldt |
| NET-3 | Sleep / resume | Reconnect ≤ 30s | Manuel 3× |
| NET-4 | Compliance drop | Fleet alert ved disconnect | Portal screenshot |

### 3.3 V-HW — Hardware

| # | Test | Pass-kriterie | Evidens |
|---|------|---------------|---------|
| HW-1 | IPP print | Testside + dokument fra Explorer-flow | CUPS log |
| HW-2 | Smartcard (MitID) | `pcsc_scan` + Identity session | Support Matrix |
| HW-3 | Docking 1× 4K | Skærm stabil 8t | Manuel |
| HW-4 | fwupd / LVFS | Firmware current | Fleet inventory |

### 3.4 V-SEC — Sikkerhed

| # | Test | Pass-kriterie | Evidens |
|---|------|---------------|---------|
| SEC-1 | Wazuh agent aktiv | Event modtaget ≤ 15 min | Manager dashboard |
| SEC-2 | Falco test rule | Alert korreleret | SIEM |
| SEC-3 | Intent Audit CEF | Samme SIEM som SEC-1/2 | CEF sample |
| SEC-4 | Tamper: stop agent som bruger | Fejler | audit log |
| SEC-5 | AppArmor enforcing `eira-*` | `aa-status` | export |

Se [EDR Partner Requirements](EIRA_EDR_Partner_Requirements_v0.1.md) §8 for fuld protokol.

### 3.5 V-OPS — Bundle og rollback

| # | Test | Pass-kriterie | Evidens |
|---|------|---------------|---------|
| OPS-1 | Fleet enroll + heartbeat | Enhed online i Portal | screenshot |
| OPS-2 | Policy push 1 YAML | Active på endpoint | compliance |
| OPS-3 | Bundle apply | Version bump, health grøn | agent log |
| OPS-4 | **Atomic rollback** | btrfs snapshot → apply → fail → rollback | apply-result: `rolled_back` |
| OPS-5 | Policy snapshot rollback | Forrige policy aktiv ≤ 15 min | Transition §9 |

### 3.6 V-UX — Intent og dashboard

| # | Test | Pass-kriterie | Evidens |
|---|------|---------------|---------|
| UX-1 | `dashboard.get` | Greeting + trust + journey | API/IPC smoke |
| UX-2 | Intent plan → confirm | Block uden step-up; execute efter | ipc_smoke_test |
| UX-3 | Rationale synlig | Menneskelig forklaring ved plan | screenshot |
| UX-4 | Silent wrong execution | **0** i 50-intention PoC | Risk Sprint R2 |

### 3.7 V-PERF — Performance (minimum)

| # | Test | Pass-kriterie | Evidens |
|---|------|---------------|---------|
| PERF-1 | Explorer cold start | ≤ 3s til interaktiv | 5× median |
| PERF-2 | Intent plan (rule path) | P95 ≤ 500ms | Risk Sprint R2 |
| PERF-3 | Daglig brug 8t | CPU idle < 15%; ingen swap thrash | telemetri |
| PERF-4 | FUSE **ikke** i hot path | Ingen FUSE mount i standard Explorer | `mount` audit |

*Tung I/O / legacy:* testes kun hvis pilot-profil kræver Legacy Bridge — ellers **N/A**.

---

## 4. Fase 0b — soak og edge (anbefalet)

| # | Test | Varighed | Pass |
|---|------|----------|------|
| SOAK-1 | Normal arbejdsdag simulering | 3 dage × 1 bruger | Ingen P1 incidents |
| SOAK-2 | Bundle apply under arbejde | 1 rollout | Ingen datatab; rollback testet |
| SOAK-3 | Netværk flap (VPN drop 5×) | 1 dag | Auto-recover; bruger ikke blokeret permanent |
| SOAK-4 | XWayland whitelisted app (hvis relevant) | 2 apps | Kendte begrænsninger dokumenteret |

---

## 5. Fase 1 gate — før ~50 PC

### 5.1 Tekniske gates (alle påkrævet)

| Gate | Kriterie |
|------|----------|
| G1 | Fase 0 alle grønne + VPN matrix **udfylt** for pilot-kommune |
| G2 | EDR-beslutning truffet (Wazuh-only signatur eller kommerciel agent testet) |
| G3 | Fleet MVP: enroll, bundle, compliance %, remote wipe testet på ≥ 3 PC |
| G4 | Rollback drill gennemført (ring 0 → forrige bundle) |
| G5 | [BCP Fallback](EIRA_BCP_Endpoint_Fallback_v0.1.md) runbook reviewed af IT-chef |
| G6 | ≥ 2 reference-adaptere i demo (R1a) |
| G7 | R2 PoC: top-1 ≥ 85%, silent wrong = 0 |

### 5.2 Organisatoriske gates

| Gate | Kriterie |
|------|----------|
| G8 | Champion udpeget med rollback-mandat |
| G9 | Pilot-afdeling valgt (ingen VBA-kritisk uden VM-plan) |
| G10 | L1 runbook — [Change Management](EIRA_Change_Management_Pilot_v0.1.md) §7 |
| G11 | Brugerbriefing planlagt (30 min + 2t dag 1) |

### 5.3 Brugeraccept (V-ADOPT)

| Metrik | Mål | Kill |
|--------|-----|------|
| Survey NPS (dag 30) | ≥ baseline − 10 | < baseline − 25 |
| L1 eskalering vs. Windows-afdeling | ≤ 1.5× | > 2.5× |
| “Kan udføre kerneopgaver” (n≥15) | ≥ 80% ja | < 60% |
| Champion vurdering | “Fortsæt Fase 2” | “Stop pilot” |

---

## 6. Fejlscenarier og rollback-drills

| Scenario | Simulering | Forventet respons | Dokument |
|----------|------------|-------------------|----------|
| Bundle corrupt | Inject bad package i test-ring | Auto rollback; ring 0 hold | Release Train |
| Policy fejl | Push broken YAML | Snapshot restore ≤ 15 min | Policy Compiler |
| VPN total failure | Blokér gateway 4t | BCP Tier 2 hybrid | BCP Fallback |
| Wazuh manager nede | Stop manager | Agent buffer; alert IT | EDR Req §3.1 E9 |
| Intent kill criterion | PoC fejl | Rule-only mode; ingen rollout | Risk Sprint |
| Brugerrevolt | Survey kill | Ring 0 + champion kommunikation | BCP §5 |

**Drill-krav:** Mindst **én** fuld rollback-drill (OPS-4) og **én** policy-rollback før Fase 1.

---

## 7. Sikkerhedsvalidering (minimum)

Fuld red team er P2 (Gap Checklist). Fase 0 minimum:

| # | Test | Pass |
|---|------|------|
| ST-1 | Standardbruger kan ikke `sudo` | Fejler |
| ST-2 | Standardbruger kan ikke stoppe `eira-governance-agent` | Fejler |
| ST-3 | Whitelisted app kan ikke læse anden brugers `/home` | Fejler |
| ST-4 | Intent Audit log kan ikke slettes af bruger | Fejler |
| ST-5 | Builder Mode kræver rolle | Ikke tilgængelig for pilot-bruger |

*Detaljeret threat model:* `EIRA_Security_Isolation_Model_v0.1` (P1).

---

## 8. Rapportering

### 8.1 Fase 0 rapport (1 PDF til IT-chef)

```
1. Executive summary (grøn/gul/rød per domæne)
2. VPN matrix (udfyldt)
3. EDR-beslutning + CISO-signatur (hvis Wazuh-only)
4. Rollback drill log
5. Kendte begrænsninger + hybrid-plan
6. Anbefaling: godkend / godkend med betingelser / afvis
```

### 8.2 Fase 1 go/no-go (møde)

Deltagere: IT-chef, champion, CISO (eller delegat), EIRA.

**Rød blocker:** Én af G1–G7 fejler → **no-go** til 50 PC.

---

## 9. Værktøjer og scripts

| Script | Domæne | Sti |
|--------|--------|-----|
| IPC smoke | V-UX, V-ID | `prototype/phase1/scripts/ipc_smoke_test.py` |
| EDR smoke | V-SEC | `eira-security-smoke` (planlagt) |
| Bundle rollback | V-OPS | governance-agent integration test |

---

## 10. Tidsplan (forslag)

| Uge | Aktivitet |
|-----|-----------|
| 0–2 | Fase 0 tests V-ID, V-NET, V-HW |
| 2–4 | V-SEC, V-OPS, rollback drill |
| 4–6 | R2 PoC (50 intentioner), V-UX |
| 6–8 | Fase 0b soak, Fase 0 rapport |
| 8–10 | Fase 1 gates G1–G11, go/no-go |

---

## 11. Relation til andre planer

| Dokument | Rolle |
|----------|-------|
| [Support Matrix](EIRA_Support_Matrix_v0.1.md) | Fase 0 acceptkriterier (overlap §6) |
| [Enterprise Transition](../../../company/EIRA_Enterprise_Endpoint_Transition_v1.0.md) | Fase 0–1 kommerciel ramme |
| [BCP Fallback](EIRA_BCP_Endpoint_Fallback_v0.1.md) | Når validation fejler |
| [OSS Ops Model](EIRA_OSS_Operations_Model_v0.1.md) | Bundle QA bag OPS-* |

---

*EIRA Pilot Validation Plan v0.1 — opdater ved hver gate-review.*
