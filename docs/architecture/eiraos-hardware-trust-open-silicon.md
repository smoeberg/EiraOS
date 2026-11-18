# EiraOS Hardware Trust & Open Silicon

**Status:** Draft for owner review — non-normative  
**Scope:** Architecture and integration direction only  
**Target platform:** Ubuntu 26.04 LTS  
**Change boundary:** No runtime implementation, no new daemon, and no changes to Gate, Fleet, enrollment, or Phase 0 contracts are authorized by this document.

> **AI'en foreslår. Gaten afgør. Systemet udfører.**  
> Hardware kan levere beviser og funktioner. Hardware kan ikke selv tildele EiraOS-rettigheder.

## 1. Formål

Dette notat beskriver, hvordan EiraOS på sigt kan forstå og udnytte hardwarefunktioner på en sikker, leverandørneutral og versionsstyret måde — og hvor åbne hardwareprojekter som GoIT Hardware Hub eventuelt kan bidrage.

EiraOS er et højniveau, policy- og sikkerhedsfokuseret OS-lag oven på Ubuntu 26.04. Ubuntu og Linux-kernen ejer den fysiske hardwareadgang, drivere og de underliggende mekanismer. EiraOS ejer sine egne kontrakter, policy, orchestration, brugeroplevelse og håndhævelse af beskyttede handlinger.

GoIT Hardware Hub er et separat lavniveau-udviklingsspor for genbrugelige hardware-IP-komponenter og værktøjer til at oprette, kontrollere og teste dem. Det er ikke en EiraOS-runtime-komponent.

Formålet er derfor ikke at flytte hardwarestyring ind i Gate Kernel. Formålet er at etablere en tydelig kontraktgrænse mellem hardware og firmware, Ubuntu/Linux' drivere og standardgrænseflader, EiraOS' hardware- og enhedstillidsmodel, Fleet og Device Registry samt Gate Kernel og EiraOS' policy.

Notatet er et arkitekturforslag. Det ændrer ikke eksisterende normative kontrakter eller implementeringsstatus.

## 2. Nuværende EiraOS-grundlag

Forslaget skal bygge på det, der allerede er besluttet eller implementeret. Det må ikke opfinde en parallel identitets-, rettigheds- eller tillidsmodel.

### 2.1 Gate og rettigheder

- Gate Kernel er den autoritative grænse for beskyttede handlinger.
- ADR-0002 fastlægger to handlingsfamilier — EDP og EiraSystemAPI — gennem én Gate og samme sikkerhedsgrænse.
- Gate må ikke omgås af hardwareadaptere, drivere, AI-modeller eller værktøjer.
- Ifølge ADR-0003 er Fleet den autoritative kilde til EiraOS-rettigheder. Endpointet læser, cacher og håndhæver signerede rettighedssæt; det opfinder eller udvider ikke rettigheder lokalt.
- Hardwareoplysninger må derfor aldrig i sig selv give en bruger, proces eller enhed nye rettigheder.

Relevante kilder: *docs/decisions/ADR-0002-gate-to-handlingsfamilier.md*, *docs/decisions/ADR-0003-rettigheder-fra-fleet.md*, *specs/GATE-KERNEL-1.0.md*, *specs/EIRA-RIGHTS-SET-1.0.md*.

### 2.2 Fleet og to eksisterende enhedsidentitetsmekanismer

EiraOS-repositoriet indeholder allerede to forskellige mekanismer, som ikke må blandes sammen:

1. **Fleet-parring og synkronisering** i *app/fleet/device_registry.py*: en parret enhed registrerer en X25519-nøgle til krypterede tilstandspayloads og en Ed25519-signaturnøgle. Enhedens id er et fingeraftryk af signaturnøglen. Synkroniseringskald bindes til engangs-challenges og signeres.
2. **Managed enrollment mod Fleet Rights API** i *app/rights/enroll.py* og *specs/EIRA-FLEET-RIGHTS-API-1.0.md*: en managed enhed danner en ECDSA P-256-enhedsnøgle i TPM 2.0. Nøglen er ikke-eksporterbar; kun en indpakket nøgleblob opbevares på disken, og en CSR sendes til Fleet. Managed enrollment afbrydes, hvis TPM 2.0 mangler.

