# 🚀 Sprint 10: Detaljeret Eksekveringsplan & AI Prompts (v1.0)

**Fokus for Sprint 10 (Uge 19–20):**  
**Production Hardening, Penetrationstesting, Disaster Recovery & Pilot Release RC1 Gatekeeping**.

---

## 📋 Sprint 10 To-Do Oversigt

- [ ] **Task 10.1:** Full System Penetration & Security Audit Suite (`tests/test_pen_audit_security.py`).
- [ ] **Task 10.2:** EUDI Wallet & MitID Erhverv Production Certificate Verifier (`app/auth/production_cert_verifier.py`).
- [ ] **Task 10.3:** Disaster Recovery & SQLite WAL Backup Engine (`scripts/disaster_recovery_backup.py`).
- [ ] **Task 10.4:** Pilot Release Candidate Packaging & Sign-off Script (`scripts/release_rc1.sh`).
- [ ] **Task 10.5:** Final End-to-End Acceptance Test & Verification (`tests/test_final_pilot_gatekeeping.py`).

---

## 🛠️ Detaljerede Prompts for Hver Opgave i Sprint 10

### 🔹 Task 10.1: Full System Penetration & Security Audit Suite
**Filer:** `tests/test_pen_audit_security.py`  
**Prompt:**
```text
Du skal oprette en penetrations- og sikkerhedstestsuite i `tests/test_pen_audit_security.py`.

Krav:
1. Simuler timing-angreb, SHA3-256 forfalskning, og uautoriserede IPC socket forbindelser.
2. Bekræft 0 ubeskyttede sårbarheder i systemet.
```

---

### 🔹 Task 10.2: EUDI Wallet & MitID Erhverv Production Certificate Verifier
**Filer:** `app/auth/production_cert_verifier.py`  
**Prompt:**
```text
Du skal oprette produktions-certifikatvalidering for MitID Erhverv og EUDI Wallet i `app/auth/production_cert_verifier.py`.

Krav:
1. Implementer verifikation af OIDC production endpoints, X.509 certifikatkæder og CRL/OCSP revokering.
```

---

### 🔹 Task 10.3: Disaster Recovery & SQLite WAL Backup Engine
**Filer:** `scripts/disaster_recovery_backup.py`  
**Prompt:**
```text
Du skal oprette et Disaster Recovery backup-modul i `scripts/disaster_recovery_backup.py`.

Krav:
1. Implementer hot online-backup af SQLite WAL databasen uden nedetid samt automatisk punkt-i-tid genoprettelse (PITR).
```

---

### 🔹 Task 10.4: Pilot Release Candidate Packaging & Sign-off Script
**Filer:** `scripts/release_rc1.sh`  
**Prompt:**
```text
Du skal oprette release candidate skriptet i `scripts/release_rc1.sh`.

Krav:
1. Byg og signer den endelige EiraOS v1.0-RC1 release bundle med GPG signatur.
```

---

### 🔹 Task 10.5: Final End-to-End Acceptance Test & Verification
**Filer:** `tests/test_final_pilot_gatekeeping.py`  
**Prompt:**
```text
Du skal oprette den endelige pilot-godkendelsestest i `tests/test_final_pilot_gatekeeping.py`.

Krav:
1. Verificer at alle 10 sprints og samtlige dæmoner, UI-komponenter og sikkerhedsgarantier overholdes 100%.
```
