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
