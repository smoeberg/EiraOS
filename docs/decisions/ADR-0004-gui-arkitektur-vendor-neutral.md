# ADR-0004 — GUI-arkitektur: vendor-neutral, webapps som isolerede Eira-apps, 3D-universet som model

**Status:** Foreslået, til ejerens accept (11. november 2026). D1–D4 er ejerens retning, og D5 (spor A i 1.0) er besluttet. ADR'en forbliver "Foreslået", indtil identityd-migreringen ([EIRA-IDENTITY 1.0](../../specs/EIRA-IDENTITY-1.0.md)) og Chromium-undersøgelsen (O-1) har afdækket eventuelle konflikter.
**Gælder for:** Eira UI (`ui/`), en ny Eira Web App Manager, compositoren (`eira-labwc`, senere egen), `identityd`, Eira Core (graphd), ADR-0003, GATE-KERNEL, RIGHTS-SET
**Relateret:** [GUI-plan 1.0](../architecture/eiraos-gui-product-and-implementation-plan-1.0.md) §13 (åbne UX-beslutninger), [EIRA-CONSENT-AGENT](../../specs/EIRA-CONSENT-AGENT-0.1.md) R-6.1/R-6.2, [ADR-0003](ADR-0003-rettigheder-fra-fleet.md)

## Normativ regel

> **Du ejer din computer. Eira er dit interface. Linux er fundamentet. Du vælger selv dine tjenester og applikationer.**
>
> Ingen leverandør er en del af EiraOS. Microsoft og alle andre tjenesteudbydere er gæster: kompatibilitet med dem er et krav for en bestemt installation, aldrig et arkitekturprincip.

## Kontekst

Tre afklaringer fra ejeren (11. november 2026):

1. Brugeren skal ikke forholde sig til, at der findes et program til at se internettet. Webapplikationer kører direkte i EiraOS.
2. Målhardwaren er almindelige pc'er.
3. 3D-skrivebordet (universet) er retningen.

Samtidig blev et forslag om at lægge Quickshell (Qt/QML) som skal-lag under React afvist. Forslaget byggede på en forkert antagelse om, at Eira kører på Electron. Det gør den ikke (Tauri 2 + React 19, WebKitGTK, Rust-bagende). Quickshell ville kræve netop de privilegerede Wayland-protokoller, som R-6.1 tager fra alle klienter, og ville give to UI-stakke.

## Beslutninger

### D1 — Vendor-neutral grundarkitektur

EiraOS indeholder ikke og forudsætter ikke:

- en bestemt browser (fx Edge) som systemkomponent;
- en bestemt identitetsudbyder (fx Microsoft Entra) som afhængighed for login;
- leverandørspecifikke API'er i Eira Core;
- leverandørspecifikke krav i app-modellen;
- en bestemt kontorpakke eller samarbejdstjeneste (fx Microsoft 365).

Integrationer med bestemte udbydere ligger i adaptere og i installationens konfiguration (Fleet), ikke i kernen. En installation, der skal bruge et eksisterende Microsoft 365-/Entra-miljø, får det som tilvalg (§D3, "særlig runtime", og §Konsekvenser, identitet).

### D2 — To UI-flader med en hård grænse

| | **Eira UI** | **Web App Runtime** |
|---|---|---|
| Teknologi | Tauri 2 + React (WebKitGTK) | Chromium-motor som udgangspunkt (D3) |
| Indhold | Kun Eiras eget, pakket indhold | Fremmed webindhold |
| Adgang | Tauri-kommandoer → daemons og gate | Ingen Tauri-kommandoer, ingen daemon-sockets, ingen Eira-hemmeligheder |
| Proces | Én betroet app | Én eller flere isolerede processer pr. webapp |

**Regel:** Fremmed webindhold indlæses aldrig i en webview, der har adgang til Tauri-kommandoer eller Eira-daemons. Det er en sikkerhedsgrænse og ikke en anbefaling. Eira UI må heller ikke navigere til eksterne URL'er; links åbnes gennem Web App Manager.

