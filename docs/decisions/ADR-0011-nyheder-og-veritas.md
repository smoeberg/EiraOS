# ADR-0011 — Nyheder i livets indbakke: afsender, håndværk og efterprøvede påstande

**Status:** Foreslået, til ejerens accept (25. november 2026). N1, N2, N4, N6 og N10 er ejerens retning; resten er et forslag.
**Gælder for:** `veritasd` og `app/veritas/`, Veritas HUD (`ui/src/components/VeritasHUD.tsx`), livets indbakke og dens adaptere (ADR-0006), kontekster (ADR-0005), Fleet-rettigheder (ADR-0003)
**Relateret:** [ADR-0003](ADR-0003-rettigheder-fra-fleet.md), [ADR-0005](ADR-0005-kontekster-og-datas-hjem.md), [ADR-0006](ADR-0006-livets-indbakke.md), [EDP 1.0](../../specs/EDP-1.0.md), [AI-INTERFACE 1.0](../../specs/AI-INTERFACE-1.0.md), [fællesskabsfundamentet](../proposals/EIRA_Human_and_Community_Centric_Foundation_v0.1.md) (#165), [arkitekturen §9](../architecture/eiraos-system-architecture.md), fundregistret G-8 og G-12

## Normativ regel

> **EiraOS viser, hvem der står bag en nyhed, og hvordan den er lavet. EiraOS afgør aldrig, om en nyhed er sand. Kun en konkret påstand kan efterprøves, og kun mod en primærkilde, der vises. Hvad personen vil se, er personens eget valg.**
>
> **Det er en samfundspligt at levere et sted, hvor man kan få troværdige nyheder. Derfor er det gratis for medierne at være med, og det er et eksternt nævn, ikke Eira, der afgør, hvem der er med.** (ejeren, 25. november 2026)

## Kontekst

Ejeren ønsker en nyhedsstrøm i EiraOS med en validering af troværdigheden. Baggrunden er, at de kommercielle platforme i stigende grad er præget af reklame, skjult reklame og svindel, og at AI-genereret indhold gør det sværere at vide, hvad man står med. Rapporten *Sociale platformes økonomiske magt* (Magtudredningen 2.0) konkluderer, at betegnelsen "sociale medier" i dag er misvisende (DR, 25. november 2026).

Udgangspunktet var et notat om en platform, der giver brugeren tryghed ved at vise "en valideret troværdighedsvurdering — ikke en dom over, hvad der er sandt, men et gennemsigtigt fundament". Notatet skelner mellem *sandhed* (kan platformen ikke afgøre), *troværdighed* (kan vurderes) og *validitet* (vurderingen følger faste, offentlige kriterier).

Det, der findes i dag:

- `veritasd` (pakket) med tre lag: regler for kilder og sprog (`layer1_rules.py`), signaturverifikation via QEAA/EUDI (`layer2_qeaa.py`) og mønstre over tid (`layer3_graph.py`), samt C2PA for billeder (`c2pa_engine.py`). Den leverer en `trust_score` i [0,1], som også bruges i EDP's `veritas`-felt for handlinger.
- `layer1_rules.py` har en hardkodet liste over godkendte og afviste domæner (`DEFAULT_ALLOWLIST`, `DEFAULT_DENYLIST`).
- `veritas-shield/` er en mock uden for pakken (fund G-8; fjernes i F1c.5).
- Lag 2 og C2PA kan ikke køre i pakken, så halvdelen af `trust_score` er altid 0 (fund G-12; F1c.7).
- Der er ingen nyhedsstrøm.

## Beslutninger

### N1 — Nyheder er en kanal, ikke en feed (ejerens retning)

Nyheder kommer ind gennem en adapter efter ADR-0006 L1–L2 og lander i livets indbakke i personens egen kontekst. Personen vælger selv sine kilder: fra mediekataloget (N10) eller ved selv at tilføje en kilde (fx RSS/Atom). Selvvalgte kilder uden for kataloget spærres ikke ude, men vises som *ikke verificeret afsender* (N2, N6).

Det, der vises fra et tilmeldt medie, er overskrifter og korte nyheder med link til mediets egen uddybende historie, også når den ligger bag mediets betalingsmur.

- Ingen central nyhedsstrøm, ingen rangering efter engagement, ingen anbefalinger fra Eira (#165 §6 og §8).
- Rækkefølgen er tid eller personens egen sortering.
- Nyheder er indhold i en kontekst og krydser ikke kontekstgrænser (ADR-0006 L5).

### N2 — Afsenderen vurderes på bevist oprindelse (ejerens retning)

Afsenderen skal vurderes, og kravet er, at indholdet er skabt af et menneske, der står ved det. Det afgøres ud fra **oprindelse, der kan bevises**, ikke ud fra analyse af teksten:

| Tegn | Hvad det viser | Kilde i EiraOS |
|---|---|---|
| Signatur på artiklen | Et navngivet menneske eller medie står ved netop denne tekst | Lag 2 (QEAA/EUDI) |
| Content credentials på billeder og video | Hvor billedet kommer fra, og om det er redigeret eller genereret | C2PA |
| Optaget i mediekataloget | Et eksternt nævn har konstateret, at mediet opfylder de offentlige kriterier, og mediets nøgle er registreret | Mediekataloget (N10) |

Resultatet er en status med begrundelse: *verificeret afsender* (med hvad der er verificeret) eller *ikke verificeret afsender*. Det er aldrig "upålidelig".

- **AI-detektion er ikke et grundlag.** Værktøjer, der gætter på, om en tekst er maskinskrevet, rammer forkert på mennesker og kan omgås. De må ikke indgå i afsendervurderingen.
- **Ingen lister over godkendte medier i koden.** `DEFAULT_ALLOWLIST` og `DEFAULT_DENYLIST` fjernes fra `layer1_rules.py`. Eira afgør ikke, hvilke medier man kan stole på. Mediekataloget (N10) er noget andet end en liste i koden: optagelsen sker efter offentlige kriterier, afgøres af et eksternt nævn og kan påklages.

### N3 — Artiklens håndværk som kriterieliste

Artiklen gennemgås efter et offentligt, versioneret kriteriesæt med udgangspunkt i de presseetiske regler, fx:

- Er kilderne navngivet?
- Er den omtalte part forelagt kritikken og hørt?
- Er fakta og kommentar adskilt?
- Henvises der til undersøgelser, data eller dokumenter?
- Er sproget ladet (superlativer, hast, "del før det slettes")?

Hvert fund vises **med sted i teksten**. Et mønster er et tegn, ikke en konklusion: citater, satire og debatindlæg skal kunne genkendes og markeres som sådan. Kriteriesættets version vises sammen med vurderingen.

### N4 — Ingen sandhedsværdi for en artikel (ejerens retning)

EiraOS sætter aldrig en sandhedsværdi på en artikel eller en historie. Begrundelse:

- En maskine kan ikke afgøre, om en nyhed er sand, og en fejl med sandhedens stempel er værre end ingen vurdering.
- At stemple en navngiven journalists artikel som falsk kan være ærekrænkende.
- EiraOS udleveres af offentlige myndigheder. Et styresystem fra en myndighed, der sætter sandhedsværdi på nyheder, kommer tæt på det, censurforbuddet er rettet mod. Det skal juridisk vurderes, før nogen funktion i den retning overvejes.

**Sandhed efterprøves kun pr. påstand og kun mod en primærkilde.** En konkret påstand (et tal, en lov, en dom) kan holdes op mod den officielle kilde, fx Danmarks Statistik, Retsinformation eller domstolens afgørelse. Resultatet viser påstanden, kilden, kildens dato og linket:

> *"Påstanden om ledigheden stemmer ikke med Danmarks Statistik (oktober 2026). [link]"*

Alt andet står som **ikke efterprøvet**. Det er ikke det samme som forkert, og brugerfladen skal sige det.

### N5 — Ingen samlet score for nyheder

Nyhedsvisningen bruger ikke `trust_score` og viser intet tal, ingen procent og ingen farve for hele artiklen. Den viser N2, N3 og N4 som det, de er: hvad der er tjekket, hvad der blev fundet, og hvad der ikke kunne vurderes.

EDP's `veritas`-felt for handlinger er uændret. F1c.7 (fund G-12) løses i samme ånd: en manglende vurdering er *ikke vurderet*, ikke 0 (arkitekturen §9).

### N6 — Strengt som standard, men personens eget valg (ejerens retning)

- Som standard er indhold uden verificeret afsender tydeligt markeret og står efter det verificerede. Det skjules ikke.
- Kun personen selv kan stramme eller løsne visningen, herunder skjule indhold uden verificeret afsender.
- **Fleet kan ikke tvinge filtrering af nyheder** og kan ikke skjule kilder eller artikler for brugeren. Rettighedssættet (ADR-0003) giver ingen sådan rettighed. En arbejdsgiver eller myndighed, der bestemmer, hvilke nyheder en person kan se, er censur, uanset kriterierne.
- Personens valg bor i personens kontekst, ikke i Fleet.

### N7 — AI hjælper, vurderer ikke

Modellen må opsummere en artikel, finde påstande, der kan efterprøves (N4), og forklare kriteriefund med almindelige ord. Den må ikke afgive vurderingen, ændre fund eller fortolke en kildes troværdighed (#165 §6).

Opslag i primærkilder kræver net. De sker i `veritasd` eller en adapter, aldrig i modelprocessen, som kører uden net (AI-INTERFACE).

Lag 3 (mønstre over tid) må kun vise, at et emne eller en påstand optræder hos flere afsendere over tid. Det må ikke kortlægge "narrativer" som en vurdering af afsendernes hensigter.

### N8 — Andre dækninger kun fra personens egne kilder

"Se hvordan andre dækker historien" viser kun artikler fra de kilder, personen selv har valgt (N1). Eira vælger ikke alternative kilder.

### N9 — Sproget i brugerfladen

Vurderingen skrives, så alle kan forstå den, og den peger på en handling:

> *"Historien bygger på en anonym kilde, og den omtalte part er ikke hørt. Afsenderen er ikke verificeret. Du kan læse den med forbehold eller se, hvordan dine andre kilder dækker samme emne."*

Ingen fagudtryk i fladen. Detaljerne (hvilke kriterier, hvilke fund, hvor i teksten, hvilken kriterieversion) ligger ét klik væk.

### N10 — Mediekataloget: medierne tilmelder sig (ejerens retning)

Troværdige medier tilmelder sig et katalog og kan derefter levere signerede overskrifter og korte nyheder til EiraOS.

**Optagelse ved et eksternt nævn.** Det er ikke Eira, der afgør, hvem der optages. Det gør et eksternt nævn. Hvilket nævn er ikke afgjort; Pressenævnet er ejerens første bud (O-5). Nævnet er ikke kontaktet, og intet i denne ADR forudsætter, at det siger ja.

**Kriterierne er objektive og offentlige.** De handler om ansvar, ikke om kvalitet eller holdning. Forslag:

- mediet er anmeldt efter medieansvarsloven og underlagt Pressenævnet
- der er en navngiven ansvarshavende redaktør
- mediet signerer det, det leverer til kataloget
- mediet har en offentlig rettelsespraksis
- mediet er selv udgiver af det, det leverer: kun indhold, mediet selv har produceret og har det redaktionelle ansvar for. Aggregatorer, der samler andres indhold (fx MSN, Google News), kan ikke optages (ejerens beslutning, 25. november 2026)

Et medie, der opfylder kriterierne, optages, uanset størrelse eller holdning. Et afslag eller en udelukkelse begrundes og kan påklages efter nævnets regler.

**Gratis, altid.** Det koster aldrig penge at blive optaget eller at være med, og troværdighed kan ikke købes. Eira tager heller ikke betaling for tillægsydelser til medierne, der hviler på kataloget.

**Eira driver kun det tekniske register.** Det rummer de optagne medier, deres offentlige nøgler, deres feed-adresser og nævnets afgørelser med dato. Eira ændrer ikke nævnets afgørelser.

**Eira kan ikke se, hvem der læser hvad.**

- Medierne udgiver selv deres signerede feeds; indholdet går ikke gennem Eira.
- EiraOS på personens egen enhed henter direkte fra mediet og tjekker signaturen mod registeret.
- Registeret hentes som helhed, ikke slået op pr. artikel, så opslag ikke afslører læsning.
- Ingen klikstatistik, ingen måling af læsning og ingen data om læsere til medierne fra Eira. Hvad mediet selv ser, når personen følger linket til mediets side, er mellem personen og mediet.

**Ingen rangering.** Katalogets medier vises alfabetisk eller efter personens eget valg. Kataloget fremhæver ingen.

## Konsekvenser

- `veritasd` får en ny evaluering for nyhedsartikler, der returnerer N2–N4 som strukturerede fund i stedet for en score. Den eksisterende evaluering for handlinger (EDP) bevares.
- `layer1_rules.py` mister sine domænelister og flytter sine mønstre ind i et versioneret kriteriesæt (N3).
- Veritas HUD'en ændres fra score til kriterieliste (N5, N9).
- `veritas-shield/` fjernes eller arkiveres i F1c.5 som planlagt; denne ADR overtager dens formål.
- En RSS/Atom-adapter kræver Input-kontrakten fra ADR-0006 og kommer først efter den.
- Mediekataloget (N10) er en ny tjeneste: et register med offentlige nøgler og afgørelser, et format for signerede feeds og et værktøj, medierne kan signere med. Registeret er offentligt og kan spejles.
- Kataloget løser, at næsten alt ellers ville stå som "ikke verificeret afsender", fordi få medier signerer i dag. Det gør det kun for de medier, der tilmelder sig. Selvvalgte kilder uden for kataloget forbliver markeret (N6).
- Kataloget kræver et nævn, der vil påtage sig opgaven, og en aftale om, hvordan afgørelser når registeret. Uden et nævn bygges kataloget ikke; N1–N9 gælder uanset.

## Afvist

| Afvist | Begrundelse |
|---|---|
| Sandhedsscore eller sandt/falsk for en artikel | N4 |
| Samlet troværdighedstal, procent eller farvekode | N5; arkitekturen §9 |
| Lister over godkendte eller afviste medier i koden | N2; Eira bliver redaktør |
| AI-detektion af maskinskrevet tekst som grundlag for afsendervurdering | N2; for upålidelig |
| Filtrering af nyheder styret af Fleet eller arbejdsgiver | N6; censur |
| Eira afgør selv optagelsen i mediekataloget | N10; Eira bliver redaktør |
| Aggregatorer i mediekataloget | N10; kun den oprindelige udgiver kan stå ved og signere indholdet |
| Betaling for optagelse, synlighed eller tillægsydelser | N10; troværdighed kan ikke købes |
| Nyheder hentet gennem en central Eira-server eller klikstatistik | N10; Eira må ikke kunne se læsning |
| En central nyhedsfeed eller anbefalingsalgoritme | N1; #165 §8 |

## Åbne spørgsmål

| # | Spørgsmål | Blokerer |
|---|---|---|
| O-1 | Hvilke primærkilder kommer først (Danmarks Statistik, Retsinformation, domstolene, EU-kilder), og hvordan håndteres en kilde, der er nede eller ændret? | N4 |
| O-2 | ~~Hvordan verificeres "ansvarligt medie" maskinelt?~~ Besvaret af N10: medierne tilmelder sig, og nævnets afgørelse står i registeret | — |
| O-3 | Hvem ejer kriteriesættet i N3: Eira, eller en ekstern, åben proces (fx med journalistuddannelser eller medieforskere)? | N3 |
| O-4 | Juridisk vurdering af N4, N6 og N10 i forhold til ærekrænkelse og censurforbuddet, før funktionen tilbydes offentlige kunder | Udgivelse |
| O-5 | Hvilket eksternt nævn? Pressenævnet er ejerens første bud. Har det hjemmel og vilje til opgaven, eller kræver det en anden instans (fx et uafhængigt nævn nedsat sammen med branchen)? | N10 |
| O-6 | Hvem betaler for drift af registeret og nævnets sagsbehandling, når medierne ikke betaler? Fx Eira, offentlig støtte eller EU-midler | N10 |

## Kilder

- DR: [Forskere: Shopping og svindel definerer i højere grad dine 'sociale medier'](https://www.dr.dk/nyheder/indland/forskere-shopping-og-svindel-definerer-i-hoejere-grad-dine-sociale-medier) (25. november 2026), om rapporten *Sociale platformes økonomiske magt* fra Magtudredningen 2.0
- Ejerens notat om troværdighedsvurdering (ikke lagt i repoet)
