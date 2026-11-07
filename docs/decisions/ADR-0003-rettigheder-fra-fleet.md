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
