# EIRA Identity 1.0 — vendor-neutral identitet fra OpenID Connect

**Status:** Udkast, implementeret i `app/auth/oidc.py` og `app/auth/login.py`. Bindende for identitetsformatet, når det er accepteret.
**Version:** 1.0 (11. november 2026)
**Grundlag:** [ADR-0004](../docs/decisions/ADR-0004-gui-arkitektur-vendor-neutral.md) D1 (ingen leverandørs login som OS-afhængighed), [ADR-0003](../docs/decisions/ADR-0003-rettigheder-fra-fleet.md) (identitet fra identityd, autorisation fra Fleet)
**Berører:** `identityd`, Gate (lag 4 og 6), RIGHTS-SET (principals), EDP og CONVERSATION (deltagere)

## 1. Udbyderen er konfiguration, ikke kode

`identityd` kender en identitetsudbyder alene gennem installationens konfiguration (`/etc/eira/eira.conf`):

| Variabel | Krav | Betydning |
|---|---|---|
| `OIDC_PROVIDER_ID` | påkrævet, `^[a-z][a-z0-9-]{0,31}$` | Installationens navn for udbyderen. Første led i alle identiteter fra den |
| `OIDC_PROVIDER_NAME` | valgfri | Navn vist i brugerfladen ("Log ind med …"). Uden den står der "Log ind" |
| `OIDC_ISSUER` | påkrævet, https | Udbyderens issuer. Tokenets `iss` skal være præcis denne |
| `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET` | client id påkrævet | Klientregistreringen hos udbyderen |
| `OIDC_SUBJECT_CLAIM` | standard `sub` | Claim med den stabile bruger-id |
| `OIDC_SUBJECT_CASE_INSENSITIVE` | standard nej | Ja kun, når subjektet er en GUID eller anden størrelse uden forskel på store og små bogstaver |
| `OIDC_GROUPS_CLAIM` | standard `groups` | Claim med gruppenavne |
| `OIDC_ORG_CLAIM` | valgfri | Claim med organisation/lejer |
| `OIDC_AUTHORIZATION_ENDPOINT`, `OIDC_TOKEN_ENDPOINT`, `OIDC_JWKS_URI` | valgfri, https | Tilsidesætter discovery |

Endpoints hentes ellers fra `{issuer}/.well-known/openid-configuration` (OpenID Connect Discovery 1.0). Dokumentets `issuer` skal være præcis den konfigurerede, og alle endpoints skal være https, ellers bruges intet fra det.

Der findes **ingen standardudbyder** og ingen udbyder-URL i koden. Mangler konfigurationen, er live-login utilgængeligt (`live_login_unavailable`). Den gamle Entra-indstilling `OIDC_TENANT_ID` uden `OIDC_ISSUER` afvises med en besked om den nye konfiguration.

Signaturer: kun RS256. En JWK uden `use` eller `alg` accepteres (RFC 7517 §4.2, §4.4); en JWK erklæret til andet bruges ikke.

## 2. Identitetsformat

```
did:eira:<provider-id>.<subjekt>
```

- `<provider-id>` er `OIDC_PROVIDER_ID`. Det indeholder ikke punktum, så punktummet afgrænser det entydigt.
- `<subjekt>` dannes af værdien i `OIDC_SUBJECT_CLAIM`:
  1. Med `OIDC_SUBJECT_CASE_INSENSITIVE` gøres den til små bogstaver.
  2. Er den nu `^[a-z0-9-]{1,64}$`, bruges den som den er.
  3. Ellers bruges `_h` + base32(SHA-256(værdi)), små bogstaver uden padding (54 tegn).

OIDC-subjekter skelner mellem store og små bogstaver og kan indeholde vilkårlige tegn, mens EDP's identiteter er `[a-z0-9_.-]`. Et rå subjekt indeholder aldrig `_`, og en hashet form begynder altid med `_h`, så de to former kan ikke falde sammen. Den længste identitet (32 + 1 + 54 tegn efter `did:eira:`) holder sig inden for EDP's 100 tegn.

Identiteten er ikke en e-mail. E-mailen er visningsnavn og `actor_id`, ikke gatens identitet.

## 3. En udbyder er bundet til sin issuer

Første gang et `provider-id` bruges til et login, gemmes parret (`provider-id`, `issuer`) i `oidc_provider_bindings`. Et senere login, hvor samme `provider-id` er konfigureret med en anden issuer, afvises (`provider_issuer_changed`), før der oprettes en session.

**Hvorfor:** Rettighedssæt fra Fleet navngiver identiteter. Hvis `entra` blev peget på en anden issuer, ville dennes subjekter blive til de gamle identiteter, og en fremmed udbyder kunne overtage brugeres rettigheder. At skifte en udbyders issuer er derfor et eksplicit administrativt skridt (åbent: O-1).

## 4. Eksisterende Entra-identiteter

Installationer, der bruger Microsoft Entra, konfigurerer:

```
OIDC_PROVIDER_ID=entra
OIDC_ISSUER=https://login.microsoftonline.com/<tenant-id>/v2.0
OIDC_SUBJECT_CLAIM=oid
OIDC_SUBJECT_CASE_INSENSITIVE=true
OIDC_ORG_CLAIM=tid
```

Det giver præcis de identiteter, den tidligere kode gav (`did:eira:entra.<oid>` med `oid` i små bogstaver), så rettighedssæt og gemte deltagere fortsat gælder. Rækkefølgen for e-mail (`preferred_username`, `email`, `upn`) er bevaret, så `actor_id` ikke ændres. `entra` er et konfigureret provider-id som alle andre og har ingen særlig betydning i koden.

Multi-tenant-issueren (`common`) understøttes ikke: tokenets `iss` skal matche én bestemt issuer.

## 5. Åbne spørgsmål

- **O-1** Hvordan en administrator bevidst flytter et provider-id til en ny issuer (fx ved tenant-migrering), og om det skal gå via Fleet. Indtil da kræver det, at rækken i `oidc_provider_bindings` fjernes manuelt.
- **O-2** Flere udbydere på samme maskine (fx personale og elever). Formatet tillader det; konfigurationen har i dag én.
- **O-3** Login uden e-mail-claim. I dag kræves en e-mail som `actor_id`.
