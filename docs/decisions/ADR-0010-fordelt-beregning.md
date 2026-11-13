# ADR-0010 — Fordelt beregning: arbejde kan flytte, myndighed kan ikke

**Status:** Foreslået, til ejerens accept (13. november 2026). Retningen er ejerens: fordelt beregning mellem personens enheder er en fremtidig funktion, som arkitekturen skal understøtte. Udformningen er et forslag. Intet bygges nu.
**Gælder for:** gaten og EiraSystemAPI (ADR-0002), `eira-modeld` og AI Interface, kontekster og enhedslisten (EIRA-CONTEXT §8), Fleet-rettigheder og attestation (EIRA-FLEET-RIGHTS-API §6), Web App Manager (ADR-0004 D3), hændelser og Event Store (ADR-0009 N3)
**Relateret:** [ADR-0002](ADR-0002-gate-to-handlingsfamilier.md), [ADR-0003](ADR-0003-rettigheder-fra-fleet.md), [ADR-0004](ADR-0004-gui-arkitektur-vendor-neutral.md), [ADR-0005](ADR-0005-kontekster-og-datas-hjem.md), [ADR-0009](ADR-0009-datalagets-byggesten-nextgraph.md), [AI-INTERFACE](../../specs/AI-INTERFACE-1.0.md), [EIRA-CONTEXT](../../specs/EIRA-CONTEXT-1.0.md), [EIRA-FLEET-RIGHTS-API](../../specs/EIRA-FLEET-RIGHTS-API-1.0.md), [GATE-KERNEL](../../specs/GATE-KERNEL-1.0.md)

## Normativ regel

> **Beregning kan flytte mellem personens egne enheder. Beslutninger, nøgler og samtykke flytter aldrig. Den enhed, hvor personen handler, afgør gennem sin gate, om arbejdet må sendes; den enhed, der modtager det, afgør gennem sin egen gate, om det må udføres.**

## Kontekst

Ejeren (13. november 2026): EiraOS skal på sigt kunne flytte *arbejde* mellem enheder, fx at en tung model kører på en hjemmeserver eller organisationens server, mens laptoppen sender opgaven. I dag flytter EiraOS kun *data* (kontekster, F2).

Anledningen var en gennemgang af EU-projektet NEMO (Horizon Europe, meta-OS til IoT/edge/cloud). NEMO's meta-orchestrator placerer og flytter arbejdsbyrder selv, oven på Kubernetes. Vi tager tankegangen og ikke maskineriet. Tre ting fra NEMO er værd at tage med (D6–D8), og én ting tager vi ikke: en orkestrator med egen beslutningsmagt.

To eksisterende regler støder direkte mod funktionen og skal ændres bevidst, ikke snige sig ud:

- **AI-INTERFACE §176:** modelprocessen har intet netværk; ingen cloud-fallback og ingen ekstern inference.
- **EIRA-FLEET-RIGHTS-API §6 pkt. 1:** målt opstart og remote attestation er udskudt til et senere krav.

## Beslutninger (forslag)

### D1 — Hvad der kan flytte

| Kan flytte | Kan aldrig flytte |
|---|---|
| Beregning: modelinferens, indeksering og søgning, medie- og dokumentkonvertering, byg | Gatens beslutning, samtykke, rettigheder |
| Det datauddrag, opgaven kræver | Nøgler (kontekstens CMK, enhedens nøgler, consent-nøglen) |
| Resultatet, som hændelse tilbage | Kontekstens samlede data som bivirkning |

### D2 — Afsendelse er en handling gennem gaten

- At sende arbejde til en anden enhed er en EiraSystemAPI-operation (fx `system:compute.dispatch`) med egen policy-post og reversibilitetsklasse. Ingen bypass, ingen debug-vej (ADR-0002).
- **Placering er et forslag.** En planlægger (eller modellen) kan foreslå "kør på hjemmeserveren"; gaten afgør. Der findes ingen orkestrator, der selv flytter arbejde.
- Hvilke opgavetyper der må sendes, og til hvilke enheder, er rettigheder fra Fleet (ADR-0003). Uden rettighed kører arbejdet lokalt eller venter.

### D3 — Den modtagende enhed arver ingen tillid

- Den modtagende enhed er en executor med sin egen gate. Den kontrollerer selv afsenderens identitet, at begge enheder er på samme kontekst-enhedsliste (EIRA-CONTEXT §8), og at dens eget rettighedssæt tillader opgavetypen.
- Arbejdet kører i den samme kontekst-isolation som lokalt (én Linux-bruger pr. kontekst, EIRA-CONTEXT §3), aldrig i en fælles tjenestebruger på tværs af kontekster.
- Den modtagende enhed beholder intet af datauddraget, når opgaven er færdig; det svarer til glemsel (F-1).

