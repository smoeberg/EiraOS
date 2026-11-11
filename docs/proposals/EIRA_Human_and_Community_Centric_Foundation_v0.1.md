# EIRA — menneske- og fællesskabscentreret fundament

**Status:** Forslag til grundlæggende platformprincip — afventer ejerens godkendelse  
**Type:** Strategisk produkt- og arkitekturprincip  
**Scope:** Hele EIRA-platformen; ikke en selvstændig app eller et nyt vertikalt fagsystem
**Afstemt med:** [ADR-0005](../decisions/ADR-0005-kontekster-og-datas-hjem.md) (kontekster), [ADR-0006](../decisions/ADR-0006-livets-indbakke.md) (livets indbakke, glimt), [EIRA-CONTEXT 1.0](../../specs/EIRA-CONTEXT-1.0.md). Hvor dette forslag og de dokumenter er uenige, gælder de (rev. 11. november 2026).

---

## 1. Formål

EIRA skal ikke alene gøre eksisterende enterprise-arbejdsgange mere intelligente. EIRA skal også give mennesker en sammenhængende digital infrastruktur til at organisere deres relationer, fællesskaber, aktiviteter, viden og samarbejde.

Teknologien skal tage udgangspunkt i menneskers virkelige relationer og fælles behov — ikke i softwareleverandørernes produktkategorier.

> **Teknologi skal ikke organisere mennesker i leverandørernes systemer. Teknologi skal hjælpe mennesker med at organisere sig selv, deres relationer og deres fællesskaber.**

Dette princip supplerer EIRAs eksisterende position som en platform oven på Ubuntu. Det ændrer ikke ved, at Ubuntu leverer operativsystem, kernel og moden Linux-infrastruktur.

## 2. Én fælles platform — ikke separate vertikale systemer

EIRA skal have én sammenhængende fælles model for mennesker, relationer, fællesskaber, aktiviteter og samarbejde.

Skole, idrætsforening, musikskole, spejdergruppe, arbejdsplads og lokalsamfund er forskellige kontekster — ikke hver deres isolerede produkt eller datasilo.

De skal bruge de samme grundlæggende platformsevner og objekttyper. Forskellene udtrykkes gennem konfiguration, roller, politikker, workflows og domænespecifikke udvidelser.

Eksempler på eksisterende produkter som Holdsport, SkoleIntra og Aula repræsenterer behov, EIRA skal kunne dække. De er ikke arkitekturmodeller, der skal kopieres.

### 2.1 Fælles grundmodel

| Fælles begreb | Hvad det skal kunne repræsentere |
|---|---|
| Person | Mennesker, herunder børn og voksne |
| Relation | Familie, værge, kontakt, samarbejde og tilknytning |
| Fællesskab | Skole, klasse, hold, klub, forening, gruppe eller lokalt netværk |
| Medlemskab | En persons tilknytning til et fællesskab med gyldighed og status |
| Rolle og mandat | Hvad en person må gøre i en bestemt kontekst |
| Aktivitet | Træning, undervisning, møde, kamp, arrangement eller arbejdsopgave |
| Kalender og deltagelse | Tid, sted, invitation, tilmelding, fremmøde og afbud |
| Kommunikation | Beskeder, dialoger, opslag og målrettede meddelelser |
| Viden og dokument | Fælles information, materialer, beslutningsgrundlag og historik |
| Opgave og ansvar | Hvem gør hvad, hvornår og med hvilket resultat |
| Beslutning | Forslag, dialog, afstemning, mandat, beslutning og opfølgning |
| Ressource | Lokaler, udstyr, faciliteter og andre fælles ressourcer |
| Økonomisk hændelse | Kontingent, betaling, tilskud, udgift og økonomisk status |

Modellen skal være generel. Den må ikke hardcodes til en bestemt organisationsform.

**Én grundmodel betyder ikke én database.** Alle fællesskaber bruger de samme objekttyper, men hvert fællesskab er en kontekst (ADR-0005) med sine egne data, sit eget hjem og sine egne regler. Det, der er fælles, er modellen og kontrakterne, ikke data.

### 2.2 Konfiguration frem for nye systemer

En fodboldklub skal kunne konfigurere hold, trænere, kampe, træning, kontingent og forældrekommunikation.

En skole skal kunne konfigurere klasser, lærere, elever, forældre/værger, undervisningsaktiviteter, beskeder og skole-hjem-samarbejde.

Begge bruger de samme platformsevner: Person, Relation, Fællesskab, Medlemskab, Rolle, Aktivitet, Kalender, Kommunikation, Dokument, Opgave og Beslutning.

Det er konfiguration og kontekst, der gør oplevelsen relevant — ikke separate systemer med hver deres identiteter, kalendere, beskeder og datamodeller.

## 3. Tre grundprincipper

### 3.1 Mennesket i centrum

- Mennesket er mere end en konto, brugerrolle eller datapost.
- En person kan deltage i flere fællesskaber og have forskellige roller i hver kontekst.
- Brugeren skal kunne forstå, kontrollere og påvirke egne relationer og data.
- Platformen skal være tilgængelig, inkluderende og anvendelig på tværs af alder, evner og teknisk erfaring.

