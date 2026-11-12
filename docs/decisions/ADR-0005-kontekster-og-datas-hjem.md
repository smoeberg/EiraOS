# ADR-0005 — Kontekster: enheden er neutral, rollen bestemmer, data bor hos konteksten

**Status:** Foreslået, til ejerens accept (11. november 2026). K1–K12 er ejerens retning.
**Gælder for:** `identityd`, Gate (lag 4 og 6), `fleetd`/`eira-governance-agent`, graphd (universet), Web App Manager (ADR-0004 D3), lagring og synkronisering, installer og første opstart
**Relateret:** [ADR-0003](ADR-0003-rettigheder-fra-fleet.md) (rettigheder fra Fleet), [ADR-0004](ADR-0004-gui-arkitektur-vendor-neutral.md) (vendor-neutral), [EIRA-IDENTITY 1.0](../../specs/EIRA-IDENTITY-1.0.md)

## Normativ regel

> **Enheden ejer intet. Personen har roller. Hver rolle bor, hvor den hører hjemme.**
>
> Den fysiske enhed er "dum": det er rollen i EiraOS, der afgør, om man er på arbejde, har fri eller sidder til bestyrelsesmøde i badmintonklubben.
>
> **Exit-garanti:** Dine data kan altid læses uden EiraOS. Formatet, de gemmes i, er åbent dokumenteret, og et åbent værktøj kan læse dem med personens (eller organisationens) nøgler.

## Begreber

| Begreb | Betydning |
|---|---|
| **Person** | Mennesket ved skærmen |
| **Identitet** | Et login hos en identitetsudbyder (`did:eira:<provider-id>.<subjekt>`, EIRA-IDENTITY) |
| **Kontekst** | En identitet *plus* en rolle givet af en organisation (eller af personen selv), med eget regelsæt, eget hjem, egne data, eget univers og egne webprofiler. Eksempler: arbejde (kommunen), fritid (personen), bestyrelse (klubben) |
| **Kontekst-hjem** | Det sted, en konteksts data autoritativt ligger: valgt af organisationen eller personen, aldrig af EiraOS |
| **ID-hjem** | Personens faste anker, drevet af EiraOS. Indeholder ingen følsomme data i læsbar form (K11) |
| **Enhed** | Maskinen. Har en krypteret, lokal kopi af de kontekster, der er i brug, og er aldrig den autoritative kilde |

En kontekst er ikke altid en egen identitetsudbyder. En forening har sjældent et login-system. Bestyrelsesrollen er en rolle, som klubben giver personens private identitet.

## Beslutninger

### K1 — Konteksten er grundenheden; enheden er neutral

Alt, hvad EiraOS viser og gør, sker i en kontekst. At skifte rolle er at skifte kontekst. Ingen funktion forudsætter, at enheden "tilhører" en bestemt organisation.

### K2 — Kontekster er adskilt

- Hver kontekst har sit eget krypterede lager og sine egne nøgler. En nøgle til én kontekst åbner ikke en anden.
- **Ingen deling mellem kontekster** (besluttet af ejer): data, filer og udklipsholder kan ikke flyttes fra én kontekst til en anden, heller ikke på brugerens opfordring. Det er bevidst friktion: grænsen mellem arbejde og fritid er absolut.
- Webprofiler (cookies, lagring) er pr. kontekst (ADR-0004 D3).
- En organisation kan ikke se, hvilke andre kontekster personen har, eller at de findes.

### K3 — Data bor hos konteksten; EiraOS definerer protokollen, ikke skyen

- EiraOS definerer, hvordan en kontekst synkroniseres med sit hjem. Lagringen bag kan udskiftes (fx S3-kompatibel, WebDAV). EiraOS kræver ingen egen sky til **data**. Krævede den det, blev Eira den nye leverandørbinding (ADR-0004 D1). Det eneste, EiraOS selv driver, er ID-hjemmet (K11), som ikke indeholder data.
- Hjemmet behøver ikke kunne læse data: lagring hos en tredjepart er end-to-end-krypteret med nøgler, som kun personen og dennes enheder har (for arbejdskontekster: organisationen).
- **Valg af hjem:** Fleet kan skubbe hjemmet ud for sine kontekster. Ellers peger brugeren selv på et hjem ved opstart. EiraOS foreslår ikke et bestemt hjem som standard.