### D4 — Kun personens egne enheder, i samme kontekst

- Arbejde sendes kun til enheder på samme konteksts enhedsliste. En arbejdskontekst kan derved bruge organisationens egne, Fleet-styrede servere; en personlig kontekst kan bruge personens hjemmeserver.
- **Ingen tredjeparts-beregning** (cloud-inference hos en udbyder) under denne ADR. Ønskes det senere, kræver det sin egen ADR (O-3).
- Opgave og resultat krypteres end-to-end til modtagerens enhedsnøgle. Transporten bærer intet læsbart.

### D5 — Modelprocessen forbliver uden netværk

- `eira-modeld` får ikke netværk. Afsendelse sker gennem en særskilt proces (arbejdsnavn `eira-dispatchd`) med netværk kun til enheder på kontekstens enhedsliste, og uden adgang til modellens eller kontekstens øvrige data.
- AI-INTERFACE §176 ændres fra "ingen ekstern inference" til "ingen inference uden for personens egne enheder i samme kontekst, og kun gennem gaten". Det er en ændring af en normativ regel og kræver ejerens accept (O-1).

### D6 — Attestation bliver en forudsætning

- På administrerede enheder må en enhed kun modtage arbejde, når Fleet har verificeret dens tilstand (målt opstart, TPM-quote ved enroll og heartbeat). Funktionen gør derfor EIRA-FLEET-RIGHTS-API §6 pkt. 1 fra "senere" til "før fordelt beregning".
- Personlige enheder uden attestation kan bruges i personlige kontekster, men skallen viser det åbent, på samme måde som `key_protection: "file"` (EIRA-CONTEXT §5).

### D7 — Ét fælles manifest for alt, der kan køre (fra NEMO)

Alt, der kan udføres i EiraOS — webapps (ADR-0004 D3), adaptere, executors og opgavetyper til fordelt beregning — beskrives i ét manifestformat: hvad det er, hvilke rettigheder og dataklasser det kræver, ressourcebehov, og om det må køre på en anden enhed. Manifestet valideres, før noget registreres. Registrering og aktivering er hver sin handling gennem gaten. Fleet tildeler rettigheder mod det, manifestet erklærer.

### D8 — Stående mål ved siden af engangshandlinger (fra NEMO)

En intention kan være en engangshandling (i dag) eller et stående mål, der skal holdes ("hold mine koder sikre", ADR-0007 A5; "hold konteksten synkroniseret", F2.6; "kør tunge opgaver på hjemmeserveren, når laptoppen er på batteri"). Et stående mål har en målt opfyldelse (opfyldt, forringet, brudt), som skallen viser ærligt. Hver rettende handling går gennem gaten som en almindelig handling; målet giver ingen rettigheder i sig selv.

### D9 — Ærlig fejl

Er modtageren utilgængelig, afvist eller uden attestation, kører arbejdet lokalt, venter eller fejler synligt. Det sendes aldrig stille videre til en anden enhed eller en tredjepart.

## Konsekvenser

**Nu (ingen kode):** de beslutninger, der træffes i mellemtiden, må ikke lukke døren:

- **EIRA-CONTEXT §8 (enhedslisten):** skal kunne bære en enheds rolle (fx `compute_host`) og attestationsstatus.
- **EIRA-FLEET-RIGHTS-API:** rettighedssættet skal kunne udtrykke opgavetyper og modtagende enheder; attestation planlægges som forudsætning (D6).
- **Gate-registry:** operationsfamilien `system:compute.*` reserveres.
- **Web App Manager-kontrakten (ADR-0004 D3):** skrives, så dens manifest kan blive det fælles manifest (D7).
- **AI-INTERFACE:** ændringen i D5 skrives ind, når O-1 er besluttet.

**Senere:** egen kontrakt `EIRA-COMPUTE` (opgaveformat, afsendelse, modtagelse, kryptering, resultat som hændelse), skrevet efter F2 (kontekster) og efter attestation i Fleet.

## Åbne spørgsmål

- **O-1 Ændring af AI-INTERFACE §176** (D5): accepterer ejeren inference på egne enheder i samme kontekst?
- **O-2 Hvilke opgavetyper først?** Forslag: modelinferens, fordi det er der, behovet er størst.
- **O-3 Tredjeparts-beregning** (europæisk cloud-inference): uden for denne ADR; kræver sin egen.
- **O-4 Stående mål (D8):** egen kontrakt, eller en udvidelse af EDP/EiraSystemAPI?

## Ikke-mål

- Kubernetes eller anden klyngeorkestrering i EiraOS Desktop.
- En orkestrator, planlægger eller model, der selv beslutter, hvor arbejde kører.
- Brede tjenesterettigheder (som `cluster-admin`) til nogen komponent.
- Beregning på enheder uden for kontekstens enhedsliste.
