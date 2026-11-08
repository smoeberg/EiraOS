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

Hvert lag skal returnere en eksplicit beslutning: `PASS`, `REJECT` eller `CLARIFY`. `CLARIFY` må kun bruges i lag 1–3, hvor brugerens betydning eller nødvendige handlingsdata er uklare. Manglende samtykke eller autorisation i senere lag er aldrig `CLARIFY` inde i gaten; de returnerer en eksplicit afvisning uden udførelse, hvorefter UI kan starte en separat samtykke-/step-up-proces. Efter denne proces skal hele handlingen valideres igen.

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
| `participants[]` | Mindst én; hver identitet skal følge en understøttet identitetssyntaks. DID'er og eksterne, scheme-kvalificerede adresser er forskellige identitetstyper; syntaks er ikke bevis på ejerskab eller autorisation |
| `transport` | `degraded` skal være boolesk; `error` skal være `null` eller et struktureret objekt med gyldig `code` |
| `veritas` | `status` i {`unassessed`, `assessed`, `unavailable`}; `trust_score` er `null` eller i [0.0, 1.0]; `evidence_refs` er en liste. EDP 1.0 har ikke et normativt `level`-felt |

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

**Ved fejl:** `REJECT` med `E_CONSENT` eller `E_NEED_CONSENT`. `E_NEED_CONSENT` betyder, at en separat samtykkeproces kan tilbydes; det tillader ikke udførelse. Efter et samtykke skal den oprindelige handling sendes gennem alle Gate-lag igen.

### 3.6 Lag 6 — Autorisation

| Kontrol | Krav |
|---|---|
| Rettighedssæt findes | Er der et aktivt, Fleet-signeret rettighedssæt i cachen (EIRA-RIGHTS-SET-1.0)? Ellers `E_UNAUTHORIZED` med `rights: missing`. |
| Rettighed findes | Giver sættet brugeren (principal eller gruppe fra sessionen) handlingsnøglen (`edp:<type>` / `system:<operation>`) på scope `conversation_id`, og rammer ingen deny? (`contract.authorize`) |
| Rettighed gælder nu | Er sæt og grant ikke udløbet målt i effektiv tid (RIGHTS-SET §4.1)? Ellers `rights: expired`. |
| Step-up niveau | Kræver politikken eller granten (den strengeste af dem) et højere assurance-niveau end sessionens? |

Rettighedssættet er den eneste kilde til rettigheder. Gaten har ingen lokal tildelingsvej og ingen IPC-metode, der skriver rettigheder. Hver audit-post indeholder sættets id, version og art, den autoriserende grant ved PASS, `owner_admin` (privat maskine, ADR-0003) og `clock_rollback`.

**Ved fejl:** `REJECT` med `E_UNAUTHORIZED` eller `E_STEP_UP_REQUIRED`. `E_STEP_UP_REQUIRED` kan starte en separat autentifikationsproces, men handlingen er ikke autoriseret, før Gate kontrollerer den igen efter step-up.

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

**Der findes ingen `PASS_WITH_WARNING`.** Hvis semantikken er uklar i lag 1–3, er svaret `CLARIFY`. Hvis en sikkerheds-, samtykke-, autorisations- eller tilstandskontrol fejler, er svaret `REJECT`. En separat afklarings-/samtykke-/autentifikationsproces må aldrig genbruge en gammel `PASS`; handlingen skal valideres igen.

## 5. Fejlkoder

| Kode | Betydning | Lag |
|---|---|---|
| `E_SYNTAX` | Ugyldig JSON eller manglende obligatoriske felter | 1 |
| `E_SCHEMA` | Ukendt `action.type` eller manglende skemafelter | 2 |
| `E_SEMANTIC` | Feltkonsistens eller temporal fejl | 3 |
| `E_MISSING_FIELD` | Nødvendigt felt kan ikke udledes | 3 |
| `E_POLICY` | Handling, mål eller parametre ikke tilladt | 4 |
| `E_CONSENT` | Manglende eller utilstrækkeligt samtykke | 5 |
| `E_NEED_CONSENT` | Samtykke mangler; separat samtykkeproces kan tilbydes, ingen udførelse | 5 |
| `E_UNAUTHORIZED` | Ingen rettighed til handlingen | 6 |
| `E_STEP_UP_REQUIRED` | Højere assurance-niveau nødvendigt; separat step-up og fuld genvalidering kræves | 6 |
| `E_STATE` | Ugyldig tilstandsovergang | 7 |
| `E_PARTIAL` | Executor fejlede delvist | 8 |
| `E_EXECUTOR_UNAVAILABLE` | Ingen executor registreret | 8 |