### K4 — Offline fra start (local-first)

En kontekst skal kunne bruges fuldt offline fra 1.0. Det betyder:

| Område | Krav |
|---|---|
| Data | Læse og skrive offline mod den lokale kopi. Synkronisering, når der er net |
| Konflikter | Overskrives aldrig stille. Strukturerede data (universet i graphd) flettes deterministisk. Filer, der er ændret begge steder, bliver to versioner og et synligt konfliktobjekt |
| Gaten | Afgør offline mod det sidst modtagne, signerede rettighedssæt (allerede gyldigt inden for sin TTL, RIGHTS-SET) |
| Identitet | Login kræver net første gang. Derefter kan konteksten låses op offline med en enhedsbundet nøgle (TPM), så længe sidste online-login ikke er ældre end kontekstens maksimale offline-periode |
| Audit | Skrives lokalt og forankres hos Fleet, når der er net (audit-anker, GATE-KERNEL bilag A pkt. 2) |
| Tilbagekaldelse | Virker først, når enheden er online. Derfor har hver kontekst en maksimal offline-periode, sat af kontekstens regelsæt (Fleet for organisationer, personen for fritid), hvorefter konteksten låses, til den har været online |
| Webapps | Offline kun i det omfang, appen selv understøtter det. Status vises ærligt |

### K5 — Genoprettelse forankret i europæisk eID

- Mistede nøgler må ikke være eneste udvej, men genoprettelse må heller ikke blive en bagdør.
- Genoprettelse af en personlig kontekst forankres i en eID på sikringsniveau **høj** efter eIDAS. Målet er EU Digital Identity Wallet, som hver medlemsstat skal stille til rådighed fra december 2026. MitID er første konkrete tilslutning via en adapter. Mekanismen er ikke bundet til ét land eller én eID.
- Genoprettelsestjenesten opbevarer kun en indpakket nøgle, som den ikke selv kan åbne. Den frigives først efter stærk autentifikation og en ventetid, hvor personens andre enheder får besked og kan afbryde.
- Arbejdskontekster genoprettes af organisationen, ikke af personens eID.
- **Drift (besluttet af ejer):** Eira driver genoprettelsesfunktionen, altså verifikationen af eID og frigivelsen. Den indpakkede nøgle ligger i kontekstens hjem (kommunens eller den privates sky), ikke hos Eira. Eira kan derfor hverken læse data eller frigive en nøgle uden personens eID. Protokollen er åben, så andre kan drive en tilsvarende tjeneste (ADR-0004 D1).

### K6 — Hvem styrer enheden

- En enhed, der er enrolled hos en organisation via Fleet, styres af organisationens Fleet: opdateringer, kryptering af enheden og hvem der må logge ind.
- Fleet-administratoren bestemmer, om enheden er **lukket** (kun organisationens kontekster) eller **åben** for flere identiteter og kontekster (fx fritid på en arbejds-pc).
- En enhed uden Fleet styres af personen.

**To veje ved første opstart (besluttet af ejer, 12. november 2026).** Installationen spørger én gang, hvem enheden tilhører:

| Vej | Hvad sker der | Hvem styrer enheden | Rettigheder |
|---|---|---|---|
| **Tilknyt en organisation** | Enheden enrolles hos organisationens Fleet (EIRA-FLEET-RIGHTS-API §8) | Organisationens Fleet | Organisationens rettighedssæt |
| **Opret eller brug et Eira ID** | Personen opretter eller logger ind med sit Eira ID (ID-hjemmet, K11). Ingen Fleet | Personen | Pakkens standardsæt (RIGHTS-SET §5) |