Disse mekanismer har forskellige formål og nøgletyper. En vellykket Fleet-parring er ikke i sig selv TPM-attestation. TPM-baseret mTLS-enhedsidentitet er heller ikke i sig selv bevis for, at den kørende software eller firmware er uændret.

### 2.3 TPM og attestation: eksisterende beslutning

Fleet Rights API 1.3 indeholder allerede en eksplicit beslutning:

- Managed-enheder kræver TPM 2.0.
- Enhedsnøglen dannes i TPM'en med egenskaber, der forhindrer eksport eller kloning af den private nøgle.
- Det beskytter mod, at en kopieret disk på en anden maskine kan genbruge enhedens Fleet-identitet.
- Det gør ikke root til en sikkerhedsgrænse. Root kan stadig ændre den kode, der kontrollerer TPM-beviser, eller ændre lokal tilstand efter verifikation.
- Remote attestation med TPM quote er udskudt, indtil en målt og beskyttet opstartskæde er etableret — herunder Secure Boot, dm-verity på /usr og PCR-målinger — og Fleet kan verificere beviset ved enrollment og heartbeat.

Dette notat genåbner ikke disse beslutninger. Det skal respektere deres begrænsninger og beskrive en mulig senere udvidelse.

Kilde: *specs/EIRA-FLEET-RIGHTS-API-1.0.md* §2, §6 og §8.

### 2.4 Sikkerhedsmodellens nuværende grænse

Den nuværende sikkerhedsmodel beskytter primært mod programmer, der kører som desktop-brugeren, andre lokale brugere, modelprocessen og netværket. Root, fysisk adgang, kernen og firmware er udtrykkeligt uden for den nuværende brugerlandstrusselsmodel.

Et hardwaretillidslag må ikke fremstille TPM-tilstedeværelse, Secure Boot-status eller en lokal måling som en garanti mod root eller fysisk kompromittering. En sådan garanti kræver en dokumenteret kæde fra hardware-roden gennem opstart og beskyttet software til en uafhængig verifier.

Kilde: *docs/security/SIKKERHEDSMODEL.md* og Fleet Rights API 1.3.

## 3. Foreslået arkitekturplacering

Hardware Trust & Device Trust er et logisk ansvarsområde — ikke nødvendigvis en ny daemon eller et nyt privilegeret subsystem.

~~~text
┌──────────────────────────────────────────────────────────────┐
│ EiraOS Experience / Applications / AI                        │
└──────────────────────────────┬───────────────────────────────┘
                               │ typed intent / domain contracts
┌──────────────────────────────▼───────────────────────────────┐
│ Gate Kernel                                                   │
│ Policy · consent · Fleet authorization · execution · audit   │
└──────────────────────────────┬───────────────────────────────┘
                               │ consumes policy-approved evidence
┌──────────────────────────────▼───────────────────────────────┐
│ Eira Hardware & Device Trust                                  │
│ Device profile · capability evidence · trust-state reporting │
│ No independent grants · no direct privileged execution       │
└──────────────────────────────┬───────────────────────────────┘
                               │ standard OS interfaces
┌──────────────────────────────▼───────────────────────────────┐
│ Ubuntu / Linux kernel / drivers / system services             │
└──────────────────────────────┬───────────────────────────────┘
                               │
┌──────────────────────────────▼───────────────────────────────┐
│ Physical hardware · firmware · TPM · FPGA · CPU · GPU · I/O   │
└──────────────────────────────────────────────────────────────┘

Separate engineering toolchain:
GoIT Hardware Hub / goit → hardware IP development, checks and tests
~~~

### 3.1 Ansvar

