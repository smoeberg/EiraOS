# AI INTERFACE 1.0 — EiraOS Modelgrænseflade

**Status:** Draft (bindende for implementering)  
**Version:** 1.0  
**Gælder for:** `intentd`, AI-adaptere, EiraLang, EiraAI, fremtidige modeller  
**Relateret:** EDP 1.0, Gate Kernel 1.0, EiraOS Systembeskrivelse

---

## 1. Formål

AI Interface er EiraOS' **modeluafhængige kontrakt** mellem `intentd` og enhver sprog- eller handlingsmodel. Kontrakten sikrer, at modeller kan skiftes ud uden at ændre EDP, gaten eller UI.

**Grundregel:**

> Modellen er en parser, der foreslår. Den er ikke en executor, og den kender ikke til transport, rettigheder eller system-API'er.

---

## 2. Arkitekturprincip

AI-laget består af to komponenter med hver sit ansvar:

```text
Brugerens input
    → EiraLang (sprogforståelse + oversættelse)
        → IntentExtraction (mellemformat)
            → EiraAI (opgaveplanlægning + handlingsforslag)
                → EdpAction (rå forslag)
                    → GATE KERNEL
```

**EiraLang** udtrækker intention og entiteter. Den kender ikke EDP.  
**EiraAI** omsætter intentionen til EDP-handlinger. Den kender EDP, men ikke transport eller autorisation.  
**Gaten** validerer, autoriserer og udfører.

Ingen af komponenterne må kalde en executor direkte.

---

## 3. Kontrakten

### 3.1 EiraLang — `extract_intent()`

```text
extract_intent(
    text: str,
    context: ConversationContext,
    language_hint: str | None
) -> IntentExtraction | Abstain | Error
```

**Input:**
- `text`: Brugerens rå input (dansk, tysk eller engelsk).
- `context`: Samtalekontekst fra `contextd` (objekt, tidligere handlinger, deltagere).
- `language_hint`: Valgfrit sprogvalg; ellers detekteres sproget.

**Output — `IntentExtraction`:**
```json
{
  "intent": "schedule_meeting",
  "entities": {
    "person": "did:eira:anne",
    "when": "2026-10-24T13:00:00Z",
    "topic": "projektmøde"
  },
  "language": "da",
  "confidence": 0.87
}
```

**Output — `Abstain`:**
```json
{"abstain": true, "reason": "ambiguous_input"}
```

**Output — `Error`:**
```json
{"error": "E_MODEL_UNAVAILABLE", "detail": "..."}
```

**Regler:**
- `confidence` er **ikke** en autorisation. Den må kun bruges til at afgøre, om der skal spørges brugeren.
- Hvis input er tvetydigt, skal modellen returnere `Abstain` — ikke gætte.
- Modellen må ikke kende til EDP-handlingstyper. Den udtrækker kun intention og entiteter.

### 3.2 EiraAI — `propose_action()`

```text
propose_action(
    intent: IntentExtraction,
    allowed_actions: list[ActionType],
    context: ConversationContext
) -> EdpAction | Abstain | Error
```

**Input:**
- `intent`: Output fra EiraLang.
- `allowed_actions`: Liste af EDP-handlingstyper, som `intentd` udleder fra den aktuelle policy og kontekst som *kandidater*, der må foreslås. Listen er ikke en tilladelse, samtykke eller autorisation til at udføre handlingen.
- `context`: Samme kontekst som EiraLang.

**Output — `EdpAction`:** Et EDP 1.0-kompatibelt forslag (uden `transport` og `veritas`, som sættes af `intentd`/`veritasd`).

**Output — `Abstain`:**
```json
{"abstain": true, "reason": "no_matching_action"}
```

**Output — `Error`:**
```json
{"error": "E_MODEL_UNAVAILABLE", "detail": "..."}
```

**Regler:**
- Modellen må kun foreslå handlinger fra `allowed_actions`. Forslag uden for listen skal afvises af modellen selv — og af gaten, hvis den alligevel kommer igennem.
- Modellen må ikke sætte `transport`, `veritas` eller `temporal.supersedes`.
- Modellen må ikke kende til executor eller system-API'er.
- Hvis ingen handling matcher, returneres `Abstain` — ikke en gættet handling.

---

## 4. Adapter-kontrakt

Hver model (Teuken, Devstral, fremtidige) implementeres som en adapter, der opfylder:

```text
ModelAdapter:
  name: str
  version: str
  capabilities: {supports: [method...], languages: [str...], max_context: int}
  extract_intent(text, context, language_hint) -> IntentExtraction | Abstain | Error
  propose_action(intent, allowed_actions, context) -> EdpAction | Abstain | Error
  health() -> {ok: bool, detail: str}
```

**Krav:**
1. **Ingen protokol-lækage:** Adapteren må ikke tilføje felter uden for kontrakten.
2. **Ingen direkte executor-adgang:** Adapteren har ingen reference til executor eller system-API.
3. **Health blokerer:** En adapter med `health().ok == false` må ikke kaldes af `intentd`.
4. **Fejl er eksplicitte:** Adapteren returnerer `Error` med en kode — ikke en tom handling.
5. **Ingen tavs fallback:** Hvis adapteren ikke kan svare, skal den returnere `Abstain` eller `Error` — ikke et gæt.

---

## 5. `intentd`'s orkestrering