- På en organisations-enhed bestemmer Fleet-administratoren, om enheden er lukket eller åben (ovenfor). Det er ét flueben pr. enhed i Fleet (`device_mode`). Er det slået til, viser skallen menupunktet **"Log ind i en anden kontekst"**, og personer kan tilknytte deres private Eira ID ved siden af organisationens kontekster. Er det slået fra, findes menupunktet ikke.
- Et privat Eira ID på en organisations-enhed giver ingen særstilling: dets kontekster får hver sin Linux-bruger efter K7, som alle andre kontekster. Et Eira ID med to kontekster (fx fritid og familie) giver altså to Linux-brugere.
- Organisationen styrer enheden, ikke de private kontekster. Fleet ved, *at* enheden er åben, men aldrig, hvilke private Eira ID'er eller kontekster der bruger den (K2).
- Uden sudo: et privat Eira ID på en organisations-enhed får ingen administratorrettigheder på enheden (ADR-0003, managed mode).
- Rettigheder for private kontekster på en åben organisations-enhed: se O-9 (besluttet). Åbent punkt: O-8.

**Aflevering af en organisations-enhed (besluttet af ejer, 12. november 2026).** Når en medarbejder stopper, lukker organisationen medarbejderens login, og enheden afleveres. Når Fleet-administratoren lukker enheden i Fleet, opdateres **alle** kontekster, der er tilknyttet enheden, også de private:

1. Fleet fjerner enheden fra organisationskonteksternes enhedslister og roterer deres CMK (EIRA-CONTEXT §8).
2. Fleet sender kommandoen *tilbagekald enhed* til enheden. Enheden melder sig selv ud af hver privat kontekst, den kender: den signerer en enhedsliste uden sig selv og sender den til kontekstens hjem (EIRA-CONTEXT §8.1). Fleet ser ikke, hvilke private kontekster det drejer sig om.
3. Enheden sletter alle lokale kopier og nøgler (tilstand *fjernet*, EIRA-CONTEXT §4). Derefter kan administratoren køre *slet disk*.
4. Personen logger ind med sit Eira ID på en ny maskine og henter sine private kontekster fra deres hjem. Intet er tabt, fordi originalen aldrig lå på maskinen; den lokale kopi var kun krypteret cache.

Er enheden offline eller væk, når Fleet lukker den, kan den ikke melde sig ud. Så låses dens private kontekster senest efter `max_offline_days`, og personen kan fjerne den fra en anden enhed.

### K7 — Isolation: én Linux-bruger pr. kontekst bag én samlet oplevelse (besluttet)

Hver kontekst kører som sin egen Linux-bruger, så kernen holder filer og processer adskilt (K2). Brugeren ser én EiraOS. Grænserne, der opstår, er netop dem, der alligevel skal kontrolleres:

| Område | Løsning |
|---|---|
| Skærm | Compositoren giver hver kontekst sin egen Wayland-socket (`wp_security_context_v1`) og ved dermed, hvilken kontekst hvert vindue tilhører (ADR-0004 D6) |
| Lyd, D-Bus, notifikationer | Pr. kontekst. Kun samlet output (lyd ud, notifikationer) går gennem en snæver formidler |
| Udklipsholder og filer | Deles ikke mellem kontekster (K2) |
| Eira-skallen | Kører som en neutral bruger uden adgang til konteksternes data. Ser kun det, hver kontekst selv udstiller (navn, ikoner, status) |

Én Linux-bruger med kryptering pr. kontekst er fravalgt: et kompromitteret program i én kontekst kunne læse en anden, så snart den er låst op. Containere under samme UID er fravalgt af samme grund.

### K8 — Synkronisering i tre udskiftelige lag (besluttet)

1. **Lagring:** standard og uden logik. S3-kompatibel først, WebDAV som nummer to. Kunden kan altid flytte til en anden udbyder.
2. **Kryptering og format:** EiraOS' eget, men åbent dokumenteret (exit-garantien). Klienten krypterer i indholdsadresserede blokke, før noget sendes. Et Merkle-træ over blokindekset beviser, at intet er udeladt eller ombyttet.
3. **Fletning:** strukturerede data (universet, objekter, relationer i graphd) flettes med et modent, åbent CRDT, fx Automerge (Rust), ikke en egen algoritme. Filer flettes ikke: samtidige ændringer bliver to versioner og et synligt konfliktobjekt (K4).

