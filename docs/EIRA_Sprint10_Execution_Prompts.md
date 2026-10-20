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

---

## 🔎 Audit-tilføjelse v1.1 — konkrete release-blokkere og manglende bevis

**Status ved gennemgang:** De fem oprindelige leverancer findes allerede på `main`. Det betyder ikke, at alle sikkerhedskrav er opfyldt. Nedenstående punkter er baseret på læsning af den aktuelle `main`; der er ikke kørt test-suite i denne dokumentationsgennemgang.

### [P0 / release blocker] Task 10.6 — Step-up må ikke hæve assurance på en vilkårlig streng
**Berørte filer:** `app/daemons/identityd.py`, `app/session_store.py`, identity/OIDC tests.

**Bekræftet adfærd:** `identity_step_up()` kontrollerer, at `step_up_token` eller `challenge_response` er ikke-tom, og kalder derefter `update_assurance()`. Den validerer ikke tokenet kryptografisk eller binder det til en gennemført MitID Erhverv-authentication, den konkrete bruger og den konkrete session.

**Krav:**
1. Fjern direkte assurance-opgradering baseret på ikke-tomt input. En klientleveret streng må aldrig være bevis på autentifikation.
2. Kræv en server-verificeret authentication result/assertion fra en konfigureret provider, med issuer, audience/client, subject, nonce/state, tidsgrænser og korrekt assurance-niveau valideret.
3. Bind resultatet til den autentificerede actor og eksisterende session; afvis replay, udløb, forkert actor, forkert session og provider mismatch.
4. Tillad kun eksplicit definerede assurance-værdier og transitions; afvis vilkårlige værdier fra klienten.
5. Hvis verifikation eller obligatorisk audit fejler, må assurance ikke ændres.

**Accepttests:** tom og vilkårlig token, falsk signatur, udløbet assertion, replay, anden actor/session og ugyldigt assurance-niveau afvises; sessionens assurance forbliver uændret. Kun en gyldig provider-verificeret testassertion kan hæve assurance.

### [P0 / release blocker] Task 10.7 — Wallet må ikke simulere betaling eller samtykke som gennemført
**Berørte filer:** `app/daemons/walletd.py`, wallet/payment tests, release gate.

**Bekræftet adfærd:** Den aktuelle `WalletDaemon.optimize_and_pay()` returnerer `status: "PAID"` og `eudi_consent_verified: True` uden at kalde en betalingsudbyder eller verificere samtykke. `list_credentials()` returnerer ligeledes hårdkodede credentials som `VALID`.

**Krav:**
1. Indtil en rigtig, verificeret providerintegration findes, skal betalings- og credential-operationer returnere en tydelig `unsupported/not_configured` status — aldrig `PAID`, `VALID` eller verificeret samtykke.
2. Bind betaling til en autentificeret bruger/session, beløb, valuta, merchant, idempotency key og provider-transaktions-ID.
3. Verificér brugerens samtykke gennem en betroet protokol og auditér både afvisning og succes.
4. Release gate skal fejle, hvis produktionskonfigurationen peger på stub/mock-adfærd.

**Accepttests:** ingen provider/consent = ingen successtatus; afvist/timeout/dobbelt request må ikke skabe falsk betaling; credential-status skal komme fra verificeret providerrespons.

### [P1] Task 10.8 — Session- og actor-binding samt session fixation
**Berørte filer:** `app/daemons/identityd.py`, `app/session_store.py`, OIDC callback og session tests.

**Bekræftet adfærd:** Identity RPC tager `session_id` og `actor_id` fra parametre; `ensure_session()` opretter en session, hvis ID'et ikke findes, og sætter som standard actor til `anonymous`. Det er ikke en tilstrækkelig grænse mellem en klientleveret session-id og en serverautentificeret identitet.

**Krav:**
1. Session-ID skal udstedes af serveren efter autentifikation og være uforudsigeligt; en ukendt klientleveret ID må ikke automatisk blive til en privilegeret session.
2. Autorisation skal hente actor fra serverens autentificerede session, ikke stole på `actor_id` i RPC-parametre.
3. Opret ny session/rotér session-ID ved login og step-up; bind den til stabil provider-identitet og tenant.
4. Afvis forsøg på at læse/opgradere en anden brugers session; tilføj udløb og logout/revokering.

**Accepttests:** klientvalgt ID, actor spoofing, genbrug af pre-login ID og krydsbruger-sessionadgang afvises.

### [P1] Task 10.9 — OIDC key rotation, claims og stabil identitet
**Berørte filer:** `app/auth/oidc.py`, `tests/test_oidc_jwks_verification.py`, `tests/test_oidc_mock_security.py`.

**Observerede gaps i den aktuelle implementering:** claim-valideringen kontrollerer issuer, audience, expiration og nonce når en nonce er givet, men kontrollerer ikke `nbf`/`iat`. En ukendt `kid` giver fejl uden et eksplicit tvunget JWKS-refresh. Sessionens actor-ID udledes primært af email/preferred username, som kan ændres.

