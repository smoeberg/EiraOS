# EIRA Fleet Rights API 1.0

**Status:** Udkast til ejerens godkendelse.
**Version:** 1.0
**Defineret af:** `eira-os`. Fleet implementerer serversiden; eira-os afhænger ikke af, hvordan Fleet er bygget.
**Grundlag:** [EIRA-RIGHTS-SET-1.1](EIRA-RIGHTS-SET-1.0.md) (sættet), [ADR-0003](../docs/decisions/ADR-0003-rettigheder-fra-fleet.md), Fleet Agent Protocol v0.1 (transport og enroll).

## 1. Formål og afgrænsning

Denne kontrakt er rettighedsdelen af grænsen mellem endpoint og Fleet: hvordan et rettighedssæt kommer til enheden, hvordan resultatet meldes tilbage, og hvad enroll skal efterlade på enheden. Den er defineret fra endpointets side, så eira-os kan bygges og testes uden Fleet.

| Fil | Rolle |
|---|---|
| `specs/EIRA-FLEET-RIGHTS-API-1.0.md` | normativ tekst (dette dokument) |
| `specs/eira-fleet-rights-api-1.0.openapi.json` | OpenAPI 3.1, som Fleet implementerer mod |
| `app/rights/fleet_api.py` | beskeder, parsere og `FleetRightsClient`-grænsefladen |
| `app/rights/agent.py` | `sync_once` og `heartbeat_fields` |
| `tests/test_fleet_rights_api.py` | en falsk Fleet (korrekt, offline og fjendtlig) og tests af, at OpenAPI-filen og koden er enige |

**Ikke her:** HTTPS, mTLS-enhedscertifikat, Fleet URL pinning, selve enroll-flowet og alt andet i desired state (bundles, kommandoer, vedligeholdelsesvinduer). Det er Fleet Agent Protocol v0.1. Denne kontrakt tilføjer kun felter til tre af dens endpoints.

## 2. Tillid

- **Svar fra Fleet er data, ikke rettigheder.** Et sæt bliver først til rettigheder, når `contract.verify` har godkendt det med et anker fra enrollment. mTLS beviser, at svaret kommer fra Fleet; signaturen beviser, at tenanten har udstedt sættet. Begge kræves.
- **Ankre fastgøres ved enroll** (§5), ikke i rettighedssæt og ikke i desired state. Et sæt signeret med en anden nøgle afvises (`unknown_key_id` eller `bad_signature`).
- **Fleet utilgængelig eller i strid med kontrakten** ændrer aldrig det aktive sæt. Offline er en normal tilstand (RIGHTS-SET §5.1); agentens kontakt til Fleet afhænger aldrig af sættet.

## 3. Kald

### 3.1 `GET /v1/desired-state?rights_version=N`

- `rights_version` er versionen af enhedens aktive sæt. Udelades, når enheden intet sæt har.
- Har Fleet et nyere sæt, indeholder svaret `rights_set`: **base64url uden padding af de præcise signerede bytes**. Sættet indlejres aldrig som JSON-objekt, så ingen JSON-parser mellem udsteder og verifikator kan omordne, fjerne dubletter eller normalisere det.
- Intet nyere: `rights_set` udelades eller er `null`.
- Et svar, der ikke er et objekt, eller hvor `rights_set` ikke er en base64url-streng på højst 1 MiB dekodet, er et brud på kontrakten. Agenten behandler det som offline og ændrer intet.
- Fleet sender det samme sæt, indtil det har fået et `apply-result` for det.

### 3.2 `POST /v1/report/apply-result`

Sendes efter hvert sæt, Fleet har leveret:

```json
{"kind": "rights_set", "device_id": "dev-0001", "rights_set_id": "…", "version": 42, "result": "applied", "reason": null}
```

- `result`: `applied`, `noop` (samme version og indhold) eller `rejected`.
- Ved `rejected` er `reason` en af kontraktens faste årsager (`contract.Reason`), og `rights_set_id` og `version` er `null`: felterne i et afvist sæt er ikke verificeret og må ikke meldes som fakta.
- Kan rapporten ikke leveres, er det ikke en fejl. Fleet sender sættet igen, og resultatet meldes igen.

### 3.3 `POST /v1/heartbeat` (tilføjede felter)

```json
{"device_id": "dev-0001", "rights": {"rights_state": "active", "rights_version": 42, "rights_expires_at": "2026-11-21T11:00:00Z", "clock_rollback": false}}
```

- `rights_state`: `active`, `expired` eller `missing`, vurderet i effektiv tid (RIGHTS-SET §4.1).
- `clock_rollback`: enheden har set sit ur gå tilbage forbi sit højvandsmærke. Fleet Console bør vise det.

## 4. Agentens runde (`sync_once`)

1. Spørg efter desired state med den aktive version.
2. Offline eller kontraktbrud → `offline`, intet ændres.
3. Intet nyere → `unchanged`, ingen rapport.
4. Ellers verificér og installér atomart (RIGHTS-SET §4), og send `apply-result`.

## 5. Enrollment-filen

Enroll (Fleet Agent Protocol v0.1 §2) skal efterlade `/etc/eira/enrollment.json` (root, 0644):

```json
{
  "eira_enrollment": "1",
  "tenant_id": "kk",
  "device_id": "dev-0001",
  "fleet_url": "https://fleet.kk.example",
  "rights_anchors": {"kk-rights-2026": {"kind": "managed", "public_key": "<base64url Ed25519>"}}
}
```

- Kun `managed`-ankre; mindst ét; `fleet_url` skal være `https://`.
- **Findes filen ikke**, er enheden privat og bruger bundlens standardsæt.
- **Findes filen, men er den ugyldig**, er det en fejl, aldrig et fald tilbage til privat tilstand: standardsættet anvendes ikke, og enheden har ingen rettigheder, indtil enrollment er rettet.
- Nøglerotation sker ved, at enroll-flowet leverer et nyt anker på samme måde, aldrig inde i et rettighedssæt.

## 6. Åbent til ejer

1. Godkendelse af kontrakten.
2. `eira-fleet-control` tager OpenAPI-filen og rettighedsvektorerne som en pinnet afhængighed og kører dem i sin CI (som RIGHTS-SET-kontrakten).
3. Transporten (HTTPS + mTLS, `FleetRightsClient` over netværket) bygges, når enroll-flowet findes. Indtil da findes kun grænsefladen og den falske Fleet i testene; intet på enheden taler med en rigtig Fleet.
