# 🚀 Sprint 5: Detaljeret Eksekveringsplan & AI Prompts (v1.0)

**Fokus for Sprint 5 (Uge 9–10):**  
Implementering af **Multi-Device E2EE State Sync Engine (`fleetd`)**, **Merkle DAG Hash-Matching** og **Real-time WebSockets synkronisering** mellem brugerens flåde af enheder (Ubuntu PC'er, bærbare og Android-kloner).

---

## 📋 Sprint 5 To-Do Oversigt

- [ ] **Task 5.1:** Merkle DAG Hash-Tree Synkroniseringsmotor (`app/fleet/merkle_sync.py`).
- [ ] **Task 5.2:** End-to-End Encryption (E2EE) Payload Sikkerhedsmodul (`app/fleet/e2ee.py`).
- [ ] **Task 5.3:** WebSockets Real-time Sync Protocol i `fleetd` (`app/daemons/fleetd.py`).
- [ ] **Task 5.4:** Device Pairing & Public Key Exchange Registry (`app/fleet/device_registry.py`).
- [ ] **Task 5.5:** Multi-Device E2EE State Sync Integration Test Suite (`tests/test_fleet_e2ee_sync.py`).

---

## 🛠️ Detaljerede Prompts for Hver Opgave i Sprint 5

### 🔹 Task 5.1: Merkle DAG Hash-Tree Synkroniseringsmotor
**Filer:** `app/fleet/merkle_sync.py`  
**Prompt:**
```text
Du skal oprette en Merkle DAG hash-træ synkroniseringsmotor i `app/fleet/merkle_sync.py`.

Krav:
1. Implementer klassen `MerkleSyncEngine` til effektiv sammenligning af uforanderlige `State` hashkæder mellem enheder:
   - Konstruktion af Merkle-træer/DAG ud fra `State.hash` og `previous_state_id`.
   - Beregning af manglende tilstands-segmenter (diff) ved at sammenligne træ-rødder og grene.
   - Håndtering og opløsning af eventuelle tilstands-forgreninger (fork resolution).
2. Verificer med pytest, at motoren præcist identificerer manglende stater mellem to usynkroniserede databaser.
```

---

### 🔹 Task 5.2: End-to-End Encryption (E2EE) Payload Sikkerhedsmodul
**Filer:** `app/fleet/e2ee.py`  
**Prompt:**
```text
Du skal oprette et E2EE krypteringsmodul for tilstandssynkronisering i `app/fleet/e2ee.py`.

Krav:
1. Implementer `StatePayloadEncryptor` baseret på `cryptography` biblioteket (ChaCha20-Poly1305 eller AES-256-GCM):
   - Kryptering af `State.payload` før afsendelse over usikre netværk.
   - Dekryptering og integritetsvalidering på modtagende autoriserede enheder.
   - Nøgleafledning via HKDF ud fra brugerens master-parsynkroniseringsnøgle.
2. Sørg for at tilstandens unikt identificerbare metadata (`id`, `version`, `hash`) forbliver tilgængelige for Merkle-sammenligning uden at lække det krypterede indhold.
3. Skriv unit-tests der bekræfter at krypteret payload ikke kan dekrypteres med en forkert nøgle.
```

---

### 🔹 Task 5.3: WebSockets Real-time Sync Protocol i `fleetd`
**Filer:** `app/daemons/fleetd.py`  
**Prompt:**
```text
Du skal opdatere `app/daemons/fleetd.py` til at understøtte real-time WebSockets synkronisering.

Krav:
1. Tilføj en WebSockets server eller handler i `fleetd` for direkte enhed-til-enhed P2P/relay kommunikation.
2. Implementer synkroniseringssekvensen:
   - Step 1: Handshake og udveksling af Merkle Root hashes.
   - Step 2: Forespørgsel på manglende state-hashes (`sync.request_blocks`).
   - Step 3: Overførsel af E2EE krypterede tilstandsblokke (`sync.push_blocks`).
   - Step 4: Indsættelse og SHA3-256 kædevalidering i lokal `StateStore` via `stated`.
3. Verificer at synkronisering sker automatisk og asynkront ved nye tilstandstilføjelser.
```

---

### 🔹 Task 5.4: Device Pairing & Public Key Exchange Registry
**Filer:** `app/fleet/device_registry.py`  
**Prompt:**
```text
Du skal oprette et modtagelses- og enhedsregister i `app/fleet/device_registry.py`.

Krav:
1. Implementer `DeviceRegistry` til håndtering af parrede enheder i brugerens flåde:
   - Enheds-enrollment via QR-kode / engangskode.
   - Opbevaring af godkendte enheders offentlige nøgler (`public_key`), enhedsnavn, OS-type (Ubuntu, Android) og seneste heartbeat.
   - Revokering af stjålne eller forældede enheder.
2. Skriv unit-tests der bekræfter at revokerede enheder blokeres fra at sende og modtage tilstands-opdateringer.
```

---

### 🔹 Task 5.5: Multi-Device E2EE State Sync Integration Test Suite
**Filer:** `tests/test_fleet_e2ee_sync.py`  
**Prompt:**
```text
Du skal oprette en samlet integrationstestsuite i `tests/test_fleet_e2ee_sync.py`.

Krav:
1. Test følgende end-to-end synkroniseringsscenarier:
   - `test_e2ee_state_sync_between_two_devices()`: Opretter 5 tilstande på Enhed A -> synkroniserer E2EE over `fleetd` til Enhed B -> verificerer identisk SHA3-256 hashkæde.
   - `test_unauthorized_device_rejected()`: Verificer at en uparret enhed afvises under handshake.
   - `test_reconciliation_after_offline_edits()`: Verificer at to enheder, der har foretaget offline ændringer, fletter deres Merkle DAGs korrekt ved genopkobling.
2. Verificer at `pytest tests/test_fleet_e2ee_sync.py` kører med 100% succes.
```
