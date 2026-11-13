# AI INTERFACE 1.0 — EiraOS Modelgrænseflade

**Status:** Draft; bindende som implementeringsmål, ikke ejeraccepteret som ny revision  
**Version:** 1.0  
**Afstemt mod:** `main` efter PR #190 (13. november 2026)  
**Gælder for:** `eira-modeld`, modeladaptere, EiraLang, EiraAI og appens AI-orkestrering  
**Relateret:** [EIRA-CONVERSATION-1.0](EIRA-CONVERSATION-1.0.md), [EDP 1.0](EDP-1.0.md), [Gate Kernel 1.0](GATE-KERNEL-1.0.md), [EIRA Delegation Protocol 1.1](EIRA-DELEGATION-PROTOCOL-1.1.md), [ADR-0002](../docs/decisions/ADR-0002-gate-to-handlingsfamilier.md)

---

## 0. Implementeringsstatus

Denne kontrakt beskriver både den modeluafhængige grænse og den aktuelle runtime. Status må ikke læses som bevis for funktioner, der endnu ikke findes.

| Område | Status på main efter #190 |
|---|---|
| Modelproces | `eira-modeld` kører som egen bruger (`eira-model`), uden netværk og uden adgang til `/data`; pakket |
| Adapter | `RuleAdapter` er aktiv. Den er deterministisk og regelbaseret; ingen sprogmodel eller modelvægte er integreret |
| Adapterkontrakt | `ModelAdapter` i `app/model/contract.py`: `health`, `extract_intent`, `propose_action`; output kontrolleres af modelprocessen |
| IPC | `model.prepare` modtager tekst og en påkrævet `session_id`; samtalekontekst er valgfri |
| Gate-forløb | Modelprocessen foreslår til Gate Kernel som sin egen procesidentitet; gaten kræver delegation og menneskeligt samtykke/bekræftelse |
| Systemhandlinger | `system:power.request_action` kan foreslås som EiraSystemAPI; modellen kalder aldrig system-API eller executor |
| Sprog | Kontrakten reserverer `da`, `de` og `en`; den aktuelle regeladapter understøtter kun dansk |
| Flersproget evaluering | Defineres separat i F8.1; denne kontrakt vælger ikke en model |

## 1. Formål og ufravigelig grænse

AI Interface er den modeluafhængige kontrakt for at omsætte brugerens tekst til et struktureret forslag. En adapter kan udskiftes uden at give modellen adgang til EiraOS' rettigheder, samtykke, transport eller udførelse.

> **Modellen fortolker og foreslår. Gaten afgør. Systemet udfører.**

Modellen er ikke en executor, policy-motor, identitetsudsteder eller samtykkemyndighed. Modellens confidence, interne vurdering, outputformat eller evalueringsscore er aldrig en tilladelse.

Alle modeloutput, herunder schema-valide output, behandles som potentielt fejlbehæftede eller adversarielle. De kontrolleres i modelprocessen og derefter igen af gaten efter dens egne regler.

## 2. Aktuel arkitektur efter #190

Den implementerede vej er:

```text
Eira UI / IntentBar
    │  model.prepare (tekst, session_id, evt. samtalekontekst)
    ▼
eira-modeld  [egen UID: eira-model, intet net]
    ├─ ModelAdapter.health()
    ├─ EiraLang.extract_intent()
    ├─ EiraAI.propose_action() med lukket kandidatliste
    ├─ kontrollerer adapterens output
    └─ oversætter forslaget til EDP- eller EiraSystemAPI-envelope
          │
          ▼
    intentd / Gate Kernel  ← modelprocessens egen identitet (SO_PEERCRED)
          │
          ├─ afviser eller registrerer et forslag
          ├─ kræver delegation, hvor det er nødvendigt
          └─ kræver menneskets samtykke og bekræftelse via den betroede agent
                    │
                    ▼
             executor bag gaten
```

Appen starter forløbet og håndterer brugerens interaktion med delegations- og samtykkeagenten. `eira-modeld` kalder adapteren og sender forslaget til gaten. Det er derfor **ikke** korrekt at beskrive `intentd` som den komponent, der kalder modeladapterne.

`intentd` er fortsat IPC-værten for Gate Kernel og samtalelagets læsemetoder. Det gør ikke `intentd` til ejer af modeladapteren.

## 3. Adapterens interne kontrakt

En adapter implementerer den interne Python-protokol i `app/model/contract.py`:

```text
ModelAdapter:
  name: str
  version: str
  health() -> {ok: bool, detail?: str}

  extract_intent(
      text: str,
      context: ConversationContext,
      language_hint: str | None
  ) -> IntentExtraction | Abstain | ModelError

  propose_action(
      intent: IntentExtraction,
      allowed_actions: tuple[str, ...],
      context: ConversationContext
  ) -> EdpAction | Abstain | ModelError
```

