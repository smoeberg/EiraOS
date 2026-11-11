# 🚀 Sprint 2: Detaljeret Eksekveringsplan & AI Prompts (v1.0)

**Fokus:** Systemd Integration, Unix Socket Isolation (`/run/eira/*.sock`) & Rettighedsstyring (`0660`).

---

## 📋 Sprint 2 To-Do Oversigt

- [ ] **Task 2.1:** Systemd Service Unit Filer (`systemd/eira-*.service`) for alle IPC dæmoner.
- [ ] **Task 2.2:** Unix Socket Sikkerheds- & Rettighedsmodul (`app/ipc/socket_security.py`).
- [ ] **Task 2.3:** Socket Activated Daemon Runner & Lifecycle Engine (`app/daemons/runner.py`).
- [ ] **Task 2.4:** Automated Systemd Deployment & Installation Script (`scripts/deploy_systemd.sh`).
- [ ] **Task 2.5:** End-to-End Socket Permissions & Security Integrationstest (`tests/test_socket_permissions.py`).

---

## 🛠️ Detaljerede Prompts for hver Opgave i Sprint 2

### 🔹 Task 2.1: Systemd Service Unit Filer
**Filer:** `systemd/eira-stated.service`, `systemd/eira-identityd.service`, `systemd/eira-fleetd.service`, `systemd/eira-veritasd.service`, `systemd/eira-intentd.service`, `systemd/eira-graphd.service`, `systemd/eira.target`  
**Prompt:**
```text
Du skal oprette produktionsklare systemd unit-filer for EiraOS IPC dæmonerne under `systemd/`.

Krav:
1. Opret følgende `.service` filer samt en samlende `eira.target`:
   - `systemd/eira-stated.service`
   - `systemd/eira-identityd.service`
   - `systemd/eira-fleetd.service`
   - `systemd/eira-veritasd.service`
   - `systemd/eira-intentd.service`
   - `systemd/eira-graphd.service`
   - `systemd/eira.target`
2. Hver service skal køre som dedikeret systembruger/gruppe `eira:eira` eller have `RuntimeDirectory=eira` (`/run/eira`).
3. Konfigurer `ExecStart` til at starte dæmonen via Python IPC runner (fx `python3 -m app.daemons.runner --daemon stated`).
4. Inkluder Linux sikkerhedshærdning i servicerne:
   - `ProtectSystem=strict`
   - `ProtectHome=true`
   - `PrivateTmp=true`
   - `CapabilityBoundingSet=` (tom for minimal priviligering)
   - `Restart=always` og `RestartSec=2s`
5. Test at unit-filerne har gyldig systemd-syntaks (`systemd-analyze verify systemd/*.service`).
```

---

### 🔹 Task 2.2: Unix Socket Sikkerheds- & Rettighedsmodul
**Filer:** `app/ipc/socket_security.py`, `app/ipc/jsonrpc.py`  
**Prompt:**
```text
Du skal oprette et Unix Socket sikkerhedsmodul i `app/ipc/socket_security.py`.

Krav:
1. Implementer funktionen `setup_unix_socket(socket_path: str, mode: int = 0o660, group: str = "eira") -> socket.socket`.
2. Sørg for at:
   - Fjerne eksisterende socket-fil hvis den findes.
   - Sætte `umask(0o117)` under oprettelse.
   - Ændre egerskab/gruppe på socket-filen via `os.chown` / `shutil.chown` til gruppen `eira` (eller fallback til nuværende GID i dev/test).
   - Anvende `os.chmod(socket_path, mode)` så kun ejer og gruppe har læse-/skriveadgang (`0660`).
3. Implementer peer credential validering (`SO_PEERCRED` på Linux) for at verificere klientens UID/GID over Unix socketen.
4. Verificer med pytest, at socket-stien oprettes med de korrekte filrettigheder og gruppe.
```

---

### 🔹 Task 2.3: Socket Activated Daemon Runner & Lifecycle Engine
**Filer:** `app/daemons/runner.py`  
**Prompt:**
```text
Du skal opdatere `app/daemons/runner.py` til at understøtte produktions-opstart af individuelle dæmoner over Unix Domain Sockets.

Krav:
1. Tilføj CLI argument-parsing via `argparse`:
   - `--daemon`: Navn på specifik dæmon der skal køre (fx `stated`, `identityd`, `fleetd`, `veritasd`, `intentd`, `graphd`, eller `all`).
   - `--socket-dir`: Sti til socket-mappe (standard: `/run/eira`).
2. Ved opstart af en dæmon skal runneren oprette en Unix Domain Socket server under `/run/eira/<daemon>.sock` med `0660` rettigheder via `socket_security.py`.
3. Implementer graciøs nedlukning (SIGINT/SIGTERM modtagelse via `signal`), som fjerner socket-filer og lukker åbne forbindelser rent.
4. Verificer at `python3 -m app.daemons.runner --daemon stated` starter `stated.sock` korrekt og reagerer på SIGTERM.
```

---

### 🔹 Task 2.4: Automated Systemd Deployment Script
**Filer:** `scripts/deploy_systemd.sh`  
**Prompt:**
```text
Du skal oprette et bash-deploymentskript i `scripts/deploy_systemd.sh` til installation af EiraOS servicerne på Ubuntu 24.04 LTS.

Krav:
1. Skriptet skal udføre følgende trin:
   - Oprette systembruger/gruppe `eira` hvis den ikke eksisterer (`groupadd -f eira` & `useradd -r -g eira eira`).
   - Oprette `/run/eira` og `/var/log/eira` med rettighederne `0770 eira:eira`.
   - Kopiere unit-filer fra `systemd/` til `/etc/systemd/system/`.
   - Genindlæse systemd dæmonen (`systemctl daemon-reload`).
   - Aktivere og starte target: `systemctl enable --now eira.target`.
2. Tilføj fejlhåndtering (`set -euo pipefail`) og tjek at skriptet afvikles som root (`sudo`).
3. Gør skriptet eksekverbart (`chmod +x scripts/deploy_systemd.sh`).
```

---

### 🔹 Task 2.5: End-to-End Socket Permissions Integrationstest
**Filer:** `tests/test_socket_permissions.py`  
**Prompt:**
```text
Du skal oprette en integrationstestsuite i `tests/test_socket_permissions.py`.

Krav:
1. Test følgende sikkerhedsaspekter for Unix Domain Sockets:
   - `test_socket_mode_permissions()`: Verificer at oprettede socket-filer i en midlertidig testmappe har nøjagtig octal mode `0o660` (rw-rw----).
   - `test_socket_cleanup_on_shutdown()`: Verificer at socket-filen automatisk slettes ved dæmon-nedlukning.
   - `test_unauthorized_user_access_blocked()`: Verificer at brugere uden for `eira` gruppen afvises af filsystemets permission-lag.
2. Verificer at `pytest tests/test_socket_permissions.py` kører med 100% succes.
```
