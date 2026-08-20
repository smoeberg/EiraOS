# EiraOS WinApp — Development & Release Guide

Dette dokument beskriver arkitekturen, byggeprocessen og release-pipelinen for **EiraOS WinApp** (den native Windows-skrivebordsklient baseret på Tauri v2 og Rust).

---

## 🏗️ 1. Arkitektur og Komponenter

- **UI / Frontend (`ui/`)**: React 19, TypeScript, Vite og Tailwind-agtig Spatial Canvas. Kommunikerer med backend via Tauri v2 IPC.
- **Tauri Shell (`ui/src-tauri`)**: Rust 2024 edition, Tauri v2 core, native system tray, sikkerhedsramme og lokal kryptering.
- **Rust Backend Workspace (`crates/`)**: `eira-core`, `eira-ipc`, og `eira-stated` som leverer lokal state, daemon-forbindelser og temporal graph-håndtering.

---

## 🛠️ 2. Lokal Udvikling & Byg

For at køre og bygge WinApp lokalt (f.eks. på en Windows-maskine eller via CI):

```bash
# 1. Gå til UI-mappen og installer afhængigheder
cd ui
pnpm install

# 2. Start lokal udviklingsserver med Tauri hot-reload
pnpm tauri dev

# 3. Byg produktionsudgave af frontend
pnpm build
```

---

## 🚀 3. Automatisk Windows Packaging (GitHub Actions)

Der er oprettet en automatisk workflow-pipeline i `.github/workflows/winapp-release.yml`, som:
1. Sætter Node.js og Rust op på `windows-latest`.
2. Installerer pnpm og bygger frontend.
3. Kører `tauri-action` til at kompilere den native Windows-applikation.
4. Genererer installationsfiler:
   - **MSI Installer** (`.msi`) til enterprise-distribution.
   - **NSIS Web/Standalone Installer** (`.exe`).
5. Uploader automatisk artefakterne til GitHub Releases og som workflow-artefakter.

---
*Udgivet til EiraOS — Spatial Workspace Platform.*