**Krav:**
1. Valider `nbf` og `iat` med begrænset clock skew; afvis fremtidige, udløbne eller urimelige tidsclaims.
2. Ved ukendt `kid`: foretag højst ét kontrolleret JWKS-refresh og genprøv; beskyt mod gentagne netværkskald/DoS.
3. Brug stabil provider-subject-identitet og tenant (fx `tid` + `oid` for Entra, eller valideret `iss` + `sub`), ikke email som primær nøgle.
4. Kræv nonce for live OIDC-flow, og test nonce mismatch/replay, key rotation, forkert tenant, forkert audience og issuer mismatch.
5. Bevar fast algoritmepolitik og afvis algoritmer/nøgletyper, som ikke eksplicit er understøttet.

**Accept:** negative tests beviser afvisning; key rotation fungerer uden at acceptere en ugyldig signatur.

### [P1] Task 10.10 — Fail-closed fleet-sync og tværsproglig hash-paritet
**Berørte filer:** `app/daemons/fleetd.py`, `tests/test_fleet_e2ee_sync.py`, `tests/test_fleet_sync.py`, Android `StateEntity.kt` og fælles testvektorer.

**Bekræftet blocker:** `FleetSyncService.push_blocks()` tæller ugyldige envelopes, men fortsætter med at persistere de gyldige elementer i samme batch. En blandet batch kan derfor ændre tilstanden delvist. Det er ikke reject-all fail-closed.

**Uafklaret verifikationsgap:** Android Room-hashinput bygger på `JSONObject.toString()`; byte-for-byte paritet med Python/native canonical state er ikke demonstreret for de delte edge-case-vektorer.

**Krav:**
1. Validér/dekryptér hele batchen før mutation; hvis ét element er ugyldigt, afvis hele batchen og lad state, Merkle root og audit-tilstand være uændret.
2. Tilføj regressionstest med valid + invalid envelope i samme batch, og verificér nul mutation.
3. Få Room-hashvejen til at bruge den fælles kanoniske kontrakt; kør samme fixtures for Unicode, dyb nesting, store heltal over 2^53, floats og JSON-typer på Python, native og Android.
4. Release gate skal kræve præcis hash-paritet, ikke blot at relevante filer eller testklasser eksisterer.

**Accept:** reject-all testen fejler før fix og består efter fix; samtlige delte hashvektorer matcher byte-for-byte.

### [P1] Task 10.11 — Shared-memory IPC: concurrency og procesgrænse
**Berørte filer:** `crates/eira-ipc/src/shm.rs`, `crates/eira-ipc/tests/shm_process.rs`, planlagt Python integrationstest.

Der findes en Rust subprocess-test for producer/consumer, men den dokumenterer ikke alene alle de krævede scenarier: format-version mismatch, stale segment, korruption og race under samtidige publish/read.

**Krav:**
1. Tilføj integrationstest, der afviser versionsmismatch og stale/ikke-ready segmenter.
2. Simulér korrupt header/payload og digest mismatch; verificér fail-closed uden at returnere payload.
3. Test samtidig publish/read og dokumentér den konkrete snapshot-/generation-garanti; læseren må ikke bruge data, der ændres efter validering.
4. Test cleanup af segmenter efter succes, fejl og child-process-crash; undgå at unlinke et segment, der ejes af en anden aktiv writer.
5. Tilføj `tests/test_ipc_shm.py` kun hvis Python↔Rust-grænsen faktisk går gennem denne testvej; ellers placér testen dér, hvor den virkelige integration sker.

**Accept:** procesgrænse-, mismatch-, stale-, corruption- og race-tests køres i CI på understøttet Linux-miljø og rapporteres separat fra tests, der ikke kan køre på platformen.

### [P1] Task 10.12 — Final gate skal bevise adfærd, ikke kun filnavne
**Berørte filer:** `tests/test_final_pilot_gatekeeping.py`, `scripts/release_rc1.sh`.

Den nuværende final-gate-test kontrollerer hovedsageligt, at filer og bestemte tekststrenge findes. Det beviser ikke, at alle sikkerhedsgarantier overholdes, og formuleringen “100%” kan ikke dokumenteres af en sådan test.

**Krav:**
1. Behold billige strukturtests, men supplér med adfærdstests for step-up, session binding, wallet stub, fail-closed sync, OIDC negative cases, IPC og backup/restore.
2. Release rapporten skal vise præcist hvilke tests der bestod, fejlede eller blev sprunget over, inklusive årsag.
3. Kræv at alle P0 release blockers er lukket med testbevis; ingen blanketpåstand om nul sårbarheder.
4. Verificér signatur og manifest fra en ren outputmappe, og bevar commit-SHA, testlog, artefakthashes og buildmiljø.

**Accept:** RC1 kan ikke godkendes, hvis en P0 er åben, en obligatorisk test blev sprunget over, eller kun statiske filchecks er tilgængelige som bevis.
