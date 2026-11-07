# ADR-0003 — Alle rettigheder sættes via Fleet's rettigheds-API

**Status:** Besluttet af ejer (Søren Møberg), 7. november 2026
**Gælder for:** Gate Kernel (lag 4 og 6), `eira-governance-agent`, `identityd`, `fleetd`, Fleet Agent Protocol, OS-substratet (bundle)
**Relateret:** [ADR-0002](ADR-0002-gate-to-handlingsfamilier.md), [GATE-KERNEL bilag A og B](../../specs/GATE-KERNEL-1.0.md), Fleet Agent Protocol v0.1 og Enterprise Portal / Fleet Console v0.1 (i `eira-fleet-control`)

## Normativ regel

> **Alle rettigheder i EiraOS sættes via Fleet's rettigheds-API. Endpointet håndhæver dem og er aldrig autoritativ kilde til rettigheder.**

| | Regel |
|---|---|
| **Kilde til rettigheder** | Fleet: skabelon og desired state |
| **Transport** | Rettigheds-API: Fleet → `eira-governance-agent` → lokal runtime |
| **EiraOS' rolle** | Læse, cache og håndhæve. EiraOS definerer eller udvider aldrig rettigheder på egen hånd |
| **Lokal ændring** | Er aldrig en autoritativ kilde. Fail closed, hvis desired state mangler eller er ugyldig |

Der findes ingen skjulte rettigheder i endpoint-kode, i en lokal admin-toggle eller i ad hoc-konfiguration, der kan tilsidesætte Fleet.

```
Fleet Control
    └── Rettigheds-API  (skabelon → eksplicitte grants/denies)
            └── desired state (signeret, versioneret)
                    └── eira-governance-agent
                            └── EiraOS runtime håndhæver (Gate lag 4 og 6)
```

- Grant og deny sker kun via API'et.
- En skabelon er en pakke af rettigheder og logik. Den erstatter ikke API'et.
- Audit kan altid pege tilbage på, hvilken skabelon, hvilket API-kald og hvilken version en rettighed kom fra.

## Nuancer (normative)

1. **Offline.** Agenten må bruge det sidst kendte, signerede rettighedssæt inden for dets TTL. Den må ikke opfinde nye rettigheder offline.
2. **Least privilege ved tvivl.** Er desired state ugyldig, udløbet eller mangler den, gælder den minimale rettighedsmængde (eller lockout efter policy).
3. **Step-up og midlertidige rettigheder** gives også via API'et som et eksplicit, tidsbegrænset grant fra Fleet, ikke via lokale genveje.
4. **OS-substratet (Ubuntu).** Systemrettigheder som sudo, pakker og polkit styres også via bundle og desired state. I managed mode findes ingen manuel lokal administration uden om Fleet.

## Konsekvenser for det eksisterende

**Gate Kernel:**
- `gate_grants` og `gate_members` er en *cache* af Fleet's signerede rettighedssæt, ikke en kilde. Kun `eira-governance-agent` må skrive dem, og kun ved at anvende et verificeret sæt:
  - signaturen skal verificeres,
  - tenant og device skal matche,
  - versionen skal være monoton,
  - TTL'en skal være overholdt.
- Der må ikke findes en IPC-metode eller en admin-vej, der tildeler en rettighed lokalt. Testenes direkte `store.grant_right(...)` er testopsætning, ikke en produktionsvej.
- Hver gate-beslutning skal i audit-loggen kunne henvise til rettighedssættets version, skabelon og API-kald.
- Udløbet eller manglende sæt betyder ingen grants og dermed `REJECT` (lag 6). Det gør gaten allerede i dag, fordi intet er provisioneret.

**Rettelse af tidligere plan:** GATE-KERNEL bilag A punkt 4 og bilag B sagde, at `identityd` skulle provisionere rettigheder. Det er erstattet af denne ADR. `identityd` er kilde til **identitet** (hvem brugeren er, session og assurance), ikke til **rettigheder** (hvad brugeren må).

**OS-substratet:** Polkit-reglen `50-eira-power.rules` (Gate 1.1) giver servicebrugeren `eira` lov til at bede logind om strømhandlinger. Den ligger i pakken og dermed i bundlen, som Fleet godkender. Det er i overensstemmelse med punkt 4. *Om brugeren må* slukke maskinen, afgøres stadig af Fleet-rettigheden `system:power.request_action` på `device:local`.

