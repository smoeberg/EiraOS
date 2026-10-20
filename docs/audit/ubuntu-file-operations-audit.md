# EiraOS — audit af filhåndtering, intent-logik og Ubuntu-systemintegration

**Auditdato:** 2026-10-20  
**Audit-base:** `main` (statisk gennemgang af repository-træ og udvalgte kildefiler)  
**Formål:** Kortlægge eksisterende funktionalitet og risici før implementering af filhåndtering og et stabilt Ubuntu-system-API-lag.  
**Begrænsning:** Dette er en statisk kodegennemgang. Der er ikke kørt tests, startet EiraOS på Ubuntu 26.04 eller udført runtime-/integrationstest i forbindelse med denne audit. Fund om runtime-adfærd skal derfor valideres på målplatformen.

## 1. Konklusion

EiraOS har allerede flere relevante byggesten: intent parsing, capability-manifester, planlægnings-/bekræftelsesflow, audit events, Python-daemon-IPC og en Tauri-bro til Unix sockets. Det er dog **ikke det samme som en implementeret Ubuntu-filmanager eller et generelt Ubuntu System API**.

I den gennemgåede `main`-kode blev der ikke fundet en dedikeret filsystemadapter eller et samlet filoperationsmodul, der implementerer listning, søgning, læsning, kopiering, flytning, omdøbning, sletning, filmetadata, konfliktbehandling og filrettigheder. De viste capability-manifester beskriver ERP-/dokumenthandlinger, ikke lokale filer. Den generiske executor returnerer `executed_stub` og siger eksplicit, at der ikke kaldes et eksternt API.

**Anbefaling:** Implementér ikke filoperationer direkte i React-komponenter eller i intent-parseren. Definér først en EiraOS-ejet, versionsstyret kontrakt og et separat adapterlag; implementér derefter én afgrænset, ikke-destruktiv operation ad gangen med tests.

## 2. Kortlagt intent- og eksekveringsflow

Den gennemgåede prototypepipeline i `app/daemons/intent_engine.py`, `app/intent_parser.py`, `app/capability.py` og `app/executor.py` fungerer konceptuelt således:

1. **Modtagelse:** `intent.parse` eller `intent.plan` modtager input og knytter det til en session.
2. **Fortolkning:** `parse_intent_request` bruger eventuelt Mistral; ellers anvendes regelbaseret parsing. Reglerne dækker primært approve/reject/status/send/skift fokus. Ukendt input bliver som udgangspunkt `search` med lav confidence.
3. **Ressourcevalg:** `infer_resource` skelner meget groft mellem `order` og `document`. Den resolver ikke en lokal fil, sti, mappe eller mount.
4. **Capability-opslag:** `find_capability_match` matcher præcist på action/resource og kræver, at adapteren står som online.
5. **Plan:** `plan_intent` sætter `can_execute` og `block_reason` ud fra afklaring, capability-match og assurance.
6. **Bekræftelse:** `intent_confirm` henter den ventende intent, kontrollerer dele af assurance-flowet og kalder executor.
7. **Eksekvering:** `execute_intent` kontrollerer capability/adapterstatus, men returnerer en stubstatus i stedet for at udføre den beskrevne systemhandling.
8. **Audit og tilstand:** Der skrives audit events, og pending intent markeres/slettes efter flowet.

### Vigtigt fund: mulig omgåelse af planens blokering

I den gennemgåede `app/daemons/intent_engine.py` kontrolleres `can_execute is False`, men afvisningen sker kun, hvis en efterfølgende kombination af assurance og capability ikke er opfyldt. Hvis begge er opfyldt, fortsætter koden trods `can_execute=False`. Det gør planens eksplicitte blokering ikke autoritativ. Bekræftelseslogikken bør fail-closed: hvis planen siger, at handlingen ikke kan udføres, skal den afvises uden undtagelse, og en eventuel ny plan skal beregnes eksplicit.

Dette fund gælder den nævnte pipeline i den auditerede `main`-version. Repository’et har også en separat `app/daemons/intentd.py`-service med CEL-constraint enforcement; disse to eksekveringsveje må ikke forveksles og bør kortlægges/forenes i en særskilt audit, før der ændres i sikkerhedsflowet.

## 3. Hvad er implementeret, og hvad er ikke dokumenteret som implementeret?