### 3.2 Fællesskabet i centrum

- Fællesskaber skal kunne opstå, organisere sig, kommunikere og udvikle sig uden at være låst til en leverandørs organisationsmodel.
- Deltagelse skal kunne føre til konkret handling: initiativ → information → dialog → forslag → beslutning → opgave → resultat.
- Fællesskaber bestemmer selv deres legitime struktur, regler og arbejdsformer inden for gældende lovgivning og platformens sikkerhedsrammer.
- Teknologien skal understøtte frivillighed, lokalt engagement, samarbejde og demokratisk deltagelse.

### 3.3 Lokal suverænitet

- Data skal så vidt muligt behandles og opbevares lokalt eller under den relevante organisations kontrol.
- Fællesskaber skal kunne vælge egen drift, hosting og deling inden for fælles åbne standarder.
- Offline-tolerance, eksport, portabilitet og mulighed for at forlade platformen er grundkrav.
- Samarbejde på tværs skal være muligt uden at kræve én central global database eller ét centralt socialt netværk.

**Local-first** er det tekniske princip om data- og behandlingskontrol.  
**Community-first** er det menneskelige og samfundsmæssige princip om deltagelse og fælles handlekraft.  
De hænger sammen, men er ikke det samme.

## 4. Én sammenhængende brugeroplevelse

En familie skal kunne bruge EIRA som én samlet indgang til sine fællesskaber.

Eksempel: Et barn går i skole, spiller fodbold og går på musikskole. Familien skal ikke vedligeholde tre separate identiteter, tre uafhængige kontaktlister og tre kalendere for at få hverdagen til at hænge sammen.

EIRA skal give familien ét overblik over hverdagen på tværs af fællesskaberne, uden at indhold krydser grænserne (ADR-0006 L5):

- **Kalender-glimt:** et fællesskab kan tillade, at dets aktiviteter vises på tværs med **tidspunkt og sted**, fx *"torsdag 17–18, Havnsø Stadion"*. Ingen titel, beskrivelse, deltagere eller beskeder.
- **Aktivitets-glimt:** at der er nyt i et fællesskab (antal og tidspunkt), aldrig hvad.
- **Indhold** (beskeder, opgaver, dokumenter) læses kun i fællesskabets egen kontekst. Et klik på et glimt tilbyder at skifte dertil.
- **Arbejdskontekster** viser som standard kun aktivitets-glimt.
- **Familien er selv et fællesskab** med fælles kalender og begivenheder. En begivenhed kan oprettes i familiekalenderen ud fra et kalender-glimt ("overfør glimt": kun tid og sted, titlen skriver man selv). Se ADR-0005 K12.
- **Forældrestyring** af barnets egen brug sker med værgesignerede regler og faste alderstrin (under 13, 13–17, ophører ved 18). Værgen ser regler og brugsoverblik, aldrig indhold (ADR-0005 K12).

En lærer må ikke automatisk få adgang til klubbens oplysninger. En træner må ikke automatisk få adgang til skolens oplysninger. En forælder/værge får kun adgang i kraft af en verificeret relation og de rettigheder, der gælder i den konkrete kontekst.

**Forældre og værger** får en **egen rolle i fællesskabets kontekst** (fx "forælder til Anna" i skolens kontekst) med deres egen identitet. De får ikke adgang til barnets kontekst. Fællesskabet styrer rollen og dens gyldighed; barnets data forbliver barnets. Verifikation af værgerelationen og aldersregler skal specificeres, før funktioner med børns persondata implementeres (§9 pkt. 4).

**Fælles platform betyder ikke fælles adgang til alle data.** Sammenhæng i oplevelsen skal kombineres med streng kontekstuel adgangskontrol og dataminimering.

## 5. Arkitektoniske konsekvenser

Dette princip skal realiseres gennem EIRAs eksisterende arkitektur — ikke ved at indføre en parallel platform ved siden af den.

| EIRA-komponent | Betydning for fællesskabsfundamentet |
|---|---|
| Identity | Personer, autentifikation, værgerelationer, delegation og identitetsbeviser |
| Object Graph | Fælles objekter og relationer mellem personer, fællesskaber, aktiviteter og ressourcer |
| Temporal Graph | Historik for medlemskaber, roller, relationer og gyldighed |
| Capability Layer | Ensartede funktioner, som kan bruges på tværs af kontekster |
| Intent Engine | Brugerens hensigt omsættes til forståelige forslag og handlinger |
| Journey Orchestrator | Forløb som tilmelding, aktivitet, dialog, beslutning og opfølgning |
| Trust & Evidence | Proveniens og dokumentation for relationer, information og beslutningsgrundlag |
| Governance / Gate | Kontekstuel adgang, samtykke, mandat, godkendelse og audit |
| Local-first Storage | Lokal tilgængelighed, synkronisering og datakontrol |
| Event Bus | Hændelser og ændringer mellem løst koblede komponenter |
| RPC | Eksplicitte kommandoer og handlinger; hændelser og kommandoer holdes adskilt |