## 6. Reversibilitetsklasser

Hver tilladt handlingstype/operation skal have en deklareret reversibilitetsklasse i Gate-policy registry. Klassen er ikke autoritativ, hvis den kommer fra modeloutput eller brugerleveret EDP:

| Klasse | Betydning | Krav |
|---|---|---|
| `idempotent` | Kan gentages uden bivirkning | Ingen ekstra bekræftelse |
| `compensable` | Kan rulles tilbage via kompenserende handling | Kompensationshandling skal være registreret |
| `irreversible` | Kan ikke fortrydes | Eksplicit bekræftelse + audit |

**Regel:** Reversibilitetsklassen er intern Gate-policy metadata i et versionsstyret, testet policy-registry — ikke et felt, modellen kan vælge i EDP-payloaden. Hvis registry ikke har en eksplicit klasse for handlingstypen og den konkrete operation, behandles handlingen som `irreversible`. Ændring af klassen kræver policy review og tests.

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

---

## Bilag A — Implementering (november 2026)

**Kode:** `app/gate/` (`kernel.py`, `edp.py`, `policy.py`, `store.py`, `executors.py`, `ipc.py`). Gaten kører i `intentd` og eksponeres som `gate.propose`, `gate.consent`, `gate.confirm` og `gate.status`. Ingen IPC-metode kalder en executor direkte.

**Flow:**
1. `propose` kører lag 1–4, gemmer handlingen som `pending`, bundet til et indholdshash, og rapporterer bagefter, hvad lag 5–6 mangler.
2. `consent` registrerer brugerens samtykke til netop det hash. Samtykket udløber efter 10 minutter.
3. `confirm` validerer igen fra lag 1 ud fra den gemte rå input. Derefter følger hash-binding, atomar claim, ny autorisation lige før udførelse og executoren med en engangsbillet.

**Indholdshashet** dækker `id`, `conversation_id`, `participants`, `action` og `valid_from`. `transport` og `veritas` er ikke med: de beriges efter brugerens beslutning og må ikke ændre handlingen.

**Afklaringer af §11:**
1. `CLARIFY` er en separat UI-tilstand, og gaten fører ingen dialog.
2. En ændret policy for handlingstypen siden forslaget giver `REJECT (E_POLICY)`. Det afgøres via et fingeraftryk af policy-posten.
3. Timeout eller crash i executoren giver `E_PARTIAL` med `state: unknown`, og handlingen prøves ikke automatisk igen.

**§7-tests → `tests/test_gate_kernel.py`:**

| §7-krav | Test |
|---|---|
| Ugyldig JSON | `test_invalid_json_is_rejected_as_syntax` |
| Ukendt `action.type` | `test_unknown_action_type_is_rejected_as_schema` |
| Manglende obligatorisk felt | `test_missing_content_field_is_rejected_as_schema` |
| Forbudt handling eller parameter | `test_forbidden_action_and_parameters_are_rejected_as_policy` |
| Manglende samtykke | `test_missing_consent_for_irreversible_action_is_rejected` |
| Ændrede parametre | `test_changed_parameters_after_confirmation_are_rejected` |
| Dobbelt eksekvering | `test_double_execution_returns_the_existing_result`, `test_concurrent_confirmations_execute_once` |
| Rettighed tilbagekaldt | `test_right_revoked_after_planning_is_rejected`, `test_right_revoked_between_claim_and_execution_is_rejected` |
| Direkte executor-kald | `test_executor_cannot_be_called_directly` |
| Model-runtime utilgængelig | `test_unavailable_model_runtime_is_a_safe_reject` |
| Delvis fejl | `test_partial_failure_is_reported_with_its_state` |
| Korrekt schema uden tilladelse | `test_correct_schema_without_permission_is_unauthorized` |

Ud over §7 dækker testene blandt andet `confidence` og `reversibility` i input (afvises af schemaet), degraded transport, udløbet samtykke, manipuleret lagret input, step-up til betaling, ukendt session, at handle på en andens vegne, et append-only og hash-kædet audit-log samt at en PASS først logges efter executorens resultat.