**Ubuntu/Linux ejer:**
- hardware enumeration, kernel drivers og standardiserede device interfaces,
- adgangskontrol på OS-niveau,
- Secure Boot- og TPM-integration via understøttede platformværktøjer,
- strømstyring og fysisk enhedstilstand.

**Eira Hardware & Device Trust ejer på sigt:**
- EiraOS' leverandørneutrale hardwareprofil,
- normalisering af capabilities og evidens,
- sammenstilling af enhedsidentitet med verificerbare hardwareoplysninger,
- tydelig rapportering af tillidsstatus og manglende evidens,
- en versionsstyret grænseflade til Fleet og Gate.

**Fleet ejer:**
- autoritativ desired state og rettighedstildeling,
- eventuelle fremtidige krav til hardwareprofiler for managed-enheder,
- eventuel central vurdering af remote attestation,
- registrering, tilbagekaldelse og compliance-status på tværs af enheder.

**Gate ejer:**
- afgørelser om beskyttede handlinger,
- kontrol af rettigheder fra Fleet,
- eventuel håndhævelse af eksplicitte, policy-definerede hardwareforudsætninger,
- audit af den konkrete beslutning.

**GoIT og andre hardwareprojekter ejer:**
- hardware-IP, værktøjer, komponenttests og build-/verifikationsartefakter,
- ikke EiraOS-identitet, brugerrettigheder eller runtime-policy.

### 3.2 Hvad laget ikke gør

Hardware Trust & Device Trust må ikke:

- erstatte Linux-kernen eller dens driver-model,
- blive en alternativ executor eller en vej uden om Gate,
- tildele Fleet-rettigheder,
- behandle en selvdeklareret capability som et sikkerhedsbevis,
- sidestille TPM-nøglebesiddelse med measured boot eller remote attestation,
- gøre GoIT til en runtime-afhængighed,
- kræve FPGA, RISC-V eller specialhardware for at køre EiraOS på en almindelig PC.

## 4. Hardware Capability Manifest — konceptuelt forslag

Et hardwaremanifest kan blive den fælles, versionsstyrede beskrivelse af en enheds hardware og dens capabilities. I første omgang er det en dokumentations- og datamodelidé; det er ikke en godkendt API eller et implementeret schema.

Manifestet skal beskrive både *hvad der hævdes*, og *hvilket bevis der understøtter påstanden*. Det må ikke blot være en liste med capability-navne.

### 4.1 Evidensniveauer

Følgende niveauer foreslås:

| Niveau | Betydning | Eksempel | Kan bruges som sikkerhedsbevis? |
|---|---|---|---|
| **Declared** | Enheden, firmware eller leverandør oplyser en funktion | Producentens modeldata siger TPM 2.0 | Nej |
| **Observed** | EiraOS/Ubuntu har observeret funktionen via en lokal OS-grænseflade | TPM-enhed findes; driver rapporterer en funktion | Nej, ikke alene |
| **Verified** | En defineret kontrol har valideret påstanden mod en betroet kilde eller et verificerbart artefakt | Signeret firmware-/IP-manifest valideret mod en kendt nøgle; TPM-egenskaber kontrolleret med en specificeret procedure | Kun hvis den konkrete policy accepterer kontrolmetoden og evidensen er aktuel |
| **Attested** | En uafhængig verifier har valideret et kryptografisk bevis bundet til en kendt enhed og en specificeret målekæde | Fleet verificerer TPM quote og PCR-målinger mod godkendt reference og frisk challenge | Kan indgå i sikkerhedspolitik, hvis attestationens scope, freshness og verifier er godkendt |

Niveauerne må ikke forveksles med en generel tillidsscore. Et manifest skal bevare den konkrete evidens, dens kilde, tidspunkt, scope og verifikationsmetode. En høj score eller et grønt UI-badge skaber ikke autorisation.

Der bør også være eksplicitte tilstande for *unknown*, *unavailable*, *stale*, *failed* og *unsupported*. Manglende evidens må aldrig opgraderes til en positiv status.

### 4.2 Mulig datamodel

