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

## Åbne spørgsmål til ejer

1. **Identitet over for rettighed.** Er Entra og `identityd` kilde til *hvem* brugeren er og *hvilke grupper* vedkommende er i, mens Fleet afgør, hvad grupperne må? Fleet Console v0.1 siger, at AD-grupper kommer fra Entra.
2. **Ikke-administrerede maskiner.** Hvor kommer rettighederne fra på en pc uden Fleet, fx en enkeltbruger eller en privat installation? Mulighed: et signeret standardsæt fra Fleet i bundlen, så kilden stadig er Fleet og ikke maskinen.