`intentd` er den eneste komponent, der kalder adapterne. Sekvensen er:

1. Modtag brugerinput.
2. Kald `EiraLang.extract_intent()`.
   - Ved `Abstain`: Spørg brugeren om afklaring (via UI, ikke via model).
   - Ved `Error`: Returnér sikker fejltilstand.
3. Beregn `allowed_actions` ud fra kontekst og politik (ikke fra modellen). Dette er kun et forslagsscope; ingen handling er dermed autoriseret.
4. Kald `EiraAI.propose_action()`.
   - Ved `Abstain`: Informér brugeren om, at handlingen ikke kan udføres.
   - Ved `Error`: Returnér sikker fejltilstand.
5. Berig forslaget med `transport`, `veritas` og `temporal` (fra `intentd`, `veritasd`, `graphd`) uden at ændre `action.type` eller `action.content`.
6. Validér den komplette, berigede EDP-envelope mod den kanoniske versionerede schema.
7. Send til Gate Kernel, som selv gentager schema-, semantik-, policy-, samtykke-, autorisations- og tilstandskontroller. En tidligere kontrol i `intentd` er aldrig autoritativ.

**Regel:** `intentd` må ikke ændre `action.type` eller `action.content` efter modellens forslag — kun tilføje metadata.

---

## 6. Kontekstmodellen

`ConversationContext` leveres af `contextd` og indeholder:

| Felt | Beskrivelse |
|---|---|
| `conversation_id` | Objekt-forankring (`obj:<type>:<id>`) |
| `participants[]` | Deltagere med DID og rolle |
| `recent_actions[]` | De seneste EDP-handlinger i samtalen |
| `available_objects[]` | Objekter brugeren har adgang til |
| `user_preferences` | Sprog, enhed, tilgængelighed |

Modellen må ikke modificere konteksten. Den er **read-only**.

---

## 7. Fejlkoder

| Kode | Betydning |
|---|---|
| `E_MODEL_UNAVAILABLE` | Adapteren kan ikke nås |
| `E_MODEL_TIMEOUT` | Adapteren svarede ikke inden for tidsgrænsen |
| `E_INVALID_OUTPUT` | Adapterens output følger ikke kontrakten |
| `E_UNSUPPORTED_LANGUAGE` | Sproget understøttes ikke |
| `E_CONTEXT_TOO_LARGE` | Konteksten overskrider modellens grænse |
| `E_ABSTAIN` | Modellen afviste at svare (ikke en fejl, men en beslutning) |

---

## 8. Testkrav (acceptkriterier)

| Test | Forventet resultat |
|---|---|
| Dansk kommando → korrekt `IntentExtraction` | `PASS` |
| Tvetydig kommando → `Abstain` | `Abstain` med `ambiguous_input` |
| Ukendt sprog → `Error` | `E_UNSUPPORTED_LANGUAGE` |
| EiraAI foreslår handling uden for `allowed_actions` | Gaten afviser (`E_SCHEMA` eller `E_POLICY`) |
| EiraAI foreslår handling med korrekt schema, men uden tilladelse | Gaten afviser (`E_UNAUTHORIZED`) |
| Adapter utilgængelig | `Error` (`E_MODEL_UNAVAILABLE`) |
| Adapter returnerer ikke-konformt output | `Error` (`E_INVALID_OUTPUT`) |
| `intentd` forsøger at ændre `action.type` | Skal ikke være muligt (kontraktbrud) |

---

## 9. Ydeevnekrav

| Krav | Grænse | Begrundelse |
|---|---|---|
| `extract_intent()` latenstid | < 2 sekunder (lokal model) | Brugeren skal ikke vente |
| `propose_action()` latenstid | < 5 sekunder (lokal model) | Acceptabelt for handlingsforslag |
| Hukommelse pr. adapter | < 16 GB (Devstral), < 8 GB (Teuken) | Skal kunne køre på almindelig hardware |
| Timeout | 30 sekunder | Sikker fejltilstand |

**Bemærk:** Hvis latenstiden overskrides, skal adapteren returnere `E_MODEL_TIMEOUT` — ikke et forsinket svar.

---

## 10. Forbudte mønstre

- At lade modellen kende til `transport`, `veritas` eller executor.
- At bruge modellens `confidence` som autorisation.
- At lade `intentd` ændre modellens `action.type` eller `action.content`.
- At kalde en adapter uden at tjekke `health()`.
- At behandle `Abstain` som en fejl (det er en gyldig beslutning).

---

## 11. Versionsstyring

- `ai_interface`-feltet er `major.minor`.
- **Major**-bump ved ændring af kontrakten (signatur eller output-format).
- **Minor**-bump ved nye fejlkoder eller nye capabilities.
- Adaptere erklærer, hvilke versioner de understøtter.

---

## 12. Åbne spørgsmål (til næste revision)

1. Skal EiraLang og EiraAI kunne køre i samme adapter (én model, to metoder), eller skal de altid være separate? **Anbefaling:** separate, så de kan skiftes uafhængigt.
2. Skal `intentd` kunne kalde EiraLang og EiraAI parallelt for at reducere latenstid? **Anbefaling:** nej, sekventielt — EiraAI afhænger af EiraLang's output.
3. Hvordan håndteres kontekst, der overskrider modellens grænse? **Anbefaling:** `intentd` opsummerer konteksten via `contextd`, før den sendes til adapteren.