I den nuværende kode hedder forslagstypen `EdpAction`. Det er et internt DTO-navn, ikke en påstand om, at alle forslag er EDP-handlinger: `system:power.request_action` oversættes særskilt til EiraSystemAPI-envelope af modelprocessen. En fremtidig kontraktrevision kan give den interne type et mere neutralt navn; denne dokumentrevision ændrer ikke Python-API'et.

### 3.1 EiraLang — intention og entiteter

`extract_intent` udtrækker betydning og entiteter. Den må ikke afgøre, om en handling er tilladt.

`IntentExtraction` har:
- `intent`: stabilt, struktureret intentionsnavn.
- `entities`: typede data, ikke fri eksekverbar kode.
- `language`: eksplicit sprogkode.
- `confidence`: tal mellem 0 og 1, alene som modelmetadata.

Tvetydighed, utilstrækkelig kontekst, ukendt person eller manglende understøttelse skal give `Abstain` eller en eksplicit `ModelError`. Adapteren må ikke opfinde identiteter, modtagere, objekter, datoer eller parametre.

### 3.2 EiraAI — handlingsforslag

`propose_action` omsætter intentionen til ét struktureret forslag fra den kandidatliste, modelprocessen har givet.

- `allowed_actions` er en lukket teknisk kandidatliste for denne forespørgsel. Den er **ikke** afledt tilladelse, delegation, samtykke eller autorisation.
- Modellen må kun returnere en type fra listen. Modelprocessen kontrollerer dette igen.
- Gaten foretager de autoritative policy-, scope-, delegations-, samtykke-, autorisations- og udførelseskontroller.
- Hvis ingen handling passer, returneres `Abstain`; modellen må ikke vælge en nærliggende handling som gæt.
- Modellen må ikke producere transport-, Veritas-, executor-, actor-, scope-, policy- eller samtykkefelter.

### 3.3 De to handlingsfamilier

I overensstemmelse med ADR-0002 findes der én Gate Kernel og to handlingsfamilier:

1. **EDP:** brugerrettede handlinger i en samtale, fx `utterance` og `commitment_proposed`.
2. **EiraSystemAPI:** typede operationer på operativsystemet, fx `system:power.request_action`.

En systemhandling er en kandidat på samme modelgrænse, men den er ikke en EDP-handling. Modelprocessen oversætter dens type og input til EiraSystemAPI-wire-format. Gaten fastlægger aktør, scope, reversibilitet, policy og rettigheder. Modellen må aldrig kalde D-Bus, logind, en executor eller en system-API direkte.

## 4. Samtalekontekst og forespørgsler uden samtale

Den gamle antagelse om, at `contextd` leverer modelkonteksten, er fjernet. `contextd` er en gammel prototype, som udviklingsplanens F1.2 skal fjerne; den er ikke en normativ afhængighed for AI Interface.

Samtaledata og medlemskab hører under [EIRA-CONVERSATION-1.0](EIRA-CONVERSATION-1.0.md). Modellen får kun den begrænsede kontekst, som appen sender til `model.prepare`; den læser ikke selv samtalestrømmen eller databaser.

Den aktuelle interne `ConversationContext` indeholder:
- `conversation_id`
- `participants[]` (identitet, rolle og eventuelt visningsnavn)
- `now` (ISO 8601-reference for relative datoer)

Den aktuelle model-IPC accepterer:
- påkrævet `session_id` og `text`
- valgfri `conversation_id`, `me`, `participants[]`, `now` og `language_hint`
- valgfri `lang` til gate/UI-sprog

Hvis `conversation_id` er udeladt, normaliserer modelprocessen den interne kontekst til tom samtale og tom `me`. I den situation er **kun systemhandlinger kandidater**. Samtalehandlinger kræver en samtale og en `me`-identitet. En tom samtale må ikke bruges til at opfinde en samtale, modtager eller medlemskab.

Modellen kan ikke selv verificere, hvem der ejer `session_id`, eller om sessionen er gyldig. Den sender forslaget til gaten med session-id'et; gaten kontrollerer session, procesidentitet og delegation. Modellen må ikke læse sessionlageret eller udlede en brugeridentitet fra fritekst.

## 5. Modelprocessens IPC og Gate-forløb

### 5.1 `model.prepare`

Den aktuelle JSON-RPC-metode `model.prepare` er modelprocessens offentlige IPC-grænse. Den kræver en ikke-model-kalder, en ikke-tom `session_id` og gyldig tekst (maks. 4.000 tegn). `eira-modeld` kører som `eira-model`; kald fra modellen selv afvises.