Et fremtidigt schema kan overveje felter som:

- **manifest_version:** schema-version, ikke hardwareversion.
- **device_ref:** reference til den allerede etablerede Eira/Fleet-enhedsidentitet.
- **collected_at:** tidspunkt for indsamling.
- **platform:** arkitektur, firmware-/bootmiljø og relevante OS-identifikatorer.
- **claims[]:** capability-id, version, evidensniveau, kilde og status.
- **evidence[]:** type, digest, issuer/verifier, tidspunkt, freshness/challenge-reference og reference til måle- eller attestationsdata.
- **provenance:** oprindelse for hardware-IP, firmware, bitstream eller build-artefakt, når den kan dokumenteres.

Dette er alene et feltkatalog. Det fastlægger ikke endnu kanonisk serialisering, signaturformat, nøglehierarki, transport eller Fleet API.

### 4.3 Minimal realistisk PC-profil

Et almindeligt eksempel bør være første referenceprofil — ikke en hypotetisk FPGA-enhed:

| Observation | Mulig status ved første indsamling | Hvad det faktisk beviser |
|---|---|---|
| TPM 2.0 findes | Observed | OS'et kan se en TPM-grænseflade; ikke i sig selv at TPM'en er korrekt provisioneret |
| Managed enrollment-nøgle dannet i TPM | Verified efter den eksisterende enroll-procedure | Enhedens mTLS-nøgle er bundet til TPM'en og ikke-eksporterbar efter kontraktens forudsætninger |
| Secure Boot er slået til | Observed, indtil en verificeret målekæde er defineret | En lokal statusrapport siger, at Secure Boot er aktiv; ikke at alle efterfølgende målinger er godkendt |
| PCR-målinger / TPM quote | Unavailable eller Not implemented i den nuværende kontrakt | Der er endnu ikke et godkendt remote-attestation-flow |
| GPU eller anden accelerator | Observed, hvis OS-driveren identificerer den | Enheden er til stede; ikke at den er egnet eller sikker til en bestemt workload |

En managed PC kan derfor have en TPM-bundet enhedsidentitet uden at være attesteret. Det skal være synligt i modellen.

## 5. Fleet- og Gate-integration

### 5.1 Fleet og Device Registry

Den nuværende Fleet-model skal forblive autoritativ for enhedsidentitet, pairing, revocation og rettigheder. Et fremtidigt hardwaremanifest skal referere til en eksisterende enhedsidentitet; det må ikke oprette en parallel identitetsautoritet.

Mulige senere funktioner — alle kræver særskilt kontrakt og ejerbeslutning:

- registrering af hardwareprofil og capability-inventar,
- versioneret indsendelse af manifest og evidens,
- udløb og genindsamling af forældede oplysninger,
- central registrering af attestation-resultater,
- policykrav til bestemte hardwareprofiler i managed mode.

Før en sådan udvidelse skal det afklares, hvordan den lokale Fleet Device Registry og managed TPM-enrollment bindes sammen. De nuværende nøglemekanismer er forskellige og må ikke antages at være samme identitet.

### 5.2 Gate Kernel

Gate forbliver den eneste autoritative sikkerhedsgrænse. Hardwarecapabilities er ikke rettigheder.

En fremtidig Gate-policy kan eventuelt kræve en verificeret eller attesteret hardwareegenskab som en *forudsætning* for en bestemt handling. Det kræver mindst:

1. En eksplicit policy-post, som navngiver capability, evidensniveau, verifier og freshness-krav.
2. En entydig binding mellem evidensen og den aktuelle enhed.
3. Kontrol af, at evidensen ikke er udløbet, tilbagekaldt eller ændret.
4. En eksplicit beslutning om adfærd ved manglende eller utilgængelig evidens.
5. Audit af den konkrete evidensreference og policyversion.

Gate må ikke udlede rettigheder fra hardwareprofilen. Fleet-rettighederne er fortsat den autoritative kilde til *hvad* en principal må. Hardwareevidens kan kun indgå som en særskilt policy-forudsætning, hvis det senere besluttes.