`fleetd`s nuværende Merkle-synkronisering videreudvikles ikke som fundament; teknikken genbruges i lag 2.

### K9 — Flere personer på samme enhed: Ubuntus brugere, men skabt af EiraOS (besluttet)

Ubuntu (logind) håndterer allerede flere samtidige brugere og sessioner, og EiraOS bygger på det i stedet for at opfinde sit eget. Forskellen er, at personer aldrig ser eller opretter Linux-brugere:

- Den neutrale skal-bruger (K7) logges automatisk ind af greetd. Det er "den dumme enhed": den viser kun "Log ind", aldrig en liste over, hvem der ellers bruger maskinen.
- Når en person logger ind (OIDC), opretter eller låser EiraOS de Linux-brugere op, der hører til personens kontekster på denne enhed. De er systemstyrede og har ingen adgangskode.
- To personer på samme enhed har hver deres kontekster og kan ikke se hinandens (K2).

Konsekvens: greetd autologger i dag ind som en fast bruger (`ubuntu`). Det skal ændres til den neutrale skal-bruger.

### K10 — Næsten konstant online som udgangspunkt (besluttet)

EiraOS udvikles ud fra, at forbindelse er næsten konstant. Offline (K4) er en sikker reserve, ikke den normale tilstand: konteksten virker videre ved afbrydelser, og konflikter håndteres som i K4, men designet optimeres ikke til lange offline-perioder. Standard for maksimal offline-periode i personlige kontekster: **7 dage** (foreslået, kan ændres af personen). Organisationer sætter deres egen via Fleet.

### K11 — ID-hjemmet: fast hos EiraOS, uden følsomme data (besluttet)

Der er to slags hjem: **kontekst-hjem** (data, valgt pr. kontekst, K3) og ét **ID-hjem** pr. person, som altid er EiraOS'. ID-hjemmet er personens anker på tværs af enheder: ved login på en hvilken som helst EiraOS-maskine finder enheden personens kontekster gennem det.

**ID-hjemmet indeholder kun:**

| Indhold | Form | Hvad Eira kan se |
|---|---|---|
| Kontoens id | Pseudonym, afledt pr. tjeneste af personens eID (ikke CPR eller tilsvarende) | At en konto findes |
| Personens kontekstliste og pegepinde til kontekst-hjemmene | Krypteret med personens nøgle | Intet: en uigennemsigtig blok og dens størrelse |
| Offentlige nøgler for personens enheder | Offentlige nøgler | Hvor mange enheder kontoen har |

**ID-hjemmet indeholder aldrig:** data fra nogen kontekst, læsbare navne på organisationer, roller eller kontekster, nøgler, der kan åbne data (genoprettelsens indpakkede nøgler ligger i kontekst-hjemmene, K5), eller indhold af nogen art.

Listen over en persons kontekster er følsom i sig selv (den afslører arbejdsgiver og foreningsliv). Derfor ligger den kun krypteret. Eira kan ikke læse den, heller ikke på krav fra en myndighed.

**Krav:**
- **Minimal logning:** ID-hjemmet gemmer ikke IP-adresser eller tidspunkter for opslag ud over det, driften strengt kræver, og sletter dem hurtigt. Brugsmønstre er også følsomme data.
- **Exit-garantien gælder:** personen kan altid hente en krypteret kopi af sin ID-post. Forsvinder Eiras ID-hjem, har personen stadig sine kontekst-hjem og nøgler og kan læse alle data (K8).
- **Ikke i datavejen:** ID-hjemmet bruges ved login og ved skift af enhed, ikke ved hver læsning eller skrivning. Er det nede, kører allerede åbnede kontekster videre (K4).
- **Lukkede enheder kører uden (besluttet af ejer):** en enhed, som Fleet har lukket for andre end organisationens kontekster (K6), bruger ikke ID-hjemmet. Kontekstlisten kommer da fra Fleet, og der er ingen Eira-tjeneste i login-vejen. Organisationer, der ikke vil have en tredjepart i medarbejdernes login, kan altså bruge EiraOS. Åbnes enheden for flere kontekster, bruges ID-hjemmet for de personer, der har mere end organisationens kontekster.
- **Privat indhold** hører ikke til i ID-hjemmet. Ønsker personen at bruge Eira til private data, er det et kontekst-hjem som alle andre, et tilvalg og ikke en del af ID-hjemmet.