**Fleet Agent Protocol:** Desired state (v0.1 §5) har i dag ingen rettighedssektion, og der findes ikke et rettigheds-API. Begge skal specificeres i `eira-fleet-control` (Agent Protocol v0.2): grants, denies, subjekter, scope, `version`, `issued_at`, `expires_at` (TTL), skabelon-reference, API-kalds-id og signatur.

## Identitet og autorisation (besluttet af ejer, 7. november 2026)

> Identity (Entra/identityd) er kilde til identitet og gruppemedlemskab.
> Fleet er kilde til autorisation: mapping fra identitet/grupper → skabelon → konkrete rettigheder.
> EiraOS håndhæver; det udleder ikke rettigheder selv fra grupper.

| Lag | Ansvar | Eksempel |
|---|---|---|
| **Entra / identityd** | *Hvem* brugeren er, og *hvilke grupper* vedkommende tilhører | `sub`, e-mail, `OU=Skole`, `group=lærere` |
| **Fleet (rettigheds-API)** | *Hvad* grupperne eller skabelonen må | intents, adapters, audit-niveau, step-up-krav |

```
Login (Entra/OIDC)
    → identityd: authenticated principal + groups
        → Fleet/rettigheds-API: groups + device + tenant → skabelon + grants
            → agent: desired rights
                → EiraOS: enforce
```

- **Grupper giver ingen rettigheder i sig selv.** Autorisation opstår først, når Fleet, eller den signerede desired state, mapper grupperne til en skabelon. Gaten må derfor aldrig oversætte en gruppe til en rettighed selv.
- **Lokale og demo-konti uden IdP følger samme regel** via en skabelon. Man bliver ikke administrator af at være lokal bruger.

## Maskiner uden aktiv Fleet-forbindelse (besluttet af ejer, 7. november 2026)

> På maskiner uden aktiv Fleet-forbindelse kommer rettigheder fra et **signeret standardsæt**, der er udstedt af Fleet og indlejret i bundlen (eller hentet ved sidste kendte kontakt). Maskinen er aldrig autoritativ kilde til rettigheder.

| Situation | Kilde til rettigheder |
|---|---|
| Managed og online | Fleet rettigheds-API (live desired state) |
| Managed og offline | Sidste signerede desired state (TTL, fail closed ved udløb) |
| Unmanaged eller privat | Signeret **default-skabelon** i bundlen, udstedt af Fleet ved build/release |

**Krav til standardsættet:**
- Det er signeret af Fleet's release-nøgle, samme tillidsanker som bundles.
- Det er eksplicit og minimalt (least privilege), fx skabelonen `personal` eller `unmanaged`.
- Det er versioneret og kan ikke udvides lokalt.
- Ved en senere enroll erstattes det af tenantens skabelon fra Fleet.

Kilden er derfor **altid** Fleet, enten live eller forudsigneret. Endpointet opfinder ikke rettigheder.

## To rettighedslag, én kilde (besluttet af ejer, 7. november 2026)

> **To rettighedslag, én kilde.**
> (1) Ubuntu-substratrettigheder (konti, sudo, AppArmor, pakker, …) defineres i Fleet som desired state og anvendes af agenten på OS-niveau.
> (2) EiraOS-rettigheder (intents, skabelon-logik, assurance, adapters) defineres via Fleet's rettigheds-API/skabeloner og håndhæves af EiraOS.
> Ingen af lagene har endpointet som autoritativ kilde.

| Lag | Eksempler | Defineres i | Anvendes af | Håndhæves af |
|---|---|---|---|---|
| Ubuntu-substrat | konti, grupper, sudo, fil-rettigheder, AppArmor, polkit, systemd-units, pakker, diskkryptering | Fleet desired state og bundle | `eira-governance-agent` via Policy Compiler (Glue Layer v0.1: compile → validate → dry-run → snapshot → apply → probe → rollback) | Kernen og Ubuntu |
| EiraOS | intents, EDP- og systemhandlinger, adapters, assurance og step-up, audit-niveau, skabeloner | Fleet rettigheds-API (`specs/EIRA-RIGHTS-SET-1.0.md`) | `eira-governance-agent` i gatens cache | Gate (lag 4 og 6) |

