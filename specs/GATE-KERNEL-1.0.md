# GATE KERNEL 1.0 — EiraOS Sikkerhedsgrænse

**Status:** Draft (bindende for implementering)  
**Version:** 1.0  
**Gælder for:** `intentd`, alle executor-adaptere, AI-interface, UI  
**Relateret:** EDP 1.0, EiraOS Systembeskrivelse

---

## 1. Formål

Gate Kernel er EiraOS' **autoritative sikkerhedsgrænse**. Intet modeloutput, ingen adapter og ingen daemon må udføre en beskyttet handling uden om gaten.

**Grundregel:**

> AI'en foreslår. Gaten afgør. Systemet udfører.

Gaten er ikke en validator, der "hjælper" modellen. Den er en **dommer**, der kan afvise alt – også output, der ser korrekt ud.

## 2. Den autoritative handlingsvej

Al modelgenereret handling skal gennemgå præcis denne sekvens:

```text
Brugerens intention
    → EiraLang (sprogforståelse)
        → EiraAI (handlingsforslag)
            → EDP-handling (rå forslag)
                → GATE KERNEL
                    ├─ 1. Syntaks
                    ├─ 2. Schema
                    ├─ 3. Semantik
                    ├─ 4. Sikkerhed
                    ├─ 5. Samtykke
                    ├─ 6. Autorisation
                    ├─ 7. Atomar tilstand
                    └─ 8. Executor
                        → Verificeret resultat
                            → graphd (audit + temporal state)
```

**Ingen alternativ kodevej må kunne udføre den samme beskyttede handling uden om gaten.** Dette gælder også interne testværktøjer, scripts og debug-endpoints.

## 3. Valideringslag (obligatorisk rækkefølge)

Hvert lag skal returnere en eksplicit beslutning: `PASS`, `REJECT` eller `CLARIFY` (kun lag 1–3).

### 3.1 Lag 1 — Syntaks

| Kontrol | Krav |
|---|---|
| Gyldig JSON | Output skal parse som JSON uden fejl |
| EDP-version | `edp`-feltet skal være `"1.0"` |
| Obligatoriske felter | `id`, `conversation_id`, `participants`, `action`, `temporal.created_at` |

**Ved fejl:** `REJECT` med `E_SYNTAX`.

Constrained decoding (JSON Schema i Ollama, GBNF i llama.cpp) kan reducere syntaksfejl, men **erstatter ikke** denne kontrol. Gaten skal validere uafhængigt af, hvad runtime hævder at have gjort.

### 3.2 Lag 2 — Schema

| Kontrol | Krav |
|---|---|
| `action.type` | Skal være i EDP 1.0's lukkede taksonomi |
| `action.content` | Skal følge skemaet for den pågældende `type` |
| `participants[]` | Mindst én; `identity` skal være gyldig DID |
| `transport` | `degraded` skal være boolesk; `error` skal være `null` eller gyldig fejlkode |
| `veritas` | `trust_score` i [0.0, 1.0]; `level` i {`green`, `yellow`, `red`} |

**Ved fejl:** `REJECT` med `E_SCHEMA`.

### 3.3 Lag 3 — Semantik

| Kontrol | Krav |
|---|---|
| Feltkonsistens | Fx `commitment_accepted` skal referere til en eksisterende `commitment_id` |
| Temporal konsistens | `temporal.valid_from` må ikke være før `created_at` |
| Supersedes | `supersedes` skal pege på en eksisterende handling i samme `conversation_id` |
| Manglende felter | Hvis et felt er nødvendigt for at forstå handlingen, men ikke kan udledes: `CLARIFY` |

**Ved fejl:** `REJECT` med `E_SEMANTIC` eller `CLARIFY` med `E_MISSING_FIELD`.

### 3.4 Lag 4 — Sikkerhed

| Kontrol | Krav |
|---|---|
| Handlingstype tilladt | Er `action.type` tilladt i den aktuelle kontekst? |
| Mål tilladt | Er `conversation_id` og eventuelle sti-/netværksmål inden for brugerens domæne? |
| Parametre tilladt | Er værdierne i `action.content` inden for politikken (fx beløbsgrænser, filstier)? |
| Konsekvensklasse | Er handlingen idempotent, kompenserbar eller irreversibel? (Se §6) |