| Område | Status ud fra kildekoden | Bemærkning |
|---|---|---|
| Regelbaseret intent parsing | Delvist implementeret | Begrænset action-sæt; ingen filspecifik intentmodel påvist |
| Valgfri Mistral-parsing | Implementeret som integrationssti | Afhænger af konfiguration og parserresultat |
| Capability-manifester | Implementeret | Matcher action/resource; nuværende eksempler er ERP/dokument |
| Planlægning og blokårsag | Implementeret | Bekræftelsesflowets håndhævelse har fundet risiko |
| Audit events | Implementeret flere steder | Dækker hændelser, men er ikke i sig selv bevis for at systemoperationen lykkedes |
| Generisk executor | Prototype/stub | `executed_stub`; ingen rigtig fil-/Ubuntu-operation |
| Fil-/mappeidentitet og sti-resolution | Ikke fundet i det gennemgåede scope | Ingen dedikeret file resource-model påvist |
| Listning/søgning/læsning af lokale filer | Ikke fundet som komplet adapter | Skal ikke udledes af generisk `search`-intent |
| Kopiér/flyt/omdøb/slet | Ikke fundet som komplet adapter | Kræver eksplicitte kontrakter, validering og tests |
| Filrettigheder, symlinks, mountpoints og konflikter | Ikke påvist som samlet løsning | Sikkerheds- og korrekthedskrav før produktion |
| Ubuntu Desktop Settings-/driver-/netværksintegration | Ikke påvist som generisk System API | Kræver separat kortlægning af hver subsystemgrænseflade |
| React → Tauri → daemon IPC | Eksisterende arkitektur | UI-wrapper kalder Tauri command; Tauri bro bruger socket-baseret JSON-RPC |
| Ubuntu 26.04 runtime-verifikation | Ikke udført i denne audit | Skal ske på faktisk målplatform |

## 4. IPC- og præsentationslag

### Frontend

`ui/src/lib/ipc.ts` eksponerer en generisk `sendIpcRequest(daemon, method, params)` og videresender kald til Tauri-commanden `send_ipc_request`. Den indeholder også en test-hook og en generisk fejlbesked-parser. Den er en transport-wrapper, ikke et Ubuntu-system-API.

### Tauri

`ui/src-tauri/src/ipc.rs` fungerer som bro til daemon-sockets, har en eksplicit liste over accepterede daemon-navne, request-/responsegrænser, timeout og retry for udvalgte forbindelsesfejl. Dette er IPC-infrastruktur; det udfører ikke selv filoperationer eller styrer Ubuntu-indstillinger.

### Python IPC

`app/ipc/transport.py` bruger Unix domain sockets på Unix og loopback TCP i Windows-kompatibilitetsstien. `app/ipc/jsonrpc.py` centraliserer JSON-RPC-svar og standardiserer nu `user_message` i fejlresponsen. Eksisterende IPC-auditdokumentation beskriver desuden statiske fund om framing, socket-livscyklus, peer-kontrol og ressourceloft. De punkter skal valideres og lukkes efter prioritet før en sikkerhedsgrænse betragtes som produktionsklar.

### Arkitekturregel

UI bør sende typede kommandoer til EiraOS-applikationslaget; UI-komponenter må ikke selv opbygge stier, kalde shell-kommandoer eller håndtere Polkit. Domænelogik skal kunne testes uden React og uden en kørende Ubuntu-session. Systemadaptere skal returnere typede resultater og fejl gennem EiraOS-kontrakten.

## 5. Foreslået målarkitektur for filoperationer

```text
React UI / filvisning
        │ typede UI-kommandoer
        ▼
EiraOS Application Use Cases
  - ListDirectory
  - SearchFiles
  - ReadFile
  - Copy / Move / Rename
  - Delete (særskilt bekræftelsesflow)
        │ EiraSystemAPI-kontrakt
        ▼
EiraOS File Operations API
  - input-/sti-validering
  - adgangskontrol og brugerbekræftelse
  - audit, idempotens og fejlkoder
        │ adapter-interface
        ▼
Ubuntu File Adapter
  - almindelige filer: brugerens POSIX-rettigheder
  - desktop-/portalflows: GIO/GVfs/XDG portals, hvor det passer
  - diske og mount: UDisks2, separat capability
        ▼
Ubuntu Desktop / Linux kernel / filsystem
```