Platformen skal være modulær og kunne udvides, men fælles identiteter, objekter og kontrakter skal forhindre, at moduler udvikler sig til uafhængige siloer.

Fællesskabsfunktioner skal ikke placeres i Linux-kernen eller blandes sammen med OS'ets lavniveauansvar. De er en del af EIRA-platformens bruger- og samarbejdsfunktionalitet og skal bruge de eksisterende sikkerheds- og runtime-kontrakter.

## 6. Privatliv, børn og tillid er fundament — ikke eftertanke

Når EIRA bruges af skoler, familier, foreninger og børn, er kravene til privatliv og sikkerhed særligt vigtige.

- Adgang er altid kontekstuel og mindst mulig.
- Relationer som forælder/værge skal være verificerbare og have gyldighed.
- Samtykke skal være formålsbestemt, forståeligt, dokumenterbart og kunne trækkes tilbage, hvor lovgivningen giver ret til det.
- Følsomme oplysninger må ikke blive synlige på tværs af fællesskaber alene fordi personer deler en platform.
- Børns data skal have særlig beskyttelse og passende værge- og aldersregler.
- Moderation, rapportering, blokering og håndtering af misbrug skal være indbyggede platformsevner.
- AI må hjælpe med oversættelse, tilgængelighed, opsummering og strukturering, men må ikke foregive at repræsentere fællesskabets vilje eller træffe bindende fælles beslutninger på dets vegne.
- Ingen reklamebaseret profilering, manipulerende engagement-optimering eller popularitetsbaserede ranglister.

## 7. ISOOKO som inspirationskilde

ISOOKO er relevant som inspiration til den menneskelige og samfundsmæssige dimension: informationsdeling, struktureret dialog, lokal deltagelse, medskabelse og fællesskabsbaseret handling.

ISOOKO var et EU-finansieret forsknings- og innovationsprojekt (Horizon 2020, grant agreement 779793), koordineret af King's College London. Projektet byggede videre på Ushahidi og arbejdede med deltagelsesbaserede løsninger, blandt andet afprøvet i Rwanda og Kenya.

EIRA skal lære af principperne og projektets dokumentation — ikke ukritisk kopiere ISOOKO eller gøre Ushahidi til en obligatorisk teknisk afhængighed. Eventuel genbrug af kode eller komponenter kræver særskilt vurdering af licens, sikkerhed, vedligeholdelse, databeskyttelse og teknisk egnethed.

ISOOKO er en inspirationskilde; EIRAs fælles platformmodel skal udvikles ud fra EIRAs egne arkitekturprincipper.

## 8. Designregler og anti-patterns

| Må ikke ske | Det ønskede princip |
|---|---|
| Et separat Eira-system til skole, sport og forening | Én fælles platform og grundmodel |
| Separate identiteter og kontaktregistre for hvert fællesskab | Sammenhængende identitet med kontekstuelle medlemskaber og rettigheder |
| En global fælles adgang til alle data | Strenge grænser mellem fællesskaber og formål |
| En central social feed-algoritme, der bestemmer synlighed | Gennemsigtig, bruger- og fællesskabsstyret information |
| AI træffer fællesskabets beslutninger | AI assisterer; mennesker og legitime organer beslutter |
| Leverandørlåsning og proprietære dataformater | Åbne standarder, eksport og portabilitet |
| Et nyt monolitisk subsystem ved siden af EIRA | Udvidelse af eksisterende EIRA-primitiver og kontrakter |

## 9. Foreslået rækkefølge for videre arbejde

Dette dokument fastlægger retningen, ikke en færdig implementering.

1. Godkend det menneske- og fællesskabscentrerede princip som supplement til EIRA Platform Principles.
2. Kortlæg eksisterende objekter og relationer i Object Graph mod den fælles grundmodel.
3. Identificér manglende fælles primitiver — især Community, Membership, Activity, Participation, Consent og Decision.
4. Definér kontekstuel autorisation og værge-/børnerelationer før funktioner med persondata implementeres.
5. Udarbejd ét end-to-end referenceforløb, der kan konfigureres til både skole og idrætsforening uden separate datamodeller.
6. Implementér først efter arkitekturreview og målbare acceptkriterier.

## 10. Foreslået grundsætning

> **EIRA er en menneske- og fællesskabscentreret platform. Den giver mennesker mulighed for at organisere deres relationer, fællesskaber, viden og fælles handling gennem én sammenhængende, lokal-first og åben digital infrastruktur.**

---

## Kilder og videre læsning

- ISOOKO på CORDIS: https://cordis.europa.eu/project/id/779793
- Ushahidi: https://www.ushahidi.com/
- EIRA Platform Principles: `docs/archive/specs-v0/EIRA_Platform_Principles_v1.0.md`
- EIRA Cognitive Runtime: `docs/archive/specs-v0/EIRA_Cognitive_Runtime_v1.0.md`
- EIRA Object Graph Specification: `docs/archive/specs-v0/EIRA_Object_Graph_Specification_v0.3.md` (findes i tre versioner, v0.1–v0.3; skal afklares ved oprydningen af `docs/specs/`)
- ADR-0005, ADR-0006 og EIRA-CONTEXT 1.0 (se øverst)