### D3 — Eira Web App Manager: Eira ejer app-modellen, motoren er en implementationsdetalje

Eira definerer for hver webapp:

- **app-identitet** (stabilt id, navn, oprindelser/URL-mønstre, som hører til appen);
- **ikon** og præsentation;
- **rettigheder** (kamera, mikrofon, notifikationer, downloads, udklipsholder, skærmdeling), givet gennem gaten og Fleet og aldrig ad hoc i motoren;
- **lager og profil** (cookies, lokal lagring, cache) adskilt pr. app eller pr. identitet (O-4);
- **placering i universet** (D4);
- **livscyklus** (start, dvale, lukning, opdatering);
- **vinduesidentitet** (hvilket Wayland-vindue der er hvilken app, D6);
- **isolation** (proces, sandbox, netværkspolitik).

Motoren er et udskifteligt modul bag et snævert grænsesnit (start app, luk app, giv/fjern rettighed, ryd lager, rapportér tilstand):

```
Eira Web App Manager
   ├── Chromium   (standard: app-vinduer uden adressefelt og faner)
   ├── Firefox    (kun hvis relevant, se O-2)
   └── særlig runtime   (kun hvis en installation kræver det)
```

En **særlig runtime** er en motor, som installationen selv tilføjer for at opfylde et eksternt krav, fx en kundes Conditional Access med krav om en godkendt enhed, som på Linux kun Microsoft Edge opfylder. Den leveres ikke med EiraOS. Den installeres og konfigureres pr. installation via Fleet og får præcis de samme grænser som andre motorer (D2). Brugeren ser stadig en Eira-app, ikke en browser.

### D4 — 3D-universet er en model i Eira Core, ikke React-tilstand

Universets objekter, positioner, relationer og tilstand ejes af Eira Core (graphd) og eksponeres gennem en typed kontrakt. Det er det, der gør, at universet kan tegnes på forskellige måder (D5) uden at ændre model, apps eller Eira UI.

En flad 2D-tilstand, der er fuldt betjenbar med tastatur, er obligatorisk (GUI-plan §3). Den er også reservetilstanden, når der ikke er GPU.

### D5 — To spor for, hvem der tegner universet

| | **Spor A: universet navigerer** | **Spor B: compositoren tegner universet** |
|---|---|---|
| Hvem tegner | Eira UI (React/WebGL) | Egen compositor (realistisk Rust/Smithay) |
| App-vinduer | Compositoren viser appens vindue, når brugeren går ind i et objekt; universet viser ikoner og metadata | Vinduer er flader placeret i 3D |
| Forudsætning | `eira-labwc` som i dag | Egen compositor: input, flere skærme, XWayland, HiDPI, tilgængelighed |
| Sikkerhed | R-6.1 via `<privilegedInterfaces/>`, R-6.2 via labwc-patch | Compositoren håndhæver R-6.1/R-6.2 direkte efter GID; labwc-patch overflødig |

Et WebGL-univers i Eira UI kan ikke vise andre programmers vinduer, fordi ét program ikke må læse et andets vindue (R-6.1). Levende app-vinduer i 3D kræver derfor spor B.

**Besluttet af ejer (11. november 2026):** 1.0 leveres på spor A. Universet bruges til navigation og præsentation, apps er almindelige Wayland-vinduer, `graphd` ejer den autoritative model, og compositoren ejer vinduerne. Arkitekturen skal være klar til, at en senere egen compositor gør universet til sin egen scene.

### D6 — Compositoren ejer vinduer; Eira styrer dem gennem et snævert, betroet grænsesnit

Eira simulerer ikke vinduesstyring inde i en React-side (GUI-plan §5). Compositoren ejer vinduerne. Eira (Web App Manager og Eira UI) placerer, fokuserer og skifter mellem dem gennem et snævert grænsesnit, som compositoren kun giver til klienter med en bestemt effektiv GID, samme mekanisme som samtykkeagenten. Ingen klient får derfor de generelle privilegerede protokoller (R-6.1 gælder fortsat).