**Mutationstjek:** Hver af disse kontroller er fjernet én ad gangen, og testsuiten fejlede hver gang: samtykke, hash-binding, autorisation lige før udførelse, idempotens, policy-fingeraftryk, verifikation af tilstandsovergangen og rettigheder.

**Kendte begrænsninger (åbne), ordnet efter alvor:**

> **Trusselsmodel i dag:** Lag 5–6 beskytter mod *fejl* (en model, der foreslår forkert, en UI-bug, en forældet plan), ikke mod en *kompromitteret lokal proces*. Grunden er, at kalderens identitet endnu ikke kommer fra forbindelsen.

1. **Kalderens identitet er påstået, ikke bevist.** Både `session_id` og `origin` (`user`/`model`) sendes af IPC-kalderen. En proces i gruppen `eira`, der kender et session-id, kan derfor handle som brugeren, og den kan kalde sig `user`. Løsningen er, at identiteten kommer fra forbindelsen: `SO_PEERCRED` plus en signeret sessionstoken, som UI'en får ved login, og som modelprocessen aldrig ser. Det skal løses sammen med punkt 4, fordi `identityd` har samme behov. Det sker i PR'en efter executors.
2. **Audit-kæden mangler et eksternt anker.** `gate_audit` er hash-kædet og append-only i en SQLite-fil, som `intentd` selv skriver. Kæden afslører ændringer foretaget af andre, men ikke at daemonen selv genskriver hele kæden. To værn, der dækker hver sin trussel:
   - **journald med Forward Secure Sealing (lokalt).** `intentd` skriver jævnligt kædens head-hash til journalen. *Dækker:* senere omskrivning eller sletning af poster fra før seneste forsegling. *Dækker ikke:* at en kompromitteret `intentd` skriver en falsk head-hash, for den bliver forseglet lige så pænt som en ægte. Og ændringer inden for det aktuelle forseglingsinterval kan ikke opdages. Drift:
     - Forseglingen sker periodisk, 15 minutter som standard (`journalctl --setup-keys --interval`).
     - Sealing-nøglen bliver på maskinen. Verifikationen kræver *verifikationsnøglen*, som skal opbevares uden for maskinen (`journalctl --verify --verify-key=…`).
     - Rotation giver flere journalfiler at verificere.
     - Verifikationen skal køre planlagt, og et udeblevet eller fejlet resultat skal alarmere. Ellers opdager ingen, at ankeret er holdt op med at virke.
   - **Et vidne uden for maskinen (fleet).** Head-hashen indgår som tilstand i den eksisterende Merkle-sync (`app/fleet/merkle_sync.py`, `fleetd` `push_blocks`) til en anden enhed. En omskrivning kræver så, at to maskiner lyver ens. *Dækker ikke:* en enkeltstående pc uden fleet-peer. Den har kun det lokale værn, og det skal fremgå af dens parity-status.