### K12 — Familie og værger (besluttet af ejer, 11. november 2026)

**Familien er en kontekst.** Forældre og børn er medlemmer; familiekalenderen og fælles begivenheder bor i familiens hjem (fx CalDAV). Klubbers og skolers begivenheder ser forældre i fællesskabets egen kontekst via en forælderrolle (forslag #165).

**"Overfør glimt"** er den eneste undtagelse fra "ingen deling" (K2): personen kan oprette en begivenhed i en anden kontekst (fx familiekalenderen) ud fra et kalender-glimt (ADR-0006 L5). Kun tid og sted følger med; titlen skriver personen selv. Det virker kun, hvis kildekonteksten har tilladt kalender-glimt.

**Værgestyret kontekst.** Et barns personlige kontekst styres af dets værger med samme politikmekanisme som Fleet, men uden Fleet-tjenesten:

- Værgernes regler er et dokument signeret med værgernes enhedsnøgler. Det ligger i familiens hjem og håndhæves af barnets enheder som et rettighedssæt. Ingen central tjeneste og ingen organisation imellem.
- **Værgen ser kun regler og et brugsoverblik** (tid, hvilke apps og kontekster). Aldrig indhold: beskeder, dokumenter, billeder. Forældrestyring er ikke overvågning.
- **Faste alderstrin i EiraOS:**

| Trin | Værgen kan |
|---|---|
| Under 13 år | Sætte tidsrum; tillade webapps og adaptere (kun tilladte virker); godkende nye kontakter; godkende køb og andre handlinger med konsekvens gennem gaten (andet sæt øjne) |
| 13–17 år | Sætte tidsrum; spærre bestemte webapps og adaptere (alt andet virker); godkende køb over en grænse, værgen sætter |
| 18 år | Intet. Værgestyringen ophører automatisk, og konteksten bliver fuldt personlig. Data har hele tiden været barnets |

- **Alderstrin afgøres uden at gemme fødselsdato:** ved barnets login med eID bruges en aldersattest ("over 13", "over 18"), som EU Digital Identity Wallet understøtter. EiraOS gemmer ikke CPR-nummer eller fødselsdato.
- **Værgerelationen i 1.0** (besluttet af ejer): samme niveau som branchen (Apple Familiedeling, Microsoft Family Safety), men stærkere bevis for voksenstatus. Som hos dem bekræftes, at værgen er voksen, ikke at værgen er barnets forælder:
  - **Voksenstatus via eID-aldersattest** ("over 18"), ikke via betalingskort.
  - **Den første værge opretter barnets kontekst** og inviterer den anden. To værger er ligestillede; ingen af dem kan fjerne den anden alene. Uenighed om værgeskab løses uden for EiraOS og afspejles i EiraOS, når begge værger eller en officiel kilde bekræfter det.
  - **Gennemsigtighed som værn:** fra 13 år kan barnet selv se, hvem dets værger er, og hvilke regler der gælder.
- **Officiel bekræftelse af forældremyndighed** (fx fra offentlige registre eller som attest i EU Digital Identity Wallet) undersøges parallelt og tilføjes, når der findes en lovlig adgangsvej. Det er ikke et krav for 1.0.

## Konsekvenser for det eksisterende

- **ADR-0003 og RIGHTS-SET** binder i dag rettighedssæt til en enhed (`tenant_id`, `device_id`). Det skal udvides til at binde til en kontekst, så en organisation kan styre sin kontekst på en enhed, den ikke ejer. Revision af RIGHTS-SET kræves.
- **EIRA-IDENTITY 1.0** har én udbyder pr. maskine. Den skal udvides (1.1) til udbydere pr. kontekst og flere samtidige identiteter, og O-1/O-2 skal opdateres efter denne ADR (tenant-migrering = nyt provider-id med overgangsliste fra Fleet).
- **Sessioner** i `identityd` og gaten bliver pr. kontekst. Samtykkeagenten (EIRA-CONSENT-AGENT) viser altid, i hvilken kontekst et samtykke gives.
- **graphd:** et univers pr. kontekst.
- **Web App Manager:** profil = kontekst (afløser ADR-0004 O-4).
- **Politikmekanismen** (Fleet) skal også kunne bruges med værgesignerede regler (K12); EIRA-CONTEXT §2 får `governance.source = guardian`.
- **`fleetd`**s E2EE-synkronisering med Merkle-træer afløses af K8. Merkle-teknikken genbruges i lag 2.
- **Compositor og skal (ADR-0004):** én Wayland-socket pr. kontekst og en neutral skal-bruger (K7) skal ind i compositor-sporet og Eira UI.
- **Session (K9):** greetd skal autologge ind som den neutrale skal-bruger i stedet for `ubuntu`.
- **Ny kontrakt:** et åbent, dokumenteret lagerformat (K8 lag 2) med et referenceværktøj, der læser det uden EiraOS.
- **Ny tjeneste:** ID-hjemmet (K11) med kontrakt for indhold, kryptering, pseudonym og logning.

**Rækkefølge (forslag):** ADR-0005 accepteres → kontrakt for kontekster og lagring → EIRA-IDENTITY 1.1 (identitet pr. kontekst) → Web App Manager. Web App Manager bygges ikke før konteksten, fordi dens profiler er konteksterne.

## Åbne spørgsmål

- **O-8 Enroll ved installation.** I dag enrolles en enhed efter installationen: IT kører `eira-enroll` som root med en invitationsfil, der indeholder Fleets CA (EIRA-FLEET-RIGHTS-API §8). Vejen "Tilknyt en organisation" i installeren kræver, at personen kan indtaste en kort kode, og at enheden kan hente invitationen ud fra koden. Åbent: hvilket endpoint der slår koden op, og hvilket tillidsanker enheden bruger, før den kender organisationens CA (fx en Eira-CA indbygget i installeren).
- ~~**O-9 Rettigheder for private kontekster på en åben organisations-enhed.**~~ Besluttet af ejer 12. november 2026: Fleet-administratorens eneste valg er fluebenet (K6). En privat kontekst på en åben organisations-enhed får pakkens standardsæt (RIGHTS-SET §5.2), som på en privat maskine, men **uden `system:`-handlinger på `device:local`**, fordi maskinen tilhører organisationen. Organisationens sæt gælder kun organisationens kontekster. Fleet udsteder intet for private kontekster og får ikke oplyst, hvilke der findes. Kræver RIGHTS-SET-revisionen (sæt pr. kontekst, F3.2); indtil da har private kontekster på en enrolled enhed ingen rettigheder (`awaiting_managed_set`).

- ~~**O-7 Arbejds-pc'er uden ID-hjem.**~~ Besluttet: en lukket enhed kan køre helt uden ID-hjemmet (K11).

- ~~**O-1 Isolation i OS'et.**~~ Besluttet: K7.
- ~~**O-2 Genoprettelsestjenesten.**~~ Besluttet: Eira driver funktionen, nøglen ligger i kontekstens hjem (K5).
- ~~**O-3 Synkroniseringsprotokol.**~~ Besluttet: K8.
- ~~**O-4 Maksimal offline-periode.**~~ Besluttet: K10.
- ~~**O-5 Flere personer.**~~ Besluttet: K9 og K11. Enheden husker intet læsbart: før login ved den hverken, hvem der har brugt den, eller hvilke kontekster der findes. Personens kontekstliste hentes fra ID-hjemmet ved login. Enheden har kun en krypteret cache af listen og af de kontekster, der er i brug, og ubrugte kontekster ryddes væk efter en periode.
- ~~**O-6 Deling mellem kontekster.**~~ Besluttet: ingen deling (K2).