Ingen ændring af Gate 1.1's handlingsfamilier eller otte valideringslag foreslås her.

### 5.3 Fail-closed uden at gøre almindelige PC'er ubrugelige

Fail-closed betyder, at en handling, som kræver et bestemt hardwarebevis, afvises, hvis beviset mangler, er ugyldigt, for gammelt eller ikke kan verificeres.

Det betyder ikke, at hele EiraOS skal nægte at starte, blot fordi en valgfri hardwarefunktion mangler. Hver capability skal have en eksplicit klassifikation:

- **Required for managed enrollment:** fx TPM 2.0 efter den eksisterende Fleet-kontrakt.
- **Required for a specific protected operation:** kun når en godkendt policy udtrykkeligt kræver det.
- **Optional capability:** funktionen kan bruges, hvis den findes, men er ikke et sikkerhedskrav.
- **Unavailable/unsupported:** EiraOS rapporterer begrænsningen og tilbyder en sikker alternativ vej, hvis en sådan findes.

En manglende AI-accelerator må fx ikke blokere almindelig lokal inference på CPU. En manglende attestation må derimod blokere en operation, hvis en senere, godkendt managed-policy gør attestation til et krav.

## 6. GoIT Hardware Hub — konkret status og mulig rolle

GoIT skal vurderes ud fra de artefakter, der faktisk findes — ikke ud fra den fulde vision for et europæisk open-silicon-økosystem.

De to undersøgte repositories er:

- **goit-project/hardware-hub:** et lille VHDL-bibliotek med bl.a. goit_common og goit_image, konkrete counter- og coordinate-counter-komponenter samt test benches.
- **goit-project/hardware-hub-utility:** Python-baseret CLI-/udviklingsværktøj til komponentoprettelse, afhængigheder, kontrol og testintegration, bl.a. med VUnit, GHDL og HDLMake.

Den gennemgåede kildekode dokumenterer en begyndende arbejdsgang for genbrugelige hardwarekomponenter og verificering. Den dokumenterer **ikke** et færdigt EiraOS-board, en AI-matrixaccelerator, en Root-of-Trust-implementering eller en komplet secure-boot-løsning. De undersøgte ZIP-snapshots havde desuden tomme LICENSE-filer; licens og rettigheder skal derfor afklares, før kode eller IP genbruges. Den tidligere kildegennemgang var en statisk gennemgang af snapshots, ikke en fuld hardwareverifikation eller en reproduceret VHDL-simuleringskørsel.

### 6.1 Hvad GoIT kan bidrage med først

Den realistiske start er udviklingsværktøj og dokumenteret IP-proveniens:

- reproducerbar komponentopbygning,
- eksplicitte afhængigheder og versionsidentiteter,
- test benches og simuleringsresultater,
- licens- og oprindelsesmetadata,
- senere eventuelt signerede build-manifester for IP, firmware eller FPGA-bitstreams.

Et sådant manifest kan på sigt være input til EiraOS' hardwareprofil. Det er ikke i sig selv en attestationskæde og giver ikke enheden tillid uden uafhængig kontrol.

### 6.2 Hvad GoIT ikke skal være

- Ingen GoIT CLI eller Python-afhængighed i EiraOS' runtime.
- Ingen VHDL-komponenter ind i Gate Kernel.
- Ingen påstand om at GoIT leverer TPM, secure boot eller AI-acceleratorer, medmindre konkrete, verificerede artefakter dokumenterer det.
- Ingen adoption af komponenter, før licens, vedligeholdelsesstatus, værktøjsversioner, testreproducerbarhed og hardwaremål er afklaret.

GoIT er en mulig leverandør og inspirationskilde for åbne hardware-IP-artefakter — ikke en betroet autoritet for EiraOS' device identity eller policy.

## 7. Forholdet til lokal AI og acceleratorer

