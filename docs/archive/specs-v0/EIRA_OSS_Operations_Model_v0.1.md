# EIRA OSS Operations Model v0.1

**Status:** Normativ — drift, QA, bundle-team  
**Dato:** 4. juli 2026  
**Formål:** Eksplicit ejerskab, opdatering og overvågning af open source-komponenter i EIRA OS Bundle  
**Relateret:**
- [EIRA_OSS_Integration_Manifest_v0.1.md](EIRA_OSS_Integration_Manifest_v0.1.md)
- [EIRA_Update_Release_Train_v0.1.md](../../eira-fleet-control/docs/specs/EIRA_Update_Release_Train_v0.1.md)
- [EIRA_Strategic_Reality_Check_v0.1.md](EIRA_Strategic_Reality_Check_v0.1.md) §11
- [EIRA_EDR_Partner_Requirements_v0.1.md](EIRA_EDR_Partner_Requirements_v0.1.md)

---

## 1. Kernebeslutning

> **IT opgraderer ikke "Ubuntu" og "Wazuh" separat. IT godkender EIRA OS Bundles.**

EIRA ejer **orkestrering, QA, pinning og release** af hele OSS-stacken. Canonical, Wazuh, CNCF m.fl. ejer **upstream** — EIRA ejer **certificeringen** af kombinationen.

---

## 2. Ejerskabsmodel (RACI)

| Aktivitet | Canonical / upstream | Kunde IT | EIRA |
|-----------|---------------------|----------|------|
| Ubuntu security patches (USN) | **R** | I | **A** — QA + bundle |
| EIRA-native binaries | — | I | **R/A** |
| OSS agent config (Wazuh, Falco, sssd) | C | I | **R/A** |
| Bundle publish til Update Repository | — | I | **R/A** |
| Staged rollout til endpoints | — | **A** | R — governance-agent |
| Emergency CVE response | C | I | **R/A** |
| L0 support (kernel, CUPS, driver) | **R** (Ubuntu Pro) | **A** | C — triage |
| L1 support (EIRA platform) | — | I | **R/A** |
| Kommerciel EDR agent | Vendor **R** | **A** (kontrakt) | **A** — bundle pin + QA |

**R** = Responsible, **A** = Accountable, **C** = Consulted, **I** = Informed

---

## 3. Komponent-ejerskab (CORE bundle)

| Komponent | Upstream | EIRA ejerskab | Overvågning |
|-----------|----------|---------------|-------------|
| **Ubuntu LTS + linux-firmware** | Canonical | Pin i `package-list.lock`; QA per bundle | USN RSS, `ubuntu-security-announce` |
| **sssd / realmd** | SSSD project + Ubuntu | Config templates, AD-join policy | Ubuntu security + SSSD releases |
| **NetworkManager + VPN plugins** | GNOME/Ubuntu | VPN profile compiler | Ubuntu security |
| **Wazuh agent** | Wazuh Inc. | Manager URL, rules, localfile for Intent Audit | Wazuh security advisories |
| **Falco** | CNCF | `falco_rules.local.yaml` fra policy | Falco GitHub security |
| **auditd** | Linux audit | Ruleset + Intent correlation | Ubuntu security |
| **AppArmor** | Ubuntu | `eira-*` profiler | Ubuntu security |
| **osquery** | osquery project | Scheduled queries fra Fleet | osquery releases |
| **fwupd / LVFS** | LVFS | Inventory integration | fwupd CVE |
| **OpenConnect / openfortivpn** | Community | VPN matrix test | Ubuntu + upstream |
| **ClamAV** | Cisco Talos sigs | Update channel pin | ClamAV + Ubuntu |

**Regel:** Ingen komponent opdateres på managed endpoints uden for bundle — governance-agent håndhæver `apt` hold/pin.

---

## 4. Opdateringsflow

```
Upstream CVE / release
        │
        ▼
EIRA Security triage (≤ 24t for kritisk)
        │
        ├── Ikke relevant for bundle → log + close
        │
        └── Relevant → opret bundle branch
                │
                ▼
        QA på reference-PC (24–72t)
          • health probes (manifest)
          • smoke: Entra, VPN, Wazuh, Intent Audit
          • regression: Explorer boot
                │
                ▼
        Sign bundle → publish kanal (stable / emergency)
                │
                ▼
        Staged rollout: 5% → 20% → 100%
                │
                ▼
        Fleet compliance % opdateret
```

### 4.1 SLA-mål (pilot → produktion)

| Severity | Eksempel | Mål: certificeret bundle |
|----------|----------|--------------------------|
| **Kritisk** | Kernel RCE, OpenSSH 0-day | 7 dage (pilot) → 72t (produktion) |
| **Emergency** | Aktivt udnyttet i wild | 4t mål — accelereret QA |
| **Høj** | Privilege escalation i sssd | Næste security bundle (ugentlig) |
| **Medium** | Falco false-positive fix | Næste security eller feature bundle |
| **Low** | Minor dep update | Feature bundle (månedlig) |

---

## 5. Overvågning (upstream)