Vinduesidentitet bygger på, hvilken proces der ejer vinduet (compositoren kender klientens pid via SO_PEERCRED, og Web App Manager kender pid'erne på de processer, den starter), og ikke på `app_id`, som en klient selv vælger.

## Konsekvenser

### Identitet: `identityd` gøres udbyder-neutral (første skridt)

Koden var bundet til Microsoft Entra (`login.microsoftonline.com` skrevet direkte, `did:eira:entra.<oid>`, "Log ind med Entra"). Det rettes i [EIRA-IDENTITY 1.0](../../specs/EIRA-IDENTITY-1.0.md):

- udbyderen er konfiguration (`OIDC_PROVIDER_ID`, issuer, client id, endpoints via OIDC Discovery); der er ingen indbygget udbyder;
- identiteten er `did:eira:<provider-id>.<subjekt>`, og provider-id'et er et frit valgt konfigurationsnavn uden særlig betydning i koden. `entra` er ikke en kategori i modellen;
- et provider-id bindes til sin issuer ved første login, så en omkonfiguration ikke kan overtage identiteter;
- eksisterende `did:eira:entra.<oid>` bevares præcis af Entra-konfigurationen.

### Rækkefølge (besluttet af ejer)

1. `identityd`: vendor-neutral identitetsmodel
2. Web App Manager: kontrakt og abstraktion af browser-runtime
3. Chromium-distribution: konkret valg (O-1)
4. Spor B: egen compositor

### Øvrige

- **Ny komponent:** Eira Web App Manager med motor-grænsesnit, app-manifest og en profil-/lagermodel. Kontrakt skrives før kode (`specs/`).
- **Compositor:** grænsesnittet i D6 kommer oven i R-6.2-patchen i `eira-labwc`, eller i spor B's egen compositor.
- **graphd:** universets model (D4) får sin egen kontrakt.
- **Ikke ændret:** gaten, samtykkeagenten og rettighederne fra Fleet. Webapps' handlinger, der rører systemet (filer, kamera, notifikationer), går gennem gaten som alle andre handlinger.

## Åbne spørgsmål

- **O-1 Chromium-distribution.** *Udskudt af ejer:* vælges først, når Web App Manager-kontrakten og sikkerhedskravene til en browser-runtime er defineret. Ubuntu leverer Chromium som snap. Mulighederne er (a) snap med eksplicitte interfaces, (b) EiraOS' egen Chromium-build som deb eller indlejret via CEF, (c) upstream-binærer. Det afgør opdateringskadence, sandbox og hvor tæt Web App Manager kan styre profiler og rettigheder. Skal undersøges, før motoren bygges.
- **O-2 Firefox.** Firefox har ikke en app-tilstand som Chromiums app-vinduer, så en Firefox-motor vil i praksis vise et browservindue. Er den nødvendig i 1.0?
- ~~**O-3 Spor A/B.**~~ Besluttet: spor A i 1.0 (se D5).
- **O-4 Profiler.** Lager pr. app giver bedst isolation, men brugeren skal logge ind i hver app. Lager pr. identitetsudbyder giver single sign-on på tværs af apps fra samme udbyder. Forslag: pr. identitetsudbyder, med pr. app som tilvalg.
- **O-5 Links mellem apps.** Hvad sker der, når et link i app A peger på en oprindelse, som app B ejer, eller som ingen app ejer? Forslag: Web App Manager slår URL'en op i app-manifesterne. Ukendte oprindelser åbnes i en midlertidig, isoleret "ukendt side"-app, der aldrig får rettigheder.
- **O-6 Filer fra webapps.** Downloads og uploads skal ind i Eiras objektmodel og ikke i en skjult downloadmappe. Det kræver en kontrakt mellem Web App Manager og graphd.

## Ikke-mål

- Quickshell eller en anden QML/Qt-skal som systemlag.
- En leverandørs browser, login eller API som en del af EiraOS.
- Vinduesstyring simuleret inde i Eira UI.
