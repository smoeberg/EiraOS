# 🚀 Sprint 3: Detaljeret Eksekveringsplan & AI Prompts (v1.0)

**Fokus for Sprint 3 (Uge 5–6):**  
In-process integration af **Veritas Shield (Lag 1–3)**, **C2PA Medie-Integritetsvalidering** og **QEAA eIDAS 2.0 Afsendersignaturer** direkte i `veritasd`.

---

## 📋 Sprint 3 To-Do Oversigt

- [ ] **Task 3.1:** Veritas Shield Lag 1 Rule Engine (`app/veritas/layer1_rules.py`).
- [ ] **Task 3.2:** eIDAS 2.0 QEAA / EUDI Wallet Signature Verifier (`app/veritas/layer2_qeaa.py`).
- [ ] **Task 3.3:** Temporal Knowledge Graph Provenance Engine (`app/veritas/layer3_graph.py`).
- [ ] **Task 3.4:** C2PA Hardware & AI Media Integrity Validation Module (`app/veritas/c2pa_engine.py`).
- [ ] **Task 3.5:** Veritas Daemon Handler & Integration Test Suite (`app/daemons/veritasd.py` & `tests/test_veritas_shield.py`).

---

## 🛠️ Detaljerede Prompts for Hver Opgave i Sprint 3

### 🔹 Task 3.1: Veritas Shield Lag 1 Rule Engine
**Filer:** `app/veritas/layer1_rules.py`  
**Prompt:**
```text
Du skal oprette Veritas Shield Lag 1 regelmotoren i `app/veritas/layer1_rules.py`.

Krav:
1. Implementer en regelbaseret analyserelateret klasse `Layer1RulesEngine`.
2. Motoren skal analysere indkommende tekst/dokumenter ud fra regelbaserede parametre:
   - Kilde-domæne og URL-troværdighed (whitelist/blacklist).
   - Tekstuel konsistens, sproglige markører, sensationalisme og sprogmønstre.
   - Forfatter- og udgiver-verifikation.
3. Beregn en del-score mellem 0.0 og 1.0 samt en liste over identificerede risikofaktorer (`flags`).
4. Verificer med pytest, at regelmotoren evaluerer kendte kilder korrekt.
```

---

### 🔹 Task 3.2: eIDAS 2.0 QEAA / EUDI Wallet Signature Verifier
**Filer:** `app/veritas/layer2_qeaa.py`  
**Prompt:**
```text
Du skal oprette Lag 2 EUDI Wallet / QEAA afsendersignatur-validering i `app/veritas/layer2_qeaa.py`.

Krav:
1. Implementer klassen `QEAA Verifier` til validering af digitale kilde-signaturer ifølge eIDAS 2.0 standarden:
   - Validering af W3C Verifiable Credentials (VC) og SD-JWT formater.
   - Verifikation af eIDAS Qualified Electronic Attestation of Attributes (QEAA).
   - Tjek af udstederens certifikatkæde mod EU Trusted List (EUTL).
2. Beregn en kryptografisk tillidsscore (0.0 til 1.0) og returner certifikatdetaljer.
3. Skriv en unit-test der verificerer at gyldige QEAA signaturer godkendes og manipulerede signaturer afvises.
```

---

### 🔹 Task 3.3: Temporal Knowledge Graph Provenance Engine
**Filer:** `app/veritas/layer3_graph.py`  
**Prompt:**
```text
Du skal oprette Lag 3 proviens- og narrativ-analysen i `app/veritas/layer3_graph.py`.

Krav:
1. Implementer `Layer3GraphEngine` der integrerer mod EiraOS's Temporal Knowledge Graph (`graphd`):
   - Analyse af påstandens oprindelse og tidsmæssige udvikling i grafen.
   - Detektion af modstridende påstande over tid (temporal modstrid).
   - Netværksanalytisk verifikation af kildens historiske pålidelighed.
2. Returner en proviens-score (0.0–1.0) samt grafiske relatiosn-links.
3. Verificer med pytest at modstridende historiske påstande sænker proviens-scoren.
```

---

### 🔹 Task 3.4: C2PA Hardware & AI Media Integrity Validation Module
**Filer:** `app/veritas/c2pa_engine.py`  
**Prompt:**
```text
Du skal oprette C2PA medie-integritetsmotoren i `app/veritas/c2pa_engine.py`.

Krav:
1. Implementer klassen `C2PAEngine` til analyse af billeder, lyd og video:
   - Udlæsning og verifikation af C2PA / CAI (Content Authenticity Initiative) manifester i mediefiler.
   - Kontrol af hardware-signaturer (fx fra kamera-sensorer).
   - AI-genereringsdetektion (markering af AI-genereret eller manipulerede billeder uden C2PA manifest).
2. Beregn en medie-integritetsscore (0.0–1.0) og returner C2PA manifest-data.
3. Skriv en test med prøve-billeder/mock-data der verificerer korrekt udlæsning af manifestet.
```

---

### 🔹 Task 3.5: Veritas Daemon Handler & Integration Test Suite
**Filer:** `app/daemons/veritasd.py`, `tests/test_veritas_shield.py`  
**Prompt:**
```text
Du skal opdatere `app/daemons/veritasd.py` til at samle Lag 1–3 og C2PA i en samlet Trust Score (0–100%).

Krav:
1. Implementer JSON-RPC metoden `veritas.evaluate` i `veritasd`:
   - Vægtet beregning: $Trust = (0.3 \cdot L1) + (0.35 \cdot L2) + (0.2 \cdot L3) + (0.15 \cdot C2PA)$.
   - Generering af et samlet Veritas HUD certifikat og forklaring (`rationale`).
2. Skriv en komplet integrationstest i `tests/test_veritas_shield.py`, der tester `veritas.evaluate` over IPC med forskellige tekst- og medie-inputs.
3. Verificer at `pytest tests/test_veritas_shield.py` kører med 100% succes.
```
