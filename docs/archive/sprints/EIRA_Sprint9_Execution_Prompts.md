# 🚀 Sprint 9: Detaljeret Eksekveringsplan & AI Prompts (v1.0)

**Fokus for Sprint 9 (Uge 17–18):**  
**OS Overlay, AppArmor Sikkerhedsprofiler, ISO Builder & Ubuntu Packaging**, der pakker EiraOS som et færdigt, installerbart Ubuntu 24.04 LTS OS-overlay.

---

## 📋 Sprint 9 To-Do Oversigt

- [ ] **Task 9.1:** AppArmor Security Profiles for EiraOS Daemons (`packaging/apparmor/usr.bin.eira-*`).
- [ ] **Task 9.2:** Debian / Ubuntu Packaging Scripts (`packaging/debian/`).
- [ ] **Task 9.3:** Live ISO Customizer & Installation Builder (`scripts/build_iso.sh`).
- [ ] **Task 9.4:** Systemd Boot & Desktop Session Integration (`packaging/session/eira-session.desktop`).
- [ ] **Task 9.5:** Live ISO & Security Profile Integration Test (`tests/test_os_packaging_security.py`).

---

## 🛠️ Detaljerede Prompts for Hver Opgave i Sprint 9

### 🔹 Task 9.1: AppArmor Security Profiles for EiraOS Daemons
**Filer:** `packaging/apparmor/usr.bin.eira-stated`, `packaging/apparmor/usr.bin.eira-identityd`  
**Prompt:**
```text
Du skal oprette AppArmor sikkerhedsprofiler for EiraOS dæmonerne under `packaging/apparmor/`.

Krav:
1. Skriv AppArmor profiler der begrænser dæmonernes adgang til kun `/run/eira/*.sock`, `/var/log/eira/` og `/data/eira.db`.
2. Bloker uautoriseret netværks- og filadgang for isolerede dæmoner.
3. Test profilerne med `apparmor_parser -q packaging/apparmor/*`.
```

---

### 🔹 Task 9.2: Debian / Ubuntu Packaging Scripts
**Filer:** `packaging/debian/control`, `packaging/debian/rules`  
**Prompt:**
```text
Du skal oprette Debian/Ubuntu pakke-scripts i `packaging/debian/`.

Krav:
1. Opret `control`, `rules` og `postinst` filer til generering af en installerbar `.deb` pakke (`eira-os-core.deb`).
```

---

### 🔹 Task 9.3: Live ISO Customizer & Installation Builder
**Filer:** `scripts/build_iso.sh`  
**Prompt:**
```text
Du skal oprette et ISO bygge-skript i `scripts/build_iso.sh`.

Krav:
1. Automatiser opbygningen af en bootbar Ubuntu 24.04 LTS Live ISO med EiraOS forudinstalleret via `cubic` / `live-build`.
```

---

### 🔹 Task 9.4: Systemd Boot & Desktop Session Integration
**Filer:** `packaging/session/eira-session.desktop`  
**Prompt:**
```text
Du skal oprette skrivebordssessions-integrationen i `packaging/session/eira-session.desktop`.

Krav:
1. Konfigurer GDM/LightDM til at starte EiraOS Calm Command UI direkte ved login.
```

---

### 🔹 Task 9.5: Live ISO & Security Profile Integration Test
**Filer:** `tests/test_os_packaging_security.py`  
**Prompt:**
```text
Du skal oprette en pakke- og sikkerhedstestsuite i `tests/test_os_packaging_security.py`.

Krav:
1. Verificer at AppArmor profiler og `.deb` pakke-manifestets afhængigheder er korrekte.
```

---

## 🔎 Audit-tilføjelse v1.1 — mangler og release-kriterier

**Vigtigt:** De oprindelige leverancer findes allerede på `main` (bl.a. `build_iso.sh`, Debian-pakkefiler og `test_os_packaging_security.py`). Filernes eksistens er ikke bevis for, at hele installations- og sikkerhedskæden er valideret. De følgende punkter supplerer — og erstatter ikke — de oprindelige opgaver.

### [P1] Task 9.6 — Afstem daemon-register med systemd og AppArmor
**Berørte filer:** `app/daemons/runner.py`, `systemd/`, `packaging/apparmor/`, `tests/test_os_packaging_security.py`

Den aktuelle pakning har systemd-units og AppArmor-profiler for seks dæmoner: `stated`, `identityd`, `fleetd`, `veritasd`, `intentd` og `graphd`. Runtime-registeret omfatter desuden `walletd`, `presenced` og `contextd`. Det skal afklares eksplicit, hvilke af de ni der er produktionsaktiverede.

**Krav:**
1. Definér én autoritativ liste over produktionsaktiverede dæmoner.
2. For hver aktiveret dæmon skal der være en passende systemd-unit, least-privilege AppArmor-profil og installation/upgrade-test.
3. Dæmoner uden produktionsimplementering må ikke fremstå som aktive produktionsfunktioner; deaktivér dem eller markér dem eksplicit som prototype.
4. Tilføj en test, der fejler ved uforklaret forskel mellem daemon-register, pakkeindhold, systemd-units og AppArmor-profiler.

**Accept:** Testen kontrollerer hele den definerede produktionsliste — ikke kun de seks nuværende profiler — og alle profiler parser uden fejl på Ubuntu 24.04.

### [P1] Task 9.7 — Test den installerede pakke, ikke kun filernes indhold
**Berørte filer:** `scripts/build_deb.sh`, `packaging/debian/`, `tests/test_os_packaging_security.py`

Den eksisterende pakke-/sikkerhedstest kontrollerer primært statiske filkrav. Det dokumenterer ikke i sig selv, at pakken kan installeres, opgraderes og afinstalleres korrekt på en ren Ubuntu 24.04-maskine.

**Krav:**
1. Byg `.deb` i et rent Ubuntu 24.04-miljø og kontrollér `dpkg-deb --info` samt manifestets afhængigheder.
2. Test install, upgrade og remove/purge i en VM/container med systemd/AppArmor-understøttelse, hvor det er muligt.
3. Kontrollér ejerskab og mode for sockets, konfiguration, trust anchors, database, log- og backupmapper; hemmeligheder må ikke ende i world-readable filer.
4. Bekræft, at installation ikke downloader eller installerer Python-pakker via `pip` eller vilkårlige netværksscripts.
5. Gem kommandoer, exit-koder og versionsoplysninger som release-evidens.

**Accept:** Ingen skjulte afhængigheder fra udviklermaskinen; install/upgrade/remove-testene er grønne, og eventuelle miljøbegrænsninger rapporteres som ikke-kørte tests — ikke som beståede tests.

### [P1] Task 9.8 — Live ISO boot- og installations-smoketest
**Berørte filer:** `scripts/build_iso.sh`, `packaging/session/`, `tests/test_os_packaging_security.py`

De statiske assertions om ISO-builderen beviser ikke, at det genererede ISO faktisk booter, starter den tilsigtede session eller holder dæmonerne inde i de tilsigtede sikkerhedsprofiler.

**Krav:**
1. Byg ISO fra den aktuelle commit og registrér SHA-256/SHA3-256, builder-version og base-image.
2. Boot ISO i en Ubuntu 24.04-kompatibel VM; verificér login/session, `eira.target`, daemon health, socket permissions og AppArmor-status.
3. Test en ren installation og genstart; kontrollér at services kommer op uden udviklingsfiler eller hemmeligheder fra build-host.
4. Skeln mellem automatiske statiske tests og VM-/hardwaretests, som faktisk er kørt.

**Accept:** RC kan ikke erklæres installationsklar alene på baggrund af, at ISO-filen blev genereret eller dens TOC kan læses.

### [P2] Task 9.9 — Reproducerbar og sporbar pakning
**Berørte filer:** `scripts/build_deb.sh`, `scripts/build_iso.sh`, `scripts/release_rc1.sh`

**Krav:**
1. Dokumentér låste/base-versioner og inputartefakter for build.
2. Gem manifest med commit-SHA, værktøjsversioner, artefakt-hashes og testresultater.
3. Kontrollér at releaseartefakter og signatur verificeres fra en ren mappe; ingen test må være markeret bestået, hvis den blev sprunget over.
4. Registrér kendte ikke-reproducerbare dele af ISO-buildet, hvis bit-for-bit reproducerbarhed ikke kan opnås.

**Accept:** En uafhængig reviewer kan knytte hver artefakt til commit, build-inputs og faktisk testbevis.