Hardwareacceleratorer kan senere være relevante for eira-modeld og andre lokale workloads. Det bør dog være et separat forbrugerspor oven på den generelle capability-model.

- Driver og runtime rapporterer, hvilke funktioner der er tilgængelige.
- EiraOS vælger kun en accelerator gennem en eksplicit, understøttet adapter.
- En accelerator må ikke få netværksadgang eller udvidede rettigheder, fordi den er til stede.
- Fejl eller manglende accelerator skal føre til en dokumenteret fallback, fx CPU, hvis modellen og ressourcerne tillader det.
- Sikkerhedskritiske workloads må ikke flyttes til hardware, hvis dens tillids- og isolationsmodel ikke er dokumenteret.

GoIT's nuværende undersøgte komponenter dokumenterer ikke en sådan accelerator. Dette afsnit beskriver alene en fremtidig anvendelse af en generisk hardware-capability-kontrakt.

## 8. Trusselsmodel og sikkerhedsinvarianter

Følgende invarianter foreslås for et fremtidigt hardwaretillidslag:

1. **Hardwareidentitet er ikke brugeridentitet.** En enhedsnøgle identificerer en enhed eller dens nøgleindehaver, ikke den menneskelige principal.
2. **Hardwarecapability er ikke autorisation.** Ingen capability kan oprette eller udvide Fleet-rettigheder.
3. **Declared er aldrig verified.** En selvdeklaration kan bruges til inventar, ikke som sikkerhedsforudsætning.
4. **TPM-nøglebesiddelse er ikke measured boot.** Ikke-eksporterbar nøgle beviser ikke, at OS eller firmware er uændret.
5. **Attestation er scoped og tidsbundet.** Et quote skal bindes til en frisk challenge, en bestemt enhed, en bestemt målekæde og en bestemt verifier.
6. **Evidence over claims.** Manglende, forældet, tvetydig eller ugyldig evidens repræsenteres eksplicit.
7. **Gate er eneste håndhæver.** Ingen hardwaretjeneste eller accelerator må udføre beskyttede systemhandlinger direkte.
8. **Fleet er rettighedskilden.** Hardwarelaget kan rapportere forhold; det kan ikke tildele rettigheder.
9. **Ingen falsk sikkerhed mod root.** Så længe root kan ændre den lokale verifier eller cache, må lokal verifikation ikke beskrives som en grænse mod root.
10. **Almindelig hardware forbliver understøttet.** TPM/attestation-krav gælder kun dér, hvor den eksisterende kontrakt eller en senere eksplicit policy kræver dem.

## 9. Afgrænsning for første fase

Første fase er alene arkitektur og evidensbaseret afklaring.

**Indgår:**
- dette arkitekturnotat,
- kortlægning af eksisterende Fleet-enhedsidentitet og TPM-enrollment,
- dokumentation af forskellen mellem declared, observed, verified og attested,
- inventar af de konkrete GoIT-repositories, licenser og reproducerbarhed.

**Indgår ikke:**
- ny daemon eller systemd-unit,
- nyt IPC-endpoint,
- ændring af Phase 0 Event Bus eller RPC,
- ændring af Gate Kernel 1.1 eller EDP/EiraSystemAPI,
- ændring af Fleet Rights API eller Rights Set,
- nyt hardwaremanifest-schema som normativ kontrakt,
- remote attestation-implementering,
- AI-accelerator eller FPGA-prototype,
- krav om specialhardware til almindelige EiraOS-installationer.

## 10. Foreslået videre rækkefølge