3. ~~**Ingen kanonisk gengivelse af samtykket.**~~ **Lukket** med `app/gate/render.py` (renderer v1, dansk og engelsk).
   - Rendereren læser kun den validerede konvolut og gatens policy, aldrig modellen.
   - Gengivelsen viser handlingen og alle dens parametre, samtalen, modtagerne og reversibiliteten fra registret.
   - Brugerleveret tekst står i «…». Linjeskift vises som ⏎, og usynlige tegn, bidi-styring, særlige mellemrum og rendererens egne afgrænsere vises som ⟨U+XXXX⟩. Derfor kan en besked ikke forfalske en linje som "Kan fortrydes".
   - Tidspunkter skrives ud fra tidsstemplets egne felter og konverteres aldrig.
   - **Binding:** Ved `propose` gemmes tekst, hash, version og sprog sammen med handlingen. `gate.consent` og `gate.confirm` kræver `rendering_hash`. Lag 5 godtager kun et samtykke til netop den tekst, og samtykker fra før rendereren (NULL) tæller ikke. Lag 7 tjekker, at den gemte tekst stadig hasher til den gemte hash. Teksten gen-renderes aldrig, så en nyere renderer ændrer ikke det, der er samtykket til.
   - Sproget indgår i hashen. Samme handling på et andet sprog er et nyt samtykke (`E_STATE` ved genbrug af id'et), og et ukendt sprog giver `E_POLICY`.
   - **Ikke dækket:** Ruten (`transport`) er ikke med i gengivelsen, fordi den vælges efter samtykket. Hvis en rute ændrer privatliv, pris eller levering væsentligt, kræver EDP §2.4 et nyt samtykke. Det hører til route-selection i adapter-laget.
4. **Rettigheder og medlemskab.** *Rettigheder: lag 6 læser nu kun det Fleet-signerede rettighedssæt (`app/rights/cache.py`, `/data/rights`); tabellen `gate_grants` og den lokale tildelingsvej er fjernet.* Tilbage: `eira-governance-agent` skal hente, verificere og installere sæt, og bundlen skal have et signeret default-sæt. Indtil da har en installeret maskine intet sæt og afviser alle handlinger i lag 6 (fejler lukket). Medlemskab (`gate_members`) har stadig ingen produktionskilde. Identitet (`gate_identities`, session, assurance) kommer fra `identityd`. Begge dele kræver procesidentitet (punkt 1). **Fundet i VM-testen:** Den installerede `identityd` har hverken database-sti eller skriveadgang (ingen `/data` i unit eller AppArmor). Sessioner, som `identityd` opretter, deles derfor ikke med `intentd` på en installeret maskine. Gaten fejler lukket (ukendt session giver `REJECT`), men flowet virker først installeret, når denne PR er lavet.
5. ~~**Tre gamle skriveveje går uden om gaten.**~~ **Lukket.** `intent.confirm`, `intent.execute` og `journey.advance` svarer nu `E_GATE_REQUIRED` med et pejl til `gate.propose` og en `user_message`. De er omdirigeret, ikke slettet. Bevis:
   - `test_former_bypasses_answer_gate_required_and_never_execute` kører over den rigtige JSON-RPC-server og viser, at hverken `execute_intent`, `stated`-appenderen eller journey-lageret nås.
   - `test_every_intentd_method_is_classified` har en tom `KNOWN_BYPASSES`.
   - Mutationstjek: at gen-eksponere `intent.execute` får testen til at fejle.
6. ~~**Samtykkets udløb regnes på vægur-tid.**~~ **Lukket** med `app/gate/clock.py`. Ved samtykket gemmes `(boot_id, CLOCK_BOOTTIME)`. Lag 5 godtager kun et samtykke fra samme boot, og kun hvis der er gået mindre end TTL'en (10 min.) på `CLOCK_BOOTTIME`, som også tæller tid i suspend. Vægur-tiden (`expires_at`) bruges kun til visning og audit.
   - Et tilbagestillet ur forlænger ikke samtykket, og et vægur-spring frem (NTP, tidszone) afbryder det ikke.
   - En genstart af maskinen afslutter samtykket. En genstart af daemonen i samme boot gør ikke.
   - Rækker uden boot-tidspunkt (fra før migrationen) er aldrig gyldige.
   - Uden kernens `boot_id` (udviklingsmaskiner uden Linux) er "boot" lig processen. Det er strengere, aldrig løsere.

**Rettet efter review af #136:**
- *Crash-recovery.* Et crash mellem claim og registreret resultat efterlader handlingen i `executing`. `Gate.recover()` kører ved opstart og lader executorens egen varige tilstand afgøre udfaldet: outbox-rækken findes → `executed`, den findes ikke → `pending` igen, kan ikke afgøres → `unknown`. Executoren køres aldrig igen, og tests dræber processen før og efter outbox-skrivningen.
- *Genautorisation lige før udførelse* bruger den session, der bekræfter, ikke den, der foreslog.
- *`gate.status`* er sessionsbundet: kun den handlende bruger og samtalens medlemmer får svar. Alle andre får samme svar som ved et ukendt id.
- *Database-sti på den installerede maskine.* VM-testen fangede, at `intentd` crash-loopede. Rettet, og VM-testen kalder nu gaten over socket'en.

**Note til punkt 1:** Alle daemons kører i dag som samme systembruger (`eira`). `SO_PEERCRED` kan derfor kun skelne modelprocessen fra UI'en, hvis modellen kører under sin egen UID og ikke er medlem af gruppen, der har adgang til gatens kommandosocket. Socket-adgang skal gives pr. socket, ikke til hele `/run/eira`.

**Rækkefølge (besluttet efter review, november 2026):**
1. Merge Gate Kernel 1.0.
2. Omdirigér den gamle vej.
3. Lav rendereren, fordi den blokerer punkt 4.
4. Flyt den første executor, der ændrer maskinens tilstand, ind under gaten: `SystemExecutor` med EiraSystemAPI's strøm-operationer og en test, der beviser, at det direkte Tauri-kald fejler.
5. Lav procesidentitet. Identitet og grupper kommer fra `identityd`, rettigheder fra Fleet via `eira-governance-agent` (ADR-0003).
6. Lav audit-ankeret (journald FSS og fleet-vidne).

**Executor-status:** Den eneste executor er conversation-outboxen for `utterance` og `commitment_*`. Den skriver hændelsen varigt, før noget leveres (Phase 1-beslutningen), og rapporterer `delivery: pending`, aldrig "leveret".


---

## Bilag B — Gate 1.1: to handlingsfamilier (ADR-0002)

**Version:** `gate` i audit-loggen er `"1.1"`. Det er en minor-ændring (§10), fordi valideringsrækkefølgen og beslutningsmodellen er uændrede.

| Familie | Genkendes på | Lag 1–2 | Omfang |
|---|---|---|---|
| EDP | `"edp": "1.0"` | EDP 1.0-schemaet (§3.1–3.2) | `conversation_id` |
| EiraSystemAPI | `"eira_system": "1"` | `app/gate/system.py`: felterne `id`, `operation`, `input` og `created_at`. Listen over operationer er lukket, input har et typet skema, og ekstra felter afvises | `device:local` |

**Afvisninger i lag 1–2:** En handling med begge nøgler afvises med `E_SYNTAX`, og det samme gør en handling med ingen af dem. En ukendt operation eller et felt som `rights` eller `reversibility` i forslaget afvises med `E_SCHEMA`.

**Fra lag 3 er koden den samme for begge familier.** Systemforespørgslen omsættes til gatens fælles form: den handlende er sessionens bruger og aldrig et felt i forespørgslen. Indholdshashet binder derfor handlingen til den bruger, der foreslog den. Samme policy-registry, med nøgler som `system:power.request_action`. Samme samtykke, renderer, autorisation, atomare claim, recovery og audit-kæde.

**Operationer i 1.1:**

| Operation | Input | Reversibilitet | Assurance | Executor |
|---|---|---|---|---|
| `power.request_action` | `{"action": "poweroff" \| "reboot" \| "suspend"}` | irreversible | `eid_low` | `PowerExecutor` |

`PowerExecutor` kalder systemd-logind over system-D-Bus med et fast argv til `busctl` (ingen shell) og `interactive=false`. Før handlingen spørger den `Can<Action>`, og svarer logind ikke `"yes"`, afvises handlingen med `E_EXECUTOR_UNAVAILABLE` og står igen som `pending`. Lykkes kaldet, er den ærlige tilstand `requested`. Ved et crash bliver tilstanden `unknown`, og handlingen prøves aldrig automatisk igen.

**Mindst mulige rettigheder:**
- `packaging/polkit/50-eira-power.rules` giver servicebrugeren `eira` netop de seks login1-power-handlinger og ikke `*-ignore-inhibit`. Programmer, der blokerer nedlukning, vinder altså stadig.
- AppArmor-profilen for `intentd` tillader kun `busctl` og D-Bus-kald til `login1.Manager`-metoderne `Can*`, `PowerOff`, `Reboot` og `Suspend`.
- Retten `system:power.request_action` på `device:local` tildeles kun via Fleet's rettigheds-API (ADR-0003). Et forslag kan ikke bære rettigheder.

**Tauri `eira_system`:** `power.request_action` fejler lukket med `UNSUPPORTED`. Det bevises af Rust-testen `power_actions_never_execute_from_a_direct_call`. Tauri beholder kun læseoperationer.

**`gate.capabilities`** er en læseoperation. Den viser familierne, systemoperationerne og logind's svar på `Can*`. VM-acceptancetesten kræver `poweroff` og `reboot` = `"yes"` på den installerede maskine, hvilket beviser, at AppArmor, polkit og logind spiller sammen. Selve nedlukningen køres ikke i CI.

**Åbent:**
1. Ingen tildeler i dag retten til `device:local` på en installeret maskine. Gaten fejler lukket, indtil `eira-governance-agent` anvender et signeret rettighedssæt fra Fleet (ADR-0003, `specs/EIRA-RIGHTS-SET-1.0.md`).
2. CEL-constraints fra den tidligere `intent.execute` er endnu ikke foldet ind i lag 4.