Modelprocessen:
1. Kontrollerer adapterens `health()`. En usund adapter kaldes ikke.
2. Kører `extract_intent` og kontrollerer resultatets type, sprog og confidence-interval.
3. Beregner kandidater ud fra samtaletilstedeværelse og den lukkede liste af understøttede handlingstyper. Det er ikke en policy-afgørelse.
4. Kører `propose_action` og kontrollerer outputtype, kandidattype og at adresserede deltagere findes i den leverede kontekst.
5. Opretter selv den relevante envelope og sender den til `gate.propose` som modelprocessen.

### 5.2 Gate-identitet og delegation

Gate Kernel ser modelprocessens UID/PID via `SO_PEERCRED`. Modellen handler som sig selv – ikke som mennesket. Når gaten afviser på grund af manglende delegation, kan modelprocessen returnere `needs_delegation` med sin egen delegee-identitet og det præcise target. Appen kan derefter bede mennesket oprette delegationen gennem den betroede agent.

Dette svar er kun en oplysning om gatens afvisning. Det opretter ikke delegationen og giver ikke modellen nye rettigheder.

Mennesket skal fortsat selv give samtykke og bekræfte den konkrete handling via samtykkeagenten. Modellen kan ikke samtykke, bekræfte, godkende sin egen delegation eller kalde executoren.

### 5.3 Svarformer

Modelprocessen kan returnere:
- `{abstain, model}`: adapteren afstod; ingen gate-handling blev foreslået.
- `{error, model}`: adapteren var utilgængelig eller leverede en fejl.
- `{gate, action_type, model}`: et forslag blev sendt til gaten; gatens svar er autoritativt.
- `{gate, action_type, model, needs_delegation}`: gaten afviste på grund af manglende delegation; appen kan indlede den betroede delegationsvej.

UI'et må ikke fremstille et forslag som udført. Status og udfald skal komme fra gaten, og UI'et må ikke selv gengive eller erstatte samtykkeagentens betroede visning.

## 6. Sikkerhedskrav

1. **Egen procesidentitet:** modelprocessen kører som `eira-model`, ikke som desktop-brugeren eller `eira`.
2. **Ingen netværksadgang:** modellen og dens runtime må ikke have netværksadgang. Ingen cloud-fallback, ekstern inference eller skjult download ved runtime.
3. **Mindst mulige adgang:** ingen adgang til `/data`, sessionlager, Gate-database, samtykkenøgle eller executor.
4. **Ingen bypass:** alle beskyttede handlinger går gennem Gate Kernel.
5. **Fail closed:** ugyldigt output, ukendt handling, timeout, manglende runtime, utilstrækkelige ressourcer eller usikker kontekst må ikke blive til et handlingsforslag.
6. **Ingen autoritet fra confidence:** confidence og modelscore kan aldrig give rettigheder eller ændre Gate-beslutningen.
7. **Prompt injection:** instruktioner i brugerindhold, dokumenter eller kontekst må ikke ændre systemets policy eller disse grænser.
8. **Ingen skjult fallback:** fejl eller manglende sprogunderstøttelse skal være synlig som fejl eller afståelse.
9. **Ingen hemmelighedslogning:** prompts, persondata, tokens og modelinterne data må ikke lækkes i logs eller audit.
10. **Reproducerbar artefaktstyring:** en integreret model skal have fastlagt modelnavn, version, licens, vægthash, tokenizer, runtime, kvantisering og oprindelse før pakning.

## 7. Sprog og capabilities

Kontraktens målsprog er dansk (`da`), tysk (`de`) og engelsk (`en`). En adapter må kun erklære sprog, som den er evalueret til at understøtte. Sprogsupport skal måles særskilt pr. sprog; en samlet score må ikke skjule et svagt sprog.

Den aktuelle `RuleAdapter` accepterer kun dansk. Det er en kendt begrænsning, ikke en opfyldelse af flersproget support. F8.1 definerer den gentagelige evaluering og dens datasæt/rapportering. F8.1-resultaterne skal foreligge, før der vælges en model til F8.2.

## 8. Fejl og abstention

Adapterfejl og afståelser er forskellige:
- `Abstain(reason)`: gyldigt resultat; modellen har ikke et forsvarligt forslag.
- `ModelError(code, detail)`: adapteren kan ikke gennemføre sin opgave.
- `E_INVALID_OUTPUT`: modelprocessens kontraktkontrol afviser adapterens output.
- `E_MODEL_UNAVAILABLE`: adapterens health-check fejler eller runtime mangler.
- `E_UNSUPPORTED_LANGUAGE`: adapteren understøtter ikke forespørgslens sprog.
- `E_CONTEXT_TOO_LARGE`: konteksten overskrider en eksplicit grænse.

En adapter må ikke returnere en tom handling, udfylde manglende felter med gæt eller skjule fejl ved at falde tilbage til en anden model eller tjeneste.