| Trin | Leverance | Forudsætning / accept |
|---|---|---|
| H0 — Arkitekturreview | Ejerreview af dette notat og afklaring af åbne spørgsmål | Ingen kodeændring |
| H1 — Evidens- og identitetskortlægning | Kortlægning af eksisterende device_registry, TPM enrollment, Fleet identity og sikkerhedsgrænser | Ingen ændring af eksisterende kontrakter |
| H2 — Manifestudkast | Ikke-normativt JSON-eksempel og schemaforslag for en almindelig TPM-PC | Ejerbeslutning om dataejerskab, kilde og signaturmodel |
| H3 — Read-only discovery | Måling/rapportering af eksisterende TPM-, Secure Boot- og driverstatus | Egen kontrakt, tests og tydelig status; ingen Gate-håndhævelse |
| H4 — Fleet integration design | Forslag til versioneret transport, freshness, revocation og attestation-evidens | Afklaring af binding mellem de to nuværende enhedsidentiteter |
| H5 — Attestation | Remote attestation først efter målt og beskyttet boot-kæde | Særskilt ADR, Fleet-kontrakt og sikkerhedsreview |
| H6 — Open Silicon pilot | Reproducerbar GoIT-komponent med licens, tests og build-proveniens | Konkret hardwaremål og verificeret vedligeholdelses-/licensstatus |

Rækkefølgen er et forslag, ikke en ændring af den gældende udviklingsplan.

## 11. Åbne beslutninger

Følgende må ikke afgøres stiltiende i en implementation:

1. Er hardwareprofilen en del af Fleet Device Registry, en separat EiraOS-ejet kontrakt eller begge dele med klart ejerskab?
2. Hvordan bindes den lokale Ed25519/X25519-parring til managed TPM-enrollment, uden at de to nøgletyper og formål blandes sammen?
3. Hvilke capabilities skal kun være inventar, og hvilke kan være policy-forudsætninger?
4. Hvem verificerer attestation — endpointet, Fleet eller begge med forskellige roller?
5. Hvilke reference-målinger og firmware-/OS-versioner skal accepteres, og hvordan håndteres opdateringer og tilbagekaldelse?
6. Hvilke hardwaremanifest- og IP-proveniensformater kan genbruges fra eksisterende åbne standarder i stedet for at opfinde nye?
7. Hvilke GoIT-artefakter har en verificerbar licens og en reproducerbar test-/build-proces?

## 12. Samlet anbefaling

EiraOS bør etablere Hardware Trust & Open Silicon som et selvstændigt arkitekturspor, men begynde med dokumentation og kontraktgrænser — ikke en ny runtime-komponent.

Den praktiske prioritering er:

- **D — udviklingsværktøj og IP-proveniens:** første konkrete GoIT-spor.
- **A — hardwareplatform og Fleet-profiler:** langsigtet arkitekturmål.
- **C — trusted hardware:** bygger videre på den eksisterende TPM-beslutning og den senere, endnu ikke implementerede attestation.
- **B — AI-acceleratorer:** først når en konkret og verificerbar platform findes.
- **E — europæisk suveræn stack:** strategisk retning, der kræver flere uafhængige projekter og leverandører.

Den vigtigste regel er, at EiraOS skal kunne beskrive og kontrollere hardware uden at blive afhængig af én hardwareleverandør eller ét IP-projekt. GoIT kan bidrage til den åbne hardwareværktøjskæde; Fleet forbliver autoritativ for rettigheder; Gate forbliver autoritativ for beskyttede handlinger.

---

## Kilder i EiraOS

- *docs/decisions/ADR-0002-gate-to-handlingsfamilier.md*
- *docs/decisions/ADR-0003-rettigheder-fra-fleet.md*
- *specs/GATE-KERNEL-1.0.md*
- *specs/EIRA-RIGHTS-SET-1.0.md*
- *specs/EIRA-FLEET-RIGHTS-API-1.0.md*
- *app/rights/enroll.py*
- *app/fleet/device_registry.py*
- *docs/security/SIKKERHEDSMODEL.md*
- *docs/architecture/eiraos-architecture-baseline-1.0.md*

## Eksterne GoIT-artefakter undersøgt

- *goit-project/hardware-hub*
- *goit-project/hardware-hub-utility*

GoIT-status i dette notat bygger på de to undersøgte kildearkiver og den tilhørende statiske gennemgang. Den er ikke en påstand om fuld funktionel verifikation af hardware eller værktøjskæde.
