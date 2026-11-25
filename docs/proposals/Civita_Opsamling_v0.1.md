# Civita: hvad EiraOS overtager, og hvad der afvises

**Status:** Forslag — afventer ejerens godkendelse
**Dato:** 25. november 2026
**Type:** Opsamling af et stoppet koncept; supplement til fællesskabsfundamentet
**Afstemt med:** [EIRA — menneske- og fællesskabscentreret fundament](EIRA_Human_and_Community_Centric_Foundation_v0.1.md) (#165), [ADR-0005](../decisions/ADR-0005-kontekster-og-datas-hjem.md) (kontekster og datas hjem), [ADR-0006](../decisions/ADR-0006-livets-indbakke.md) (livets indbakke, glimt), [EIRA-CONTEXT 1.0](../../specs/EIRA-CONTEXT-1.0.md). Hvor dette dokument og de dokumenter er uenige, gælder de.

---

## 1. Baggrund

Civita var ejerens koncept fra juni 2025 for "fremtidens sociale medie": et europæisk socialt netværk, hvor brugeren ejer sine data. Materialet (otte konceptdokumenter og en række mockups) voksede til fire produkter på én gang:

1. et socialt netværk som alternativ til Facebook (profil, opslag, feed, Facebook-import)
2. en dataøkonomi (Data Wallet, opt-in reklamer med indtægtsdeling, dataauktion)
3. en søgemaskine (Civita Search: SearxNG, YaCy, OpenSearch)
4. et forenings- og fællesskabsmodul (stiftelse, bestyrelse, medlemmer, generalforsamling, dokumenter, kontingent)

Konceptet gik i stå. Det blev gennemgået 25. november 2026 med to spørgsmål: Har det gang på jord, og skal det være en del af EiraOS?

Kildematerialet lægges ikke i repoet. Kun dette dokument gælder.

## 2. Ejerens beslutning

> **Det offentlige torv opgives. Det handler om mennesket og dets relationer.** (ejeren, 25. november 2026)

Civita videreføres ikke som selvstændigt socialt netværk, app eller platform. Navnet lever videre som navnet på fællesskabslaget i EiraOS (CO-1). Det, der kan bruges, går ind i EiraOS' fællesskabslag gennem de eksisterende primitiver: kontekst, fællesskab, medlemskab, rolle, aktivitet, beslutning og økonomisk hændelse.

## 3. Begrundelse

Civita forsøgte at bygge et bedre Facebook. Vurderingen er, at netop den kategori er ved at forsvinde:

- **Det sociale har splittet sig.** Den offentlige feed er blevet til underholdning og nyheder fra fremmede. Det nære sociale liv er flyttet ind i små grupper og gruppechats.
- **Gruppechatten er en dårlig infrastruktur.** Den har ingen hukommelse, ingen roller, ingen kalender, intet arkiv og ingen grænse mellem arbejde og fritid. Det hul er det, EiraOS kan fylde.
- **AI-genereret indhold gør den offentlige feed værdiløs.** Værdien flytter til *verificerede mennesker, man kender*, inden for fællesskaber med en grænse.
- **Grænsefladen bliver en agent, ikke en feed.** En agent, der samler indgangene, er præcis "livets indbakke" (ADR-0006). Opmærksomhedsøkonomien og dermed en reklamemodel passer ikke ind.
- **Selv forskningen kalder dem ikke længere sociale.** Rapporten *Sociale platformes økonomiske magt* (Magtudredningen 2.0, lektorerne Andreas Lindegaard Gregersen og Jacob Ørmen, Københavns Universitet) konkluderer, at betegnelsen "sociale medier" i dag er misvisende. Platformene er styret af fastholdelse og annoncer, og indhold fra ens virkelige venner trænges i baggrunden, fordi det ikke fastholder nok (DR, 25. november 2026).
- **Reklamemodellen gør platformene til markedspladser for handel og svindel.** Ifølge interne Meta-dokumenter, som omtales i samme artikel, anslog Meta selv, at over ti procent af omsætningen kom fra annoncer for svindel og forbudte varer. Meta bestrider, at dokumenterne giver et retvisende billede. Ifølge Forbrugerrådet Tænk kom over halvdelen af den svindel, danskerne mødte i 2025, fra Facebook, og kun hver fjerde anmeldte svindelannonce blev fjernet. En model, hvor platformen tjener på annoncer, har ikke et incitament til at rydde op.
- **Pengene ligger i tilhørsforhold, ikke i opmærksomhed.** Fællesskaber betaler allerede for at fungere (kontingent). Brugerne skal ikke sælges.

Konklusion: Civitas oprindelige ambition (mennesket og dets relationer frem for platformen) er bedre realiseret som et lag i EiraOS end som en app. Lagets form er allerede beskrevet i fællesskabsfundamentet (#165). Civita bidrager med konkret indhold til det.

## 4. Det, EiraOS overtager

Hvert punkt er formuleret som et behov, ikke som en løsning. Implementeringen følger fællesskabsfundamentets §9 og udviklingsplanens rækkefølge.

### C1 — Foreningens livsforløb som konfiguration

Civitas stærkeste del. En forening har et forløb, som en gruppechat ikke kan bære:

| Forløb | Indhold | EiraOS-primitiv |
|---|---|---|
| Stiftelse | Navn, formål, vedtægter (skabelon eller egne), stiftelsesdokument, første bestyrelse | Fællesskab, Dokument, Beslutning |
| Bestyrelse og roller | Formand, kasserer, menige medlemmer, suppleanter, revisor; med gyldighed | Rolle og mandat, Temporal Graph |
| Medlemskab | Indmeldelse (evt. med godkendelse), udmeldelse, medlemsliste | Medlemskab |
| Generalforsamling | Indkaldelse, dagsorden, forslag, afstemning, valg, referat | Aktivitet, Beslutning, Dokument |
| Løbende drift | Bestyrelsesmøder, referater, opslagstavle, arrangementer | Aktivitet, Kommunikation, Dokument |
| Økonomi | Kontingent, budget, udgifter, årsregnskab | Økonomisk hændelse |
| Årsafslutning | Årsberetning, regnskab, bestyrelsesoversigt samlet og klar til eksport | Dokument, Trust & Evidence |

Forløbet leveres som **konfiguration og skabeloner** for fællesskabstypen "forening", ikke som et separat foreningssystem (jf. fundamentets anti-patterns).

**Skal afklares:** hvilke formkrav der faktisk gælder. En frivillig forening har få lovkrav. Foreninger, der modtager kommunalt tilskud efter folkeoplysningsloven, har flere (vedtægter, demokratisk opbygning, regnskab). Skabelonerne må ikke love "automatisk opfyldelse af lovkrav", før det er gennemgået.

### C2 — Afstemning og valg

Generalforsamlingens afstemninger og valg er den mest krævende form for Beslutning. De skal kunne håndtere:

- stemmeret afledt af gyldigt medlemskab på et bestemt tidspunkt (Temporal Graph)
- åben og hemmelig afstemning
- fuldmagt, hvis vedtægterne tillader det
- et resultat med proveniens, der kan dokumenteres bagefter (Trust & Evidence)

AI må hjælpe med dagsorden, opsummering og referatudkast, men aldrig afgive, tælle eller fortolke stemmer (fundamentet §6).

### C3 — Kontingent uden at EiraOS holder penge

Kontingent og arrangementsbetaling går gennem en ekstern, licenseret betalingsudbyder. EiraOS registrerer **økonomiske hændelser** (opkrævet, betalt, refunderet). Det holder aldrig saldi, udbetaler aldrig og har ingen wallet. En betaling, der sættes i gang fra EiraOS, er en handling med konsekvens og går gennem gaten.

Mulig motor til medlemmer og kontingent: Dolibarrs medlemsmodul bag en grænseflade. Det er ikke besluttet.

### C4 — "Siden sidst" i stedet for uendelig feed

Civitas idé om et dashboard i stedet for en evighedsfeed bliver et princip for fællesskabets visning:

- Standardvisningen er **siden sidst**: hvad der er nyt i dette fællesskab, siden personen sidst var her. Den har en ende.
- Ingen feed-algoritme, ingen popularitetsrangering (fundamentet §8).
- **Ro:** et fællesskab kan sættes på pause pr. person. Det giver ingen glimt og ingen notifikationer, kun det, fællesskabet markerer som vigtigt (fx indkaldelse til generalforsamling).

### C5 — Gennemsigtig økonomi som valg for fællesskabet

Et fællesskab kan vælge, at medlemmer kan se budget og regnskab i fællesskabets kontekst. Det er en politik pr. fællesskab, ikke en standard.

### C6 — Arrangementer med sted

Aktiviteter med et fysisk sted, tilmelding og kortvisning. Det passer med kalender-glimt (tid og sted, ADR-0006) og med Ushahidi-inspirationen om steder på et kort.

### C7 — Kommunen som kanal (hypotese)

Kommuner har allerede en relation til foreningerne gennem tilskud og dokumentation. Det er de samme kunder som ECK. Hypotesen er, at et foreningslag kan være en konkret demonstration af EiraOS-kontekster over for en kommune, og at en eksport af medlems- og aktivitetstal i kommunens format kan være en indgang.

**Parkeret** (CO-3). Den er ikke valideret og afprøves ikke sammen med ECK. Der bygges intet til den.

### C8 — Eget arkiv med fra andre tjenester (lav prioritet)

En person kan importere sit *eget* arkiv fra en anden tjeneste (fx den dataeksport, Facebook selv udleverer) som filer i sin egen kontekst. Ingen venneliste, ingen invitationer, ingen opslag på andre tjenester. Det er exit-garantien set fra den anden side: dine data kan også komme ind.

## 5. Det, der afvises

Disse dele af Civita må ikke genindføres i EiraOS. Listen står her, så de ikke dukker op igen under et andet navn.

| Afvist | Begrundelse |
|---|---|
| **Data Wallet**, indtjening og udbetaling til brugere | At holde saldi og udbetale kræver betalings- eller e-pengetilladelse og identitetskontrol, og det tiltrækker svindel. Det strider mod ID-hjemmets krav om ingen følsomme data (ADR-0005) |
| **Dataauktion** og salg af datakategorier | Strider mod fundamentets "ingen reklamebaseret profilering". Civitas mockup tilbød salg af politisk tilhørsforhold, som er en særlig kategori efter GDPR art. 9 |
| **Opt-in reklamer**, også med indtægtsdeling til fællesskaber | Opmærksomhedsøkonomi. Den ødelægger tilliden hos det offentlige som kunde og passer ikke med en agent-baseret grænseflade |
| **Facebook-import af venner**, scraping og automatiske opslag ("følg mig på Civita") | Strider mod tjenesternes vilkår og mod ejerens retning om ikke at kigge bagud ("lad dem dø", ADR-0006). Se C8 for det, der er tilladt |
| **Civita Search** (SearxNG, YaCy, OpenSearch-integration) | Et eget søgeindeks er et selvstændigt produkt, og metasøgning lever af andres resultater |
| **Blockchain**, smart contracts, Polygon | Løser intet problem, EiraOS har. CRDT og kontekst-hjem (ADR-0009, EIRA-CONTEXT) dækker synkronisering og proveniens |
| **Realtidsauktion** (Prebid.js o.l.) | Følger af afvisningen af reklamer |
| **Et globalt offentligt torv**, én fælles feed og én fælles social graf | Ejerens beslutning (§2). Strider også mod skarpe grænser mellem kontekster (ADR-0005, ADR-0006 L5) |
| **"Luminous Glassmorphism"**-designspecifikationen og stemmepanelet "Hey Nova" | Ikke forankret i EiraOS' GUI-arkitektur (ADR-0004) og i strid med Civitas egne mockups. UI følger EiraOS' egne designdokumenter |
| **Civita som separat app** og egen platform (navnet bruges om fællesskabslaget, CO-1) | Fundamentets anti-pattern: et separat subsystem ved siden af EiraOS |

## 6. Ejerens svar (25. november 2026)

| # | Spørgsmål | Svar |
|---|---|---|
| CO-1 | Skal navnet "Civita" (af latin *civitas*, borgerfællesskab) leve videre som navnet på fællesskabslaget i EiraOS? | **Ja.** Fællesskabslaget i EiraOS hedder Civita. Det er et navn på et lag, ikke en separat app eller platform (§5) |
| CO-2 | Skal C1 (foreningens livsforløb) være det end-to-end referenceforløb, fundamentet §9 pkt. 5 kræver? | **Nej.** Referenceforløbet forbliver skole og idrætsforening som i #165. C1 er indhold, der skal kunne konfigureres på samme model |
| CO-3 | Skal hypotesen C7 (kommunen som kanal) afprøves sammen med ECK-samtalerne? | **Nej.** C7 parkeres. ECK-samtalerne holdes fri af fællesskabslaget |

## 7. Forhold til udviklingsplanen

Dokumentet ændrer ikke rækkefølgen. Fællesskabsfunktioner forudsætter identitet (F3), kontekster og hjem (F2, F4) og livets indbakke (F6). C1–C6 er indhold til fællesskabsfundamentets §9 pkt. 2–5, når de trin nås.

---

## Kilder

- DR: [Forskere: Shopping og svindel definerer i højere grad dine sociale medier](https://www.dr.dk/nyheder/indland/forskere-shopping-og-svindel-definerer-i-hoejere-grad-dine-sociale-medier) (25. november 2026), om rapporten *Sociale platformes økonomiske magt* fra Magtudredningen 2.0
- Forbrugerrådet Tænk: [Kun hver 4. svindelannonce bliver fjernet fra sociale medier](https://taenk.dk/forbrugerliv/elektronik-og-digitale-tjenester/kun-hver-4-svindelannonce-fjernes-sociale-medier)
- Fællesskabsfundamentet (#165), ADR-0005, ADR-0006, EIRA-CONTEXT 1.0 (se øverst)