Tidsgrænser, cancellation, ressourcegrænser og konkrete runtime-fejlkoder skal fastlægges for den valgte modelruntime i F8.2's implementeringsdesign. De tidligere generelle latenstids- og RAM-tal i denne draft er ikke dokumenteret som målte eller accepterede krav og må ikke behandles som sådanne.

## 9. Test- og acceptkrav

### 9.1 Kontrakt og adapter
- Gyldig og ugyldig `IntentExtraction`.
- Confidence uden for intervallet afvises.
- Ukendt sprog afvises eksplicit.
- Ugyldig type, malformed entities eller ugyldigt action-output bliver `E_INVALID_OUTPUT`.
- Handling uden for kandidatliste bliver afstået/afvist og når ikke gaten.
- Deltager uden for leveret kontekst afvises.
- Usund adapter kaldes ikke.
- Ingen samtale begrænser kandidater til systemhandlinger.
- Samtalehandling uden samtale afstås.
- Ukendt eller tvetydig input giver afståelse, ikke gæt.

### 9.2 Gate- og sikkerhedsgrænse
- Modellen foreslår som sin egen procesidentitet.
- Modellen kan ikke samtykke eller bekræfte.
- Manglende delegation rapporteres præcist, men oprettes ikke automatisk.
- Gate afviser manglende/ugyldig session, manglende delegation og manglende rettigheder.
- Gate håndhæver policy, reversibilitet, samtykke, autorisation og udførelse uafhængigt af modeloutput.
- EDP- og EiraSystemAPI-forslag går gennem samme autoritative Gate Kernel.
- Forsøg på direkte executor- eller system-API-adgang fra modellen fejler.
- Netværk er utilgængeligt fra modelprocessen også i installeret pakke.

### 9.3 Multilingual og runtime
- F8.1 evaluerer de samme faste cases på hvert deklareret sprog.
- Modelartefakt, tokenizer, runtime, kvantisering og konfiguration er pinned og hash-verificeret.
- Timeout, cancellation, OOM, runtime-crash og utilgængelige modelartefakter giver fail-closed udfald.
- Ressourceforbrug og latenstid måles på den definerede hardwareprofil.
- Tests omfatter prompt injection, adversarielle input, gentagne input, manglende kontekst og ugyldige modeloutput.

Sikkerhedsaccept er en selvstændig gate. Høj sproglig kvalitet kan ikke kompensere for et brud på en sikkerhedsinvariant.

## 10. Afgrænsning og afhængigheder for F8.2

Denne revision afklarer kontraktens nuværende arkitektur. Den vælger **ikke** en model og implementerer **ikke** en sprogmodelruntime.

F8.2 må først begynde på kode, når:
1. F8.1 har leveret reproducerbare evalueringsresultater, så modelvalg bygger på evidens.
2. En model og dens licens, vægte, tokenizer, runtime og hardwareprofil er gennemgået og accepteret.
3. Den relevante rækkefølge og forudsætninger i ejerens udviklingsplan er opfyldt. Den nuværende plan placerer F8 efter F2 og F3; planen står fortsat som forslag til ejerens accept, og denne kontraktrevision accepterer den ikke på ejerens vegne.
4. Denne kontraktrevision og det konkrete implementeringsdesign er gennemgået og accepteret af ejeren.

PR #190 er allerede merged og er derfor en del af det aktuelle grundlag. F0/F2/F3-status skal stadig kontrolleres mod udviklingsplanen, før F8.2's implementeringsarbejde startes; denne dokumentændring erklærer dem ikke færdige.

## 11. Versionsstyring

- `ai_interface` er versioneret som `major.minor`.
- Major bump kræves ved inkompatibel ændring af adapterens signaturer, wire-format eller sikkerhedsgrænser.
- Minor bump kan bruges ved kompatible capabilities eller fejltyper.
- Adaptere skal erklære deres understøttede interface-version og capabilities.
- Dokumentrevisionen ændrer ikke i sig selv den eksisterende Python-protokol eller `model.prepare`-wire-formatet.

## 12. Historiske antagelser, der ikke længere gælder

Følgende formuleringer fra den tidligere draft er afløst:
- `intentd` er ikke den komponent, der kalder adapterne; `eira-modeld` ejer adapterkaldet.
- `contextd` leverer ikke samtalekontekst; det er en gammel prototype, og samtaledata hører under EIRA-CONVERSATION.
- Modellen modtager ikke en fuld samtalehistorik, objektliste eller brugerpræferencer. Den får kun den begrænsede kontekst, appen eksplicit sender.
- Kandidatlisten er ikke en policy-tilladelse. Gaten er autoritativ.
- EiraSystemAPI er en særskilt handlingsfamilie, ikke en EDP-handling, selvom den interne nuværende DTO hedder `EdpAction`.
- De tidligere latenstids- og hukommelsesgrænser er ikke accepterede målte krav.

