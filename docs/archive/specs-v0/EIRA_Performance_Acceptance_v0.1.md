# EIRA Performance Acceptance v0.1

**Status:** Normativ — Fase 0 gate (reference-PC)  
**Dato:** 4. juli 2026  
**Formål:** Målbare acceptkriterier for ydeevne — Explorer hot path uden FUSE  
**Relateret:**
- [EIRA_Pilot_Validation_Plan_v0.1.md](EIRA_Pilot_Validation_Plan_v0.1.md) V-PERF
- [EIRA_Windows_Technical_Parity_v0.1.md](EIRA_Windows_Technical_Parity_v0.1.md) §3
- [EIRA_Support_Matrix_v0.1.md](EIRA_Support_Matrix_v0.1.md)

---

## 1. Princip

> **FUSE er kompatibilitetslag — ikke performance-path.** Acceptkriterier gælder standard vidensarbejder-profil i Explorer uden Legacy Bridge.

---

## 2. Reference-miljø

| Felt | Værdi |
|------|-------|
| Hardware | [Support Matrix v0.1](EIRA_Support_Matrix_v0.1.md) reference-PC |
| OS | EIRA bundle `stable` @ Ubuntu 24.04 |
| Netværk | Kontor Wi-Fi eller docked Ethernet |
| Last | Ingen anden tung baggrunds-app |

---

## 3. Acceptkriterier

| ID | Metrik | Mål | Kill | Måling |
|----|--------|-----|------|--------|
| P1 | Explorer cold start → interaktiv | ≤ 3s median | > 5s | 5× boot, stopwatch |
| P2 | `dashboard.get` API | P95 ≤ 200ms | > 1s | curl × 50 |
| P3 | Intent plan (rule path) | P95 ≤ 500ms | > 2s | Risk Sprint R2 |
| P4 | CPU idle (8t kontordag) | < 15% avg | > 30% sustained | telemetri 1 dag |
| P5 | RAM pressure | Ingen swap thrash | OOM eller constant swap | `free -h` spot checks |
| P6 | FUSE ikke mounted (Explorer) | `mount \| grep fuse` tom | FUSE i hot path | script |
| P7 | Reboot efter bundle apply | Login ≤ 60s | > 120s | OPS-3 |

---

## 4. Legacy / FUSE (kun hvis pilot kræver det)

| ID | Metrik | Mål | Note |
|----|--------|-----|------|
| P8 | FUSE list 1000 filer | ≤ 5s | Whitelisted app only |
| P9 | FUSE vs. Builder POSIX | FUSE ≤ 3× overhead | Ellers VM/Builder path |

**Default pilot:** P8–P9 **N/A** — ingen Legacy Bridge i Fase 1.

---

## 5. VM / Legacy Runtime (Fase 2+)

| ID | Metrik | Mål |
|----|--------|-----|
| P10 | KVM slice boot → app usable | ≤ 30s |
| P11 | RDP session connect | ≤ 10s |

---

## 6. Rapportering

Én side i Fase 0 rapport:

```
PERF: P1–P7 grøn / gul / rød
FUSE i hot path: ja/nej
Anbefaling: godkend / godkend med legacy undtagelse / blokér pilot-profil
```

---

*EIRA Performance Acceptance v0.1 — opdater ved ny reference-PC eller major bundle.*