| Kilde | Frekvens | Ejer | Handling |
|-------|----------|------|----------|
| Ubuntu USN | Daglig (automatiseret) | EIRA security | Triage ticket |
| Wazuh security advisories | Ugentlig | EIRA security | Pin review |
| Falco / CNCF | Ugentlig | EIRA security | Rules update |
| NVD CVE (kurateret liste) | Daglig | EIRA security | Match mod `package-list.lock` |
| Microsoft Entra / Graph API changes | Månedlig | Identity team | Connector regression |
| EDR vendor release notes | Ved vendor publish | EIRA + partner | Bundle slot update |

**Værktøj (mål):** `eira-cve-watch` — script der diff'er `package-list.lock` mod USN + NVD; output til Fleet security dashboard.

---

## 6. Bundle QA-checkliste (obligatorisk før publish)

| # | Check | Automatiseret |
|---|-------|---------------|
| 1 | `package-list.lock` signeret og hash match | ✅ |
| 2 | Alle `health_probe` i manifest grønne | ✅ CI |
| 3 | Reference-PC boot + Explorer login | ✅ CI + manuel |
| 4 | Entra OIDC + step-up | ✅ smoke |
| 5 | Wazuh event modtaget | ✅ smoke |
| 6 | Intent Audit CEF i SIEM | ✅ smoke |
| 7 | VPN connect (hvis profil i test) | Manuel |
| 8 | Bundle apply + rollback (btrfs) | ✅ CI |
| 9 | Parity matrix opdateret i manifest | Manuel |
| 10 | Release notes + CVE-liste publiceret | Manuel |

---

## 7. Versionering og kanaler

| Kanal | Indhold | Målgruppe |
|-------|---------|-----------|
| `emergency` | Kritisk CVE only | IT godkender accelereret |
| `stable` | Security + EIRA patch | Alle managed endpoints |
| `feature` | Minor EIRA + udvalgte Ubuntu updates | IT godkendt månedlig |
| `lts-migration` | Ny Ubuntu LTS + EIRA major | Planlagt 6–12 mdr projekt |

**IT ser én linje:**

> Bundle `2026.07.04-stable` — 12 Ubuntu-patches (1 kritisk) + EIRA 2.4.1 + Wazuh agent 4.9.x — [Rollout 5%]

---

## 8. Konflikter og afhængigheder

| Risiko | Mitigation |
|--------|------------|
| Ubuntu opdaterer sssd — bryder Entra login | Pin indtil QA; regression test OIDC |
| Falco kernel module vs. ny kernel | Bundle tester **hele** stack; hold kernel metapackage |
| Wazuh + kommerciel EDR konflikt | [EDR Requirements](EIRA_EDR_Partner_Requirements_v0.1.md) §6 — 72t soak |
| OpenConnect vs. NetworkManager version | VPN matrix re-test ved NM bump |
| Snap/Flatpak uden for bundle | Policy: kun EIRA-godkendte remotes |

---

## 9. Kunde med Ubuntu Pro

| Model | Drift |
|-------|-------|
| **Bundtet (anbefalet)** | EIRA inkluderer Ubuntu Pro; én support-matrix |
| **Kunde ejer Ubuntu Pro** | EIRA koordinerer CVE-triage; kunde eskalerer L0 til Canonical |

EIRA **abonnerer ikke** på behalf of customer uden kontrakt — men bundle **testes** mod Ubuntu Pro-pinned repos.

---

## 10. Dokumentation per bundle

Hver publish **skal** inkludere:

```json
{
  "bundle_id": "eira-bundle-2026.07.04-stable",
  "cve_resolved": ["USN-XXXX-X"],
  "oss_components_bumped": [
    {"id": "wazuh-agent", "from": "4.8.2", "to": "4.9.0"},
    {"id": "falco", "from": "0.37.1", "to": "0.38.0"}
  ],
  "parity_matrix_delta": {"vpn": "yellow→green"},
  "rollback_tested": true,
  "qa_reference_pc": "ThinkPad T14 Gen 5"
}
```

---

## 11. Team og roller (minimum viable)

| Rolle | Ansvar | FTE (pilot) |
|-------|--------|-------------|
| **Bundle lead** | QA, publish, CVE triage | 0.5 |
| **Identity/OSS** | sssd, Entra, VPN regression | 0.25 |
| **Security** | Wazuh, Falco, EDR slot, Intent Audit | 0.25 |
| **Fleet** | Rollout, compliance dashboard | 0.25 (fleet-control) |

Ved skala (1000+ PC): dedikeret security + bundle CI.

---

## 12. Forhold til Windows-opdateringer

EIRA **jagter ikke** Windows Update 1:1. EIRA jagter **sårbarheds-exposure** på EIRA endpoints.

| Windows event | EIRA respons |
|---------------|--------------|
| Microsoft Patch Tuesday | Review om Ubuntu/USN allerede dækker tilsvarende CVE |
| Ny Windows EDR feature | Vurder paritetspunkt 4 — partner roadmap |
| Windows 11 hardware krav | Opdater Support Matrix — ikke EIRA scope |

---

## 13. Beslutninger

| # | Beslutning | Deadline |
|---|------------|----------|
| 1 | `eira-cve-watch` script i CI — ja/nej | Sprint 1 |
| 2 | Ugentlig security bundle cadence — bekræft | Nu |
| 3 | Ubuntu Pro bundtet i pilot-pris — ja/nej | Salg uge 4 |

---

*EIRA OSS Operations Model v0.1 — opdater ved ændring i bundle-proces eller SLA.*