EiraOS redigerer ikke Ubuntu-rettigheder på egen hånd. Det anvender Ubuntu-desired state fra Fleet og håndhæver sit eget lag.

### Forholdet mellem lagene (normativt)

1. **Substratet beskytter Eira-laget.** Eira-rettigheder virker kun, hvis brugeren og brugerens programmer ikke kan ændre gatens tilstand. Det gælder rettighedscache, samtykker, handlinger og audit-log. Det er en *substrat*-rettighed:
   - Desktop-brugeren må have adgang til daemons' sockets.
   - Desktop-brugeren må aldrig have skriveadgang til Eira-daemons' data (`/data`, `/var/lib/eira`).
2. **Substratet må ikke åbne en vej uden om gaten.**
   - I managed mode har desktop-brugeren ingen sudo. Administratoradgang gives kun via Fleet: et midlertidigt, auditeret grant til en navngiven IT-konto, aldrig til Explorer-brugeren.
   - Med root kan man ændre alt, og det kan intet Eira-lag forhindre. Derfor er "ingen lokal root uden om Fleet" et substratkrav.
3. **Eira-laget kan ikke give mere, end substratet tillader.** Et grant til `system:power.request_action` virker kun, fordi bundlen giver servicebrugeren `eira` netop de polkit-handlinger. Hverken bundlen eller polkit giver *brugeren* noget.
4. **Ét begreb hører til ét lag.**
   - "Må denne session godkende budgettet?" hører til Eira-laget.
   - "Må `intentd` tale med logind?" hører til substratet.
   - Et begreb må ikke styres to steder.

### Fundet ved gennemgangen (skal rettes)

- **Explorer-brugeren kan skrive gatens database.** `eira-firstboot` lægger brugeren i gruppen `eira` for at give adgang til sockets. Men `/data` er `eira:eira 0770`, og daemons' `UMask=0117` giver databasefilen `0660 eira:eira`. Brugeren og alle brugerens programmer kan derfor skrive direkte i `gate_grants`, `gate_consents` og `gate_actions`. Det bryder punkt 1. Rettelsen er at adskille grupperne: `eira-clients` får adgang til sockets og IPC-token, mens `eira` forbliver daemons' egen gruppe, som brugeren ikke er medlem af.
- **Installerens bruger er sudo-administrator** (Ubuntu-standard). Det er forkert i managed mode (punkt 2). Det skal afgøres, hvordan en ikke-administreret, privat maskine skal håndteres (se åbent punkt).

### Åbent punkt til ejer

**Privat maskine og root.** På en privat, ikke-administreret pc er ejeren typisk administrator af sin egen Ubuntu. Med sudo kan ejeren ændre alt, også Eira-laget. Det kan og skal EiraOS ikke forhindre på ejerens egen maskine. Men så er Eira-håndhævelsen der kun en beskyttelse mod fejl og mod programmer, der kører som brugeren, ikke mod ejeren selv. Skal installeren i privat tilstand oprette:
- **(a)** en separat administrator-konto og en Explorer-bruger uden sudo, eller
- **(b)** én konto med sudo, hvor begrænsningen beskrives ærligt?

## Implementeringsrækkefølge (afledt)

1. **Specificér rettighedssættets format** som et fælles kontraktdokument mellem `eira-os` og `eira-fleet-control`. Formatet består af:
   - grants og denies med subjekt (gruppe eller principal), scope og handlingsnøgle (fx `edp:commitment_proposed`, `system:power.request_action`),
   - `version`, `issued_at` og `expires_at`,
   - skabelon, API-kalds-id, tenant og device,
   - Ed25519-signatur.
   Signaturen genbruger Phase 0-signaturkontrakten med eget domæne.
2. **Endpoint-siden:** `eira-governance-agent` verificerer og anvender sættet i gatens cache. Hvis signatur, tenant/device, version eller TTL ikke holder, anvendes intet (fail closed).
3. **Gaten løser rettigheder op** gennem principalens grupper fra `identityd` og rettighedssættets grants. Audit-loggen registrerer rettighedssættets version.
4. **Bundlen får det signerede default-sæt.**
