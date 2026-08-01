# 🚀 Sprint 4: Detaljeret Eksekveringsplan & AI Prompts (v1.0)

**Fokus for Sprint 4 (Uge 7–8):**  
Kobl **Intent Engine (`intentd`)** sammen med **`IntegratedEngine`** og **CEL (Common Expression Language) Regel-Constraints**, så forvaltningsmæssige og juridiske beslutningsregler valideres deterministisk før enhver tilstandstransformation.

---

## 📋 Sprint 4 To-Do Oversigt

- [ ] **Task 4.1:** CEL Rule Parser & Betingelses-Evaluator (`app/core/cel_evaluator.py`).
- [ ] **Task 4.2:** Intent Parser & State Proposal Generator (`app/intent_parser.py`).
- [ ] **Task 4.3:** Constraint Enforcement Engine i `intentd` (`app/daemons/intentd.py`).
- [ ] **Task 4.4:** Forvaltningsmæssigt Policy Store Modul (`app/core/policy_store.py`).
- [ ] **Task 4.5:** Intent & CEL Rule Integration Test Suite (`tests/test_intent_cel_constraints.py`).

---

## 🛠️ Detaljerede Prompts for Hver Opgave i Sprint 4

### 🔹 Task 4.1: CEL Rule Parser & Betingelses-Evaluator
**Filer:** `app/core/cel_evaluator.py`, `app/core/constraint.py`  
**Prompt:**
```text
Du skal oprette en CEL (Common Expression Language) evaluator i `app/core/cel_evaluator.py`.

Krav:
1. Implementer klassen `CELEvaluator` til sikker og deterministisk evaluering af CEL-regler over tilstande og world-state.
2. Understøt standard sammensatte udtryk:
   - Betingede tjek: `candidate.payload.amount <= 100000`
   - Rolle- & fuldmagtsvalidering: `world.actor.assurance_level == 'org_acting'`
   - Dato- og tidsfrister: `candidate.payload.due_date >= world.now`
3. Sørg for at ugyldige eller ondsindede udtryk afvises sikkert uden at afvikle ubeskyttet Python `eval`.
4. Verificer med pytest, at gyldige CEL-regler evaluerer korrekt og fejlbehæftede udtryk returnerer False.
```

---

### 🔹 Task 4.2: Intent Parser & State Proposal Generator
**Filer:** `app/intent_parser.py`  
**Prompt:**
```text
Du skal opdatere `app/intent_parser.py` til at konvertere fritekst-intentioner til uforanderlige `ProposalState` objekter.

Krav:
1. Udvid `IntentParser` til at fortolke brugerinput (fx "Opret byggetilladelse for Bygaden 12") og generere et `ProposalState` objekt med:
   - `suggested_transformation`: Navn på den ønskede handling (fx `create_building_permit`).
   - `candidate_state`: Ny forslået `State` med SHA3-256 hash.
   - `confidence_score`: AI-modellens sikkerhedsscore (0.0–1.0).
   - `rationale`: Begrundelse for forslaget.
2. Integrer mod Mistral API / lokal LLM for strukturering af ustrukturerede henvendelser.
3. Skriv en unit-test der verificerer at fritekst-input konverteres til et validt `ProposalState`.
```

---

### 🔹 Task 4.3: Constraint Enforcement Engine i `intentd`
**Filer:** `app/daemons/intentd.py`  
**Prompt:**
```text
Du skal opdatere `app/daemons/intentd.py` til at afvikle `IntegratedEngine` med tvungen CEL constraint-validering.

Krav:
1. Opdater JSON-RPC metoden `intent.execute` i `intentd`:
   - Modtag brugerens intention og generer et `ProposalState`.
   - Hent gældende CEL-constraints for transformationen fra `PolicyStore`.
   - Kør proposal igennem `IntegratedEngine.apply_proposal()`.
   - Hvis alle constraints overholdes: Tilstanden gemmes i `stated` via RPC, og hændelsen udstedes på `EventBus`.
   - Hvis en constraint overtrædes: Afvis transformationen med JSON-RPC error `-32001 (CONSTRAINT_VIOLATION)` og returner den specifikke regeltekst.
2. Skriv en integrationstest der bekræfter at afviste forslag ikke gemmes i databasen.
```

---

### 🔹 Task 4.4: Forvaltningsmæssigt Policy Store Modul
**Filer:** `app/core/policy_store.py`  
**Prompt:**
```text
Du skal oprette et forvaltningsmæssigt Policy Store i `app/core/policy_store.py`.

Krav:
1. Implementer `PolicyStore` til opbevaring og styring af CEL-regler og lovmæssige constraints pr. handlingstype.
2. Tilføj indbyggede standardregler for kommunale og offentlige sagsarbejder:
   - Beløbsgrænser for udbetalinger og bevillinger.
   - Kraver om step-up identifikation (MitID Erhverv `org_acting`).
   - Frist- og inhabilitetsregler.
3. Understøt dynamisk tilføjelse og opdatering af regler med versionering.
4. Skriv unit-tests der verificerer at regler kan gemmes, hentes og filtreres pr. transformationstype.
```

---

### 🔹 Task 4.5: Intent & CEL Rule Integration Test Suite
**Filer:** `tests/test_intent_cel_constraints.py`  
**Prompt:**
```text
Du skal oprette en samlet integrationstestsuite i `tests/test_intent_cel_constraints.py`.

Krav:
1. Test følgende end-to-end scenarier:
   - `test_intent_execution_success()`: Intention overholder alle CEL-regler -> `State` godkendes, gemmes i `stated`, og `KnowledgeEntry` oprettes.
   - `test_intent_execution_blocked_by_cel()`: Intention overtræder beløbsgrænse eller fuldmagt -> afvises med `CONSTRAINT_VIOLATION` og tilstanden ændres ikke.
   - `test_intent_step_up_escalation()`: Intention kræver `org_acting` assurance level -> returnerer krav om MitID Erhverv step-up.
2. Verificer at `pytest tests/test_intent_cel_constraints.py` kører med 100% succes.
```
