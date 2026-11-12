# ADR-0007 — Adgangskoder og nøgler: ingen kode, du selv finder på

**Status:** Foreslået, til ejerens accept (12. november 2026). Retningen er ejerens; udformningen er et forslag.
**Gælder for:** kontekster (EIRA-CONTEXT, nøglehierarki og lager), `identityd`, gaten og samtykkeagenten, Web App Manager (ADR-0004 D3), genoprettelse (ADR-0005 K5), ID-hjemmet (ADR-0005 K11)
**Relateret:** [ADR-0004](ADR-0004-gui-arkitektur-vendor-neutral.md), [ADR-0005](ADR-0005-kontekster-og-datas-hjem.md), [EIRA-CONTEXT](../../specs/EIRA-CONTEXT-1.0.md), [EIRA-CONSENT-AGENT](../../specs/EIRA-CONSENT-AGENT-0.1.md)

## Normativ regel

> **Personen finder aldrig selv på en kode. EiraOS skaber, gemmer, udfylder og fornyer adgangen. Personens europæiske eID er roden, der giver adgang til det hele igen, men eID-udbyderen kan aldrig selv se det.** (ejerens retning)

## Kontekst

Ejeren (12. november 2026): alle adgangskoder skal være sikre, systemet må ikke bygge på, at man selv finder på en kode, ens EU-ID skal give adgang til alle koder, og der skal kunne være rullende koder.

Tre ting fra omverdenen former forslaget:

- **Passkeys** (WebAuthn) erstatter adgangskoder, hvor tjenesten understøtter det: der er ingen delt hemmelighed at stjæle eller forny, og nøglen er bundet til tjenestens adresse, så den ikke kan lokkes ud på en falsk side.
- **Et åbent eksportformat findes:** FIDO Alliance's Credential Exchange Format (CXF) dækker adgangskoder, passkeys, TOTP-koder, SSH-nøgler og mere; det blev Proposed Standard i august 2025, mens protokollen til krypteret overførsel (CXP) stadig er et udkast.
- **EU-wallet'en er på vej, men dens rolle ved login er uafklaret:** alle medlemsstater skal udstede en EU-wallet ved udgangen af 2026, men om den skal fungere som passkey-udbyder, er omstridt: FIDO Alliance foreslår det, mens borgerrettighedsorganisationer advarer om, at det kan udhule retten til pseudonymer.

## Beslutninger (forslag)

### A1 — Rækkefølgen for, hvordan der logges ind

For hver tjeneste vælger EiraOS den stærkeste vej, tjenesten understøtter:

1. **Konteksten selv:** tjenesten bruger kontekstens identitet (OIDC/SSO). Der findes ingen kode.
2. **Passkey**, skabt af EiraOS i konteksten, med nøglen i enhedens TPM og en synkroniseret kopi krypteret i kontekst-hjemmet.
3. **En kode, EiraOS har skabt:** lang og tilfældig, unik pr. tjeneste. Personen ser den kun, hvis hun beder om det.
4. **Engangskoder (TOTP)** gemmes ved siden af og udfyldes på samme måde.

En kode, personen selv har fundet på, accepteres kun ved import (A6) og fornyes derefter (A5).

### A2 — Koderne bor i konteksten

- Hver kontekst har sit eget nøglebundt i sit eget krypterede lager (EIRA-CONTEXT §5–6), synkroniseret til kontekst-hjemmet og krypteret end-to-end. **Ingen deling mellem kontekster** (ADR-0005 K2): arbejdskoder findes kun i arbejdskonteksten.
- Arbejdskontekstens koder tilhører organisationen og genoprettes af den (escrow, EIRA-CONTEXT §5.4). Familiekontekstens fælles koder (fx streaming, wifi) bor i familiens kontekst.
- Hverken Eira, ID-hjemmet eller kontekst-hjemmets udbyder kan læse koderne.

### A3 — Oplåsning: eID er roden, ikke en daglig dør

| Situation | Hvad låser op |
|---|---|
| Daglig brug på egen enhed | At konteksten er låst op (login + enhedens TPM). **Ingen ekstra hovedadgangskode** |
| Se, kopiere eller eksportere en rå kode | Samtykkeagenten og en frisk bekræftelse af personen; eksport kræver eID (A7) |
| Ny enhed, mistet enhed, glemt alt | eID på niveau høj (MitID nu, EU-wallet når den findes) frigiver kontekstens nøgle efter ADR-0005 K5: genoprettelsestjenesten verificerer eID, men den indpakkede nøgle ligger i kontekst-hjemmet, og ingen andre end personen kan åbne den |

Det er sådan "EU-ID giver adgang til alle koder" opfyldes uden at gøre eID-udbyderen eller Eira til nøgleholder. eID bruges, når der står meget på spil, ikke ved hvert login, for et eID-krav hele dagen ville lære folk at godkende uden at læse.