**Ved fejl:** `REJECT` med `E_POLICY`.

**Regel:** Hvis konsekvensklassen er `irreversible`, kræves eksplicit bekræftelse (lag 5) – også hvis handlingen ellers er autoriseret.

### 3.5 Lag 5 — Samtykke

| Kontrol | Krav |
|---|---|
| Samtykke påkrævet? | Irreversible handlinger og cloud-eskalering kræver altid samtykke |
| Samtykke givet? | Er der et gyldigt, ikke-udløbet samtykke for netop denne handling? |
| Samtykke dækker parametre? | Dækker samtykket de konkrete parametre (beløb, modtager, sti)? |

**Ved fejl:** `REJECT` med `E_CONSENT` eller `CLARIFY` med `E_NEED_CONSENT`.

### 3.6 Lag 6 — Autorisation

| Kontrol | Krav |
|---|---|
| Rettighed findes | Har `participants[].identity` rettighed til `action.type` på `conversation_id`? |
| Rettighed gælder nu | Er rettigheden ikke tilbagekaldt eller udløbet? |
| Step-up niveau | Kræver handlingen et højere assurance-niveau end sessionens? |

**Ved fejl:** `REJECT` med `E_UNAUTHORIZED` eller `CLARIFY` med `E_STEP_UP_REQUIRED`.

**Regel:** Autorisation kontrolleres **igen umiddelbart før udførelse** (lag 7), ikke kun ved planlægning.

### 3.7 Lag 7 — Atomar tilstand

| Kontrol | Krav |
|---|---|
| Handlingens tilstand | Skal være `pending` eller `confirmed` – ikke `executed` eller `cancelled` |
| Bekræftelsens binding | Er bekræftelsen bundet til handlingens `id` og en hash af `action.content`? |
| Idempotens | Er der allerede en `execution_id` for denne handling? I så fald: returnér eksisterende resultat |
| Samtidighed | Er der en lås på `conversation_id` + `action.id`? |

**Ved fejl:** `REJECT` med `E_STATE` eller returnér eksisterende resultat (idempotens).

### 3.8 Lag 8 — Executor

Executoren kaldes kun, hvis lag 1–7 alle returnerer `PASS`.

| Krav | Implementering |
|---|---|
| Kun én executor pr. `action.type` | Registreres i et eksplicit executor-registry |
| Executor må ikke kaldes direkte | Kun gennem gaten; direkte kald skal fejle |
| Resultat skal verificeres | Executoren returnerer `result` + `state_transition`; gaten verificerer, at transitionen er gyldig |
| Delvis fejl | Skal returnere `E_PARTIAL` med eksplicit tilstand – ikke falsk succes |

## 4. Beslutningsmodellen

Gaten returnerer altid én af:

| Beslutning | Betydning | Effekt |
|---|---|---|
| `PASS` | Handlingen er valideret og autoriseret | Executor kaldes |
| `REJECT` | Handlingen er ugyldig eller forbudt | Ingen udførelse; audit logges |
| `CLARIFY` | Handlingen kræver brugerafklaring | UI viser spørgsmål; ingen udførelse |

**Der findes ingen `PASS_WITH_WARNING`.** Hvis der er tvivl, er svaret `REJECT` eller `CLARIFY`.

## 5. Fejlkoder

| Kode | Betydning | Lag |
|---|---|---|
| `E_SYNTAX` | Ugyldig JSON eller manglende obligatoriske felter | 1 |
| `E_SCHEMA` | Ukendt `action.type` eller manglende skemafelter | 2 |
| `E_SEMANTIC` | Feltkonsistens eller temporal fejl | 3 |
| `E_MISSING_FIELD` | Nødvendigt felt kan ikke udledes | 3 |
| `E_POLICY` | Handling, mål eller parametre ikke tilladt | 4 |
| `E_CONSENT` | Manglende eller utilstrækkeligt samtykke | 5 |
| `E_NEED_CONSENT` | Samtykke kan indhentes | 5 |
| `E_UNAUTHORIZED` | Ingen rettighed til handlingen | 6 |
| `E_STEP_UP_REQUIRED` | Højere assurance-niveau nødvendigt | 6 |
| `E_STATE` | Ugyldig tilstandsovergang | 7 |
| `E_PARTIAL` | Executor fejlede delvist | 8 |
| `E_EXECUTOR_UNAVAILABLE` | Ingen executor registreret | 8 |

