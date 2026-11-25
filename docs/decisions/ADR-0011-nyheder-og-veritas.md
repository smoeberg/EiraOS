# ADR-0011 — Nyheder i livets indbakke: afsender, håndværk og efterprøvede påstande

**Status:** Foreslået, til ejerens accept (25. november 2026). N1, N2, N4 og N6 er ejerens retning; resten er et forslag.
**Gælder for:** `veritasd` og `app/veritas/`, Veritas HUD (`ui/src/components/VeritasHUD.tsx`), livets indbakke og dens adaptere (ADR-0006), kontekster (ADR-0005), Fleet-rettigheder (ADR-0003)
**Relateret:** [ADR-0003](ADR-0003-rettigheder-fra-fleet.md), [ADR-0005](ADR-0005-kontekster-og-datas-hjem.md), [ADR-0006](ADR-0006-livets-indbakke.md), [EDP 1.0](../../specs/EDP-1.0.md), [AI-INTERFACE 1.0](../../specs/AI-INTERFACE-1.0.md), [fællesskabsfundamentet](../proposals/EIRA_Human_and_Community_Centric_Foundation_v0.1.md) (#165), [arkitekturen §9](../architecture/eiraos-system-architecture.md), fundregistret G-8 og G-12

## Normativ regel

> **EiraOS viser, hvem der står bag en nyhed, og hvordan den er lavet. EiraOS afgør aldrig, om en nyhed er sand. Kun en konkret påstand kan efterprøves, og kun mod en primærkilde, der vises. Hvad personen vil se, er personens eget valg.**

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

Nyheder kommer ind gennem en adapter efter ADR-0006 L1–L2 (først RSS/Atom) og lander i livets indbakke i personens egen kontekst. Personen vælger selv sine kilder.

- Ingen central nyhedsstrøm, ingen rangering efter engagement, ingen anbefalinger fra Eira (#165 §6 og §8).
- Rækkefølgen er tid eller personens egen sortering.
- Nyheder er indhold i en kontekst og krydser ikke kontekstgrænser (ADR-0006 L5).

### N2 — Afsenderen vurderes på bevist oprindelse (ejerens retning)

Afsenderen skal vurderes, og kravet er, at indholdet er skabt af et menneske, der står ved det. Det afgøres ud fra **oprindelse, der kan bevises**, ikke ud fra analyse af teksten:

| Tegn | Hvad det viser | Kilde i EiraOS |
|---|---|---|
| Signatur på artiklen | Et navngivet menneske eller medie står ved netop denne tekst | Lag 2 (QEAA/EUDI) |
| Content credentials på billeder og video | Hvor billedet kommer fra, og om det er redigeret eller genereret | C2PA |
| Ansvarligt medie | Afsenderen kan holdes ansvarlig efter dansk ret (fx medieansvarsloven) | Opslag, se O-2 |

Resultatet er en status med begrundelse: *verificeret afsender* (med hvad der er verificeret) eller *ikke verificeret afsender*. Det er aldrig "upålidelig".

- **AI-detektion er ikke et grundlag.** Værktøjer, der gætter på, om en tekst er maskinskrevet, rammer forkert på mennesker og kan omgås. De må ikke indgå i afsendervurderingen.
- **Ingen lister over godkendte medier i koden.** `DEFAULT_ALLOWLIST` og `DEFAULT_DENYLIST` fjernes fra `layer1_rules.py`. Eira afgør ikke, hvilke medier man kan stole på; det afgør beviserne.

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

## Konsekvenser

- `veritasd` får en ny evaluering for nyhedsartikler, der returnerer N2–N4 som strukturerede fund i stedet for en score. Den eksisterende evaluering for handlinger (EDP) bevares.
- `layer1_rules.py` mister sine domænelister og flytter sine mønstre ind i et versioneret kriteriesæt (N3).
- Veritas HUD'en ændres fra score til kriterieliste (N5, N9).
- `veritas-shield/` fjernes eller arkiveres i F1c.5 som planlagt; denne ADR overtager dens formål.
- En RSS/Atom-adapter kræver Input-kontrakten fra ADR-0006 og kommer først efter den.
- **I begyndelsen vil næsten alt være "ikke verificeret afsender".** Få medier signerer deres artikler i dag. Det er et korrekt billede af virkeligheden og en grund til, at N6 markerer frem for at skjule.

## Afvist

| Afvist | Begrundelse |
|---|---|
| Sandhedsscore eller sandt/falsk for en artikel | N4 |
| Samlet troværdighedstal, procent eller farvekode | N5; arkitekturen §9 |
| Lister over godkendte eller afviste medier i koden | N2; Eira bliver redaktør |
| AI-detektion af maskinskrevet tekst som grundlag for afsendervurdering | N2; for upålidelig |
| Filtrering af nyheder styret af Fleet eller arbejdsgiver | N6; censur |
| En central nyhedsfeed eller anbefalingsalgoritme | N1; #165 §8 |

## Åbne spørgsmål

| # | Spørgsmål | Blokerer |
|---|---|---|
| O-1 | Hvilke primærkilder kommer først (Danmarks Statistik, Retsinformation, domstolene, EU-kilder), og hvordan håndteres en kilde, der er nede eller ændret? | N4 |
| O-2 | Hvordan verificeres "ansvarligt medie" maskinelt? Findes der et register (fx hos Pressenævnet), der kan slås op, og hvem vedligeholder opslaget? | N2, tredje række |
| O-3 | Hvem ejer kriteriesættet i N3: Eira, eller en ekstern, åben proces (fx med journalistuddannelser eller medieforskere)? | N3 |
| O-4 | Juridisk vurdering af N4 og N6 i forhold til ærekrænkelse og censurforbuddet, før funktionen tilbydes offentlige kunder | Udgivelse |

## Kilder

- DR: [Forskere: Shopping og svindel definerer i højere grad dine 'sociale medier'](https://www.dr.dk/nyheder/indland/forskere-shopping-og-svindel-definerer-i-hoejere-grad-dine-sociale-medier) (25. november 2026), om rapporten *Sociale platformes økonomiske magt* fra Magtudredningen 2.0
- Ejerens notat om troværdighedsvurdering (ikke lagt i repoet)