### A4 — Kun den rigtige app får den rigtige kode

- En kode eller passkey udfyldes kun i den app, hvis oprindelse den er gemt til (Web App Manager kender appens oprindelser, ADR-0004 D3). En falsk side får intet, fordi den ikke er appen.
- **AI'en ser aldrig en kode.** Modelprocessen har ingen adgang til nøglebundtet; den kan foreslå "log ind på X", men udfyldningen sker uden om den.
- Eira UI's webview indeholder aldrig en kode (ADR-0004 D2).
- At vise, kopiere, dele eller eksportere en kode er en beskyttet handling gennem gaten, med samtykke i samtykkeagenten.

### A5 — Rullende koder: forny, når det gør en forskel

| Hvad | Hvordan |
|---|---|
| Passkeys | Behøver ingen fornyelse: der er ingen delt hemmelighed |
| Koder ved læk | **Altid.** Er en tjeneste kompromitteret, eller optræder koden i et kendt læk, fornyer EiraOS den |
| Koder efter plan | Kun hvor konteksten beder om det (fx organisationens politik via Fleet), ikke som standard. Tvungen fornyelse efter kalender gør ikke tilfældige, unikke koder sikrere |
| Maskin- og app-hemmeligheder (API-nøgler, app-adgangskoder, SSH) | Kort levetid og automatisk fornyelse, hvor tjenesten har en API til det |
| Hvordan fornyelsen sker | Hvor tjenesten har en API, automatisk; ellers via tjenestens side til skift af kode (`/.well-known/change-password`), hvor EiraOS udfylder ny kode, og personen bekræfter |

**Ærlig grænse:** fuldautomatisk fornyelse overalt er ikke mulig, fordi mange tjenester kræver et menneske (CAPTCHA, e-mailbekræftelse). EiraOS skal sige, hvilke tjenester det kan forny selv, og hvilke der kræver personen. Det må ikke love mere.

### A6 — Ind: flyt dine koder hjem på én gang

Import fra andre kodeholdere (CXF og de almindelige CSV-formater) er en del af første opstart. Importerede koder, som personen selv har fundet på, eller som går igen på flere tjenester, markeres og fornyes efterhånden (A5).

### A7 — Ud: exit-garantien gælder også koder

Personen kan altid eksportere alle sine koder og passkeys i CXF, krypteret, efter eID-bekræftelse. Det er exit-garantien (ADR-0005) anvendt på adgang.

### A8 — "Mine adgange"

Personen kan se, pr. kontekst: hvilke tjenester EiraOS logger ind på og hvordan (A1), hvilke koder der er svage, genbrugte eller lækkede, hvornår de sidst blev fornyet, og hvilke apps og delegationer der har adgang til hvad. Det er den samme oversigt som i udviklingsplanen ("Mine adgange"), udvidet med koder.

## Konsekvenser

- **Ny kontrakt** `EIRA-CREDENTIALS` (lagerformat i konteksten, udfyldning, fornyelse, eksport), skrevet efter EIRA-CONTEXT og Web App Manager-kontrakten, fordi den bygger på begge.
- **EIRA-CONTEXT:** nøglebundtet er en del af kontekstens lager og nøglehierarki; F-1 (glemsel) skal også dække koderne.
- **Web App Manager (ADR-0004 D3):** bliver passkey-udbyder og den eneste, der udfylder koder; oprindelserne i app-manifestet er det, der binder en kode til en app.
- **Gaten:** nye handlingstyper for vis, kopiér, del, eksportér og forny kode, alle med samtykke.
- **Læk-tjek:** kræver et opslag udadtil. Det skal ske uden at afsløre koden (kun et kort præfiks af en hash forlader enheden), og det er en beslutning, hvem der driver tjenesten (O-2).

## Åbne spørgsmål

- **O-1 EU-wallet som passkey-udbyder.** Skal EiraOS kunne bruge EU-wallet'ens passkeys, når de findes, eller holde sine egne? Afhænger af, hvordan implementeringsretsakterne ender.
- **O-2 Læk-tjek.** Egen tjeneste, en tredjepart med k-anonymitet, eller slået fra som standard?
- **O-3 Digital arv.** Hvordan får de efterladte adgang, når en person dør? Forslag: en udpeget arving, der efter dokumentation (eID og dødsattest) og en ventetid får en eksport af de konti, personen har markeret.
- **O-4 Fælles koder i familien.** Bor de i familiekonteksten, og hvem må se dem? Værgestyrede børn bør kun kunne bruge, ikke se.
- **O-5 Koder uden for webapps.** Wifi, VPN, SSH og apps, der ikke er webapps: samme nøglebundt, men hvem udfylder dem?

## Ikke-mål

- En hovedadgangskode, personen skal huske.
- At AI'en eller Eira UI nogensinde ser en kode.
- At Eira, ID-hjemmet eller en eID-udbyder kan læse personens koder.