## 6. Reversibilitetsklasser

Hver `action.type` skal have en deklareret reversibilitetsklasse i EDP-skemaet:

| Klasse | Betydning | Krav |
|---|---|---|
| `idempotent` | Kan gentages uden bivirkning | Ingen ekstra bekræftelse |
| `compensable` | Kan rulles tilbage via kompenserende handling | Kompensationshandling skal være registreret |
| `irreversible` | Kan ikke fortrydes | Eksplicit bekræftelse + audit |

**Regel:** Hvis reversibilitetsklassen ikke er deklareret, behandles handlingen som `irreversible`.

## 7. Testkrav (acceptkriterier)

Gaten er kun "færdig", når følgende tests passerer:

| Test | Forventet resultat |
|---|---|
| Ugyldig JSON | `REJECT` (`E_SYNTAX`) |
| Ukendt `action.type` | `REJECT` (`E_SCHEMA`) |
| Manglende obligatorisk felt | `REJECT` (`E_SCHEMA`) |
| Forbudt sti eller handling | `REJECT` (`E_POLICY`) |
| Manglende samtykke til irreversibel handling | `REJECT` (`E_CONSENT`) |
| Ændrede parametre efter bekræftelse | `REJECT` (`E_STATE`) |
| Dobbelt eksekveringsforsøg | Returnér eksisterende resultat (idempotens) |
| Rettighed tilbagekaldt efter planlægning | `REJECT` (`E_UNAUTHORIZED`) |
| Executor kaldes direkte uden autorisation | `REJECT` (ingen direkte adgang) |
| Model-runtime er utilgængelig | `REJECT` med sikker fejltilstand |
| Handling fejler delvist | `E_PARTIAL` med korrekt registreret tilstand |
| Model foreslår korrekt schema uden tilladelse | `REJECT` (`E_UNAUTHORIZED`) |

**Regel:** Ingen test må bestå, fordi modellen "opfører sig pænt". Testene skal bevise, at gaten afviser, **selv når input ser korrekt ud**.

## 8. Audit

Hver beslutning skal logges i `graphd` som en temporal kant:

```json
{
  "gate": "1.0",
  "action_id": "dlg-7f3a9c2e",
  "decision": "REJECT",
  "layer": 6,
  "error": "E_UNAUTHORIZED",
  "participant": "did:eira:bo",
  "timestamp": "2026-10-21T10:00:00Z",
  "input_hash": "sha256:...",
  "policy_version": "2026.10"
}
```

Audit-loggen må ikke kunne ændres af modeller eller adaptere.

## 9. Forbudte mønstre

- At kalde en executor direkte fra `intentd`, UI eller adapter.
- At behandle `transport.degraded=true` som en undskyldning for at springe validering over.
- At bruge en models `confidence` som autorisation.
- At logge en `PASS`, før executoren har bekræftet resultatet.
- At have en "debug"- eller "admin"-vej uden om gaten.

## 10. Versionsstyring

- `gate`-feltet i audit er `major.minor`.
- **Major**-bump ved ændring af valideringsrækkefølge eller beslutningsmodellen.
- **Minor**-bump ved nye fejlkoder eller nye reversibilitetsklasser.
- Policy-version (`policy_version`) styres separat og kan opdateres uden gate-version-bump.

## 11. Åbne spørgsmål (til næste revision)

1. Skal `CLARIFY` kunne føre til en ny EDP-handling (`utterance`), eller skal det være en separat UI-tilstand? **Anbefaling:** separat UI-tilstand, så gaten ikke bliver en dialogmotor.
2. Skal `policy_version` kunne tvinge en `REJECT`, hvis en handling er planlagt under en ældre policy? **Anbefaling:** ja, hvis policyen er ændret på en måde, der påvirker handlingen.
3. Hvordan håndteres executor-timeout? **Anbefaling:** `E_PARTIAL` med `state: unknown`, og en efterfølgende verifikationshandling.
