# ADR-0006 — Livets indbakke: Input → API → indbakke

**Status:** Foreslået, til ejerens accept (11. november 2026). L1–L6 er ejerens retning; O-1–O-3 afventer beslutning.
**Gælder for:** EDP, samtalelaget (`app/conversation/`), graphd, intentd og gaten, Web App Manager (ADR-0004 D3), kontekster (ADR-0005)
**Relateret:** [ADR-0004](ADR-0004-gui-arkitektur-vendor-neutral.md), [ADR-0005](ADR-0005-kontekster-og-datas-hjem.md), [EDP 1.0](../../specs/EDP-1.0.md), [EIRA-CONVERSATION 1.0](../../specs/EIRA-CONVERSATION-1.0.md)

## Normativ regel

> **Styresystemet er en forlængelse af dit liv. Alt, der kommer til dig, kan komme ind. EiraOS kender ikke kanalerne på forhånd, kun kontrakten.**

## Kontekst

Ejeren ønsker, at EiraOS samler alt, hvad der kommer til en person (mail, mobil, WhatsApp, Messenger, Teams og kanaler, der ikke findes endnu), ét sted pr. kontekst.

Inspirationen er [Ushahidi Platform](https://github.com/ushahidi/platform): en open source-platform, der indsamler signaler fra SMS, e-mail, Twitter og RSS, gør dem til strukturerede indberetninger via skemaer, fører dem gennem trin og placerer dem på et kort. EiraOS overtager **strømmen** (ustruktureret signal → struktureret, gennemgået objekt), ikke koden: Ushahidi er AGPL-licenseret og kræver PHP 7.4 og Laravel 8, som begge er udgået.

### Afvist: "EiraOS Social Fabric – Komplet Arkitektur Audit" (Vibe, 11. november 2026)

Dokumentet foreslog ni nye daemons (`contactsd`, `messaged`, `sociald`, `formsd`, `collectiond`, `tagd`, `geod`, `federationd`, `personald`) og afvises i sin helhed, fordi det:

- misforstår Ushahidi som et socialt netværk (opslag, reaktioner, "gør Facebook irrelevant");
- lægger alle brugeres data i fælles databaser under systembrugeren `eira`, i strid med ADR-0005 K2 og K7;
- bygger på Entra som login, Redis og samtykke med TTL pr. handlingstype, i strid med ADR-0004, EIRA-IDENTITY og gatens model;
- indeholder tal uden grundlag (testdækning, sikkerhedsniveau, ROI).

Det er ikke lagt i repoet. Kun denne ADR er gældende.

## Beslutninger

### L1 — Tre lag: Input → API → Livets indbakke

| Lag | Ansvar |
|---|---|
| **Input** | Adaptere, én pr. kanal. Taler kanalens sprog (IMAP, Matrix, Graph, notifikationer …) |
| **API** | Eira Input-kontrakten: stabil, versioneret og åbent dokumenteret. Det eneste, en adapter kender til EiraOS |
| **Livets indbakke** | Pr. kontekst. Modtager signaler, bevarer dem uændret og lader dem blive til objekter i universet (L3) |

En ny kanal, også en der opstår i morgen, er en ny adapter. Den kræver ingen ændring i kernen.

### L2 — Adapterkontrakten

- En adapter er en selvstændig proces, der kører som den konteksts Linux-bruger, den hører til (ADR-0005 K7), i en sandbox. Den har kun adgang til sin kanal og til Input-API'et.
- Den har et manifest: id, version, kanaltype og kapabiliteter (modtage, sende, læse status, vedhæftninger, kontakter, kalender).
- Indgående leveres som **signaler** i EDP-format. En adapter skriver aldrig direkte i graphd eller i andre konteksters indbakker.
- **Afsendelse går altid gennem gaten** med samtykke (EIRA-CONSENT-AGENT). En adapter kan ikke sende på egen hånd.
- Organisationer godkender adaptere til deres kontekster via Fleet. Personen godkender adaptere til sine egne.

### L3 — Fra signal til objekt

1. **Modtaget:** signalet ligger uændret i indbakken og bevares, så alt kan spores tilbage til kilden.
2. **Forstået:** den lokale AI foreslår en struktur (fx mailen om bestyrelsesmødet → objektet "Bestyrelsesmøde 20/11" med tid, sted, deltagere og dagsorden).
3. **Handlet:** svar, aftale eller opgave går gennem intentd og gaten. *AI'en foreslår. Gaten afgør. Systemet udfører.*
4. **Arkiveret.**

Det er Ushahidis skema → indberetning → trin, bare for én person og hendes kontekster. Sted og tid fra signalerne bliver akser i universet (ADR-0004 D4), ikke et separat kort.

### L4 — Kanaler: hvad der er muligt, og hvordan

| Kanaltype | Eksempler | Vej |
|---|---|---|
| Åbne protokoller | Mail (IMAP/SMTP, JMAP), kalender (CalDAV), kontakter (CardDAV), Matrix, XMPP, ActivityPub, RSS | Fuld adapter |
| Officielle API'er med organisationens samtykke | Teams og Outlook (Microsoft Graph), Slack, Google Workspace | Adapter i organisationens kontekst og på dens app-registrering. Leverandøren er gæst (ADR-0004 D1) |
| Lukkede forbrugertjenester | WhatsApp, Messenger | Ingen adapter; kun som almindelig webapp (se nedenfor) |
| Mobiltelefonen | SMS, opkald, notifikationer | Adapter via parring med telefonen (kandidat: KDE Connect-protokollen) |
| Myndigheder | Digital Post | Adapter, når der findes en tilgængelig adgangsvej (O-3) |

**WhatsApp og Messenger: ingen særlig indsats (besluttet af ejer).** EiraOS ser frem, ikke tilbage. Lukkede forbrugertjenester uden åben API får ingen adapter, ingen bro og ingen Eira-beskedtjeneste for at nå dem. Vil en person bruge dem, kører de som almindelige webapps via Web App Manager (ADR-0004 D3) uden særbehandling. EiraOS' egen kommunikation bygges på åbne protokoller (Matrix, mail, XMPP, ActivityPub).

Uofficielle broer bygget på reverse engineering bruges heller ikke. De bryder tjenesternes vilkår, kan få personens konto lukket og flytter beskedindhold gennem kode uden for vores kontrol.

### L5 — Skarpe grænser mellem identiteter; "glimt" viser kun aktivitet

Grænserne mellem kontekster er absolutte (ADR-0005 K2). Den eneste undtagelse er et **glimt** (besluttet af ejer):

- Et glimt viser **kun, at der er aktivitet** i en anden konteksts indbakke: kontekstens navn, antal nye signaler og hvornår. Eksempel: *"Bestyrelse, badmintonklubben: 3 nye siden kl. 14"*.
- Et glimt viser **aldrig** titler, afsendere, typer, uddrag eller vedhæftninger. En titel er også indhold.
- Et glimt kan **ikke åbnes og ikke læses**. For at læse skal personen skifte identitet til den kontekst (log ind/lås op). Et klik på glimtet tilbyder netop det skifte og intet andet.
- Glimt vises af den neutrale skal (ADR-0005 K7) og skrives aldrig ind i en anden konteksts lager eller indbakke.
- Kontekstens regelsæt bestemmer, om den må vise aktivitet udadtil. En organisation kan via Fleet forbyde glimt fra sin kontekst. Personen bestemmer, hvilke kontekster der viser glimt.

### L6 — Intet forlader EiraOS uden gaten

Svar, opslag, accept af en invitation og alt andet, der sendes på personens vegne, går gennem gaten med samtykke, uanset kanal. AI'en kan forberede et svar, men aldrig sende det.

## Konsekvenser

- **EDP** får en signaltype for indgående, der bevarer kilden uændret, og en reference fra objekt til signal.
- **Ny kontrakt:** Eira Input-API og adaptermanifest (`specs/`).
- **graphd:** objekttyper for møder, opgaver, aftaler, dokumenter og personer, med henvisning til de signaler, de kom fra.
- **Web App Manager:** en bro, der gør appens notifikationer til signaler i den rigtige kontekst.
- **Den neutrale skal:** visningen af glimt.
- **Rækkefølge (forslag):** kontekst- og lagerkontrakten (ADR-0005) → Input-API og adapterkontrakt → mail- og kalenderadapter som de første → Web App Manager med notifikationsbro.

## Åbne spørgsmål

- **O-1 Sandbox til adaptere.** Bubblewrap/Landlock, systemd-sandboxing eller begge?
- **O-2 Hvem må udgive adaptere?** Kun Eira, signerede tredjeparter eller alle med personens accept?
- **O-3 Digital Post.** Hvilken adgangsvej findes for en privat klient, og hvad kræver den?
- ~~**O-4 Eira-beskedtjeneste.**~~ Besluttet: nej. Ingen særlig indsats for WhatsApp og Messenger (L4).
- ~~**O-5 Glimtets indhold.**~~ Besluttet: kun aktivitet (kontekst, antal, tid). Læsning kræver skift af identitet (L5).