EiraOS-kontrakten skal eje semantik og versionering. Adapteren må gerne anvende eksisterende Ubuntu-/freedesktop-grænseflader, men UI må ikke blive afhængigt af interne Cockpit- eller desktop-UI-implementeringer. Cockpit kan vurderes som en genbrugsadapter for relevante administrationsfunktioner; det er ikke en erstatning for en universel API-kontrakt.

## 6. Minimumskrav før filhandlinger aktiveres

- Brug brugerens egne rettigheder som standard; ingen generel root-shell eller generisk privilegeret fil-API.
- Afvis stier, der ikke er tilladt i operationens scope; håndtér symlinks, `..`, mountpoints og TOCTOU-risici bevidst.
- Sletning og overskrivning kræver tydelig forhåndsvisning og bekræftelse; operationen skal kunne rapportere delvise fejl.
- Brug operation-/request-id til at håndtere gentagne kald og usikre retries.
- Registrér audit-resultatet efter den faktiske operation, ikke blot når en intent er godkendt.
- Adskil brugerrettigheder fra privilegerede handlinger. Brug systemets normale tilladelsesmodel og en snæver Polkit-aktion kun hvor det er nødvendigt.
- Test mod midlertidige kataloger: tilladelse/afvisning, manglende fil, navnekollision, symlink, fil ændret under operation, disk fuld, read-only mount og afbrudt operation.
- Tilføj kontrakttests, adaptertests og integrationstests på den valgte Ubuntu 26.04.x LTS-baseline.

## 7. Anbefalet implementeringsrækkefølge

1. **Sikkerhedsgate:** Ret og test fail-closed-håndhævelsen for `can_execute=False`; afklar hvilken intent-daemon der er autoritativ.
2. **Kontrakt:** Definér versioneret `EiraSystemAPI` og typede filressourcer/resultater/fejl uden Ubuntu-specifik logik i UI.
3. **Læs-only MVP:** Implementér `list_directory` og `stat/read metadata` med brugerrettigheder, allowlist/scope og automatiske tests.
4. **Søgning og læsning:** Tilføj eksplicit begrænsning af katalogscope, filstørrelse, tekstkodning og følsomme filer.
5. **Ikke-destruktive ændringer:** Kopiér/flyt/omdøb med kollisionspolitik, atomisk adfærd hvor muligt og audit.
6. **Destruktive operationer:** Sletning/overskrivning først efter separat trusselsmodel og bekræftelses-/gendannelsesdesign.
7. **Desktop-/systemfunktioner:** Kortlæg Settings, netværk, drivere, enheder, diske og tjenester hver for sig; brug relevante systeminterfaces og test på Ubuntu 26.04.x.

## 8. Verifikationsplan

Denne audit dokumenterer ikke, at tests er bestået. Næste trin er:

- Kør relevante eksisterende parser-, intent-, IPC- og sikkerhedstests i CI.
- Tilføj regressionstest, der beviser, at `can_execute=False` aldrig kan bekræftes.
- Søg efter alle eksekveringsveje og verificér forskellen mellem `intent_engine` og `intentd`.
- Tilføj arkitekturtest, der forhindrer Ubuntu-/filesystem-kode i UI-laget.
- På Ubuntu 26.04.x: verificér socket-ejerskab/permissions, session, D-Bus-/Polkit-adgang, portal-/GIO-adfærd og faktiske filoperationer.
- Registrér præcise Ubuntu-, kernel-, desktop- og pakk versioner sammen med testresultaterne.

## 9. Relevante filer gennemgået

- `app/intent_parser.py`
- `app/capability.py`
- `app/models.py`
- `app/daemons/intent_engine.py`
- `app/executor.py`
- `app/daemons/intentd.py` (eksistens og adskilt service; kun delvist gennemgået)
- `app/ipc/jsonrpc.py`
- `app/ipc/transport.py`
- `ui/src/lib/ipc.ts`
- `ui/src-tauri/src/ipc.rs`
- `manifests/erp-ordre.capability.json`
- `manifests/public360.capability.json`
- `tests/test_intentd_enforcement.py`
- `docs/audit/B_IPC.md`
- `docs/EIRA_Sprint8_Audit_IPC.md`

Repository-træet indeholder mange filer; denne audit er et målrettet scope og ikke en påstand om, at hver eneste fil i repository’et er manuelt gennemgået.
