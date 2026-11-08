# EIRA Fleet Rights API 1.0

**Status:** Godkendt af ejer 8. november 2026. Normativ.
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
- **Tillidsgrænse: root er udenfor.** Tillidsroden på enheden er `/etc/eira/enrollment.json` (root-ejet) og den installerede kode under `/usr/lib/eira-os`. Den, der har root på enheden, kan skrive sit eget anker ind, ændre verifikatoren eller rette i cachen efter verifikationen. **På en enhed, hvor nogen har root, er resten af denne kontrakt ikke en sikkerhedsgrænse.** Den beskytter mod fejl, mod programmer der kører som brugeren og mod alt på netværket, ikke mod root. Derfor er "ingen stående lokal admin, kun midlertidig Fleet-grant" (ADR-0003) den kontrol, der bærer managed mode, og §6 punkt 1 er den vigtigste åbne beslutning.

## 3. Kald

### 3.1 `GET /v1/desired-state?rights_version=N`

- `rights_version` er versionen af enhedens aktive sæt. Udelades, når enheden intet sæt har.
- Har Fleet et nyere sæt, indeholder svaret `rights_set`: **base64url uden padding af de præcise signerede bytes**. Sættet indlejres aldrig som JSON-objekt, så ingen JSON-parser mellem udsteder og verifikator kan omordne, fjerne dubletter eller normalisere det.
- **Kun kanonisk base64url:** gen-kodning af de dekodede bytes skal give præcis den modtagne streng. Ellers kan to wire-strenge være samme sæt, og noget, der logger eller deduplikerer på strengen, ville se ét sæt som to. Længden er højst 1.398.102 tegn (1 MiB ukodet); grænsen udledes ét sted (`MAX_ENCODED_LENGTH`) og er bundet til OpenAPI-filen af en test.
- Intet nyere: `rights_set` udelades eller er `null`.
- Et svar, der ikke er et objekt, eller hvor `rights_set` ikke er en base64url-streng på højst 1 MiB dekodet, er et brud på kontrakten. Agenten behandler det som offline og ændrer intet.
- Fleet sender det samme sæt, indtil det har fået et `apply-result` for det, **undtagen** når resultatet var `rejected` (§3.2).

### 3.2 `POST /v1/report/apply-result`

Sendes efter hvert sæt, Fleet har leveret:

```json
{"kind": "rights_set", "device_id": "dev-0001", "rights_set_id": "…", "version": 42, "result": "applied", "reason": null}
```

- `result`: `applied`, `noop` (samme version og indhold) eller `rejected`.
- Ved `rejected` er `reason` en af kontraktens faste årsager (`contract.Reason`), og `rights_set_id` og `version` er `null`: felterne i et afvist sæt er ikke verificeret og må ikke meldes som fakta.
- Kan rapporten ikke leveres, er det ikke en fejl. Fleet sender sættet igen, og resultatet meldes igen.
- **`rejected` er endeligt for præcis de bytes.** Fleet gensender ikke et afvist sæt, markerer enheden som non-compliant og kræver operatørhandling; løsningen er altid et nyt sæt med ny version. Agenten husker afviste sæt (hash af bytes, højst 32), verificerer dem aldrig igen og melder dem kun igen, hvis den første rapport ikke nåede frem.

### 3.3 `POST /v1/heartbeat` (tilføjede felter)

```json
{"device_id": "dev-0001", "rights": {"rights_state": "active", "rights_version": 42, "rights_expires_at": "2026-11-21T11:00:00Z", "clock_rollback": false}}
```

- `rights_state` og `rights_reason` er den samme vurdering, som gaten bruger ved hver beslutning (`RightsCache.resolve`):

| `rights_state` | `rights_reason` | Betyder for IT |
|---|---|---|
| `active` | `null` | i orden |
| `expired` | `rights_expired` | enheden har ikke hørt fra Fleet længe nok |
| `missing` | `no_rights_set` | intet sæt endnu |
| `missing` | `awaiting_managed_set` | enrolled, venter på første managed-sæt (standardsættet gælder ikke længere) |
| `misconfigured` | `enrollment_malformed` | enrollment-filen er i stykker; skal rettes |
| `misconfigured` | `set_not_for_this_enrollment` | cachen har et sæt til en anden tenant/enhed (gen-enrolled) |
| `misconfigured` | `managed_set_without_enrollment` | enrollment er fjernet fra en managed enhed |

  `missing` skal sættes op; `misconfigured` er en fejl.
- `clock_rollback`: enheden har set sit ur gå tilbage forbi sit højvandsmærke. Fleet Console bør vise det.

## 4. Agentens runde (`sync_once`)

1. Spørg efter desired state med den aktive version.
2. Offline eller kontraktbrud → `offline`, intet ændres.
3. Intet nyere → `unchanged`, ingen rapport.
4. Et sæt, enheden allerede har afvist → `rejected_known`, ingen ny verifikation (§3.2).
5. Ellers verificér og installér atomart (RIGHTS-SET §4), og send `apply-result`.

**Interval** (`next_poll`): 15 minutter. Offline giver eksponentiel backoff op til 6 timer. Alle intervaller får ±20 % jitter, så enheder, der mistede Fleet samtidig, ikke vender tilbage samtidig. Et afvist sæt får ikke agenten til at spørge oftere.

## 5. Enrollment-filen

Enroll (Fleet Agent Protocol v0.1 §2) skal efterlade `/etc/eira/enrollment.json` (root, 0644):

```json
{
  "eira_enrollment": "1",
  "tenant_id": "kk",
  "device_id": "dev-0001",
  "fleet_url": "https://fleet.kk.example",
  "rights_anchors": {"kk-rights-2026": {"kind": "managed", "public_key": "<base64url Ed25519>", "not_after": "2027-12-31T00:00:00Z"}}
}
```

- Kun `managed`-ankre; mindst ét; hvert med `not_after`; `fleet_url` skal være `https://`.
- **`not_after`** vurderes i enhedens effektive tid ved verifikation (`anchor_expired`), aldrig mod sættets `issued_at`, som den, der har lækket en nøgle, kan tilbagedatere.
- **Findes filen ikke**, er enheden privat og bruger bundlens standardsæt.
- **Findes filen, men er den ugyldig**, er det en fejl, aldrig et fald tilbage til privat tilstand: standardsættet anvendes ikke, og enheden har ingen rettigheder, indtil enrollment er rettet.
- **Gaten vejer cachen mod enrollment ved hver beslutning**, ikke kun når et sæt anvendes (tabellen i §3.3). Et cachet standardsæt og `owner_admin` overlever derfor ikke enrollment, og en ødelagt eller fjernet enrollment-fil fjerner rettigheder, som cachen stadig har.
- Nul rettigheder betyder ikke en død maskine (RIGHTS-SET §5.1): gaten starter, `gate.capabilities` viser tilstand og årsag, audit kan læses, og netværk og agentens kontakt til Fleet er substrat, ikke gate-handlinger. Der er ingen nødkonvolut med rettigheder.
- Nøglerotation sker ved, at enroll-flowet leverer et nyt anker på samme måde, aldrig inde i et rettighedssæt.

## 6. Besluttet (8. november 2026)

1. **Tillidsrod mod root — besluttet: transporten bygges nu med §2's grænse; attestation bliver et senere krav.** At signere enrollment-filen med en TPM-forseglet nøgle eller lægge ankeret i TPM NVRAM gør ikke root til en grænse: root kan stadig ændre koden, der kontrollerer TPM-signaturen, eller rette i cachen efter verifikationen. Det giver først mening med en målt og uforanderlig kæde (Secure Boot, `dm-verity` på `/usr`, PCR-målinger) **og** remote attestation, hvor Fleet verificerer et TPM-quote ved enroll og heartbeat, før det udsteder sæt. Så flyttes kontrollen til Fleet, som kan opdage en ændret enhed. Beslutning: transporten bygges nu med §2's ærlige grænse; attestation lægges ind i enroll og heartbeat som et senere krav, sammen med en uforanderlig `/usr`.
2. **Nøglerotation — besluttet: rod- og driftsnøgler.** Reviewet foreslår et nyt ankersæt signeret af det forrige anker. Det løser planlagt rotation, men ikke kompromittering: den, der har lækket det gamle anker, kan selv signere sig et nyt. Beslutning: to niveauer. Enrollment fastgør tenantens **rod-nøgle** (offline, langlivet, i HSM), og roden udsteder kortlivede **driftsnøgler** med `not_after` som nøglecertifikater, leveret via desired state. En lækket driftsnøgle tilbagekaldes af roden uden re-enroll; kun en lækket rod kræver re-enroll.
3. **Åbent:** `eira-fleet-control` tager OpenAPI-filen og rettighedsvektorerne som en pinnet afhængighed og kører dem i sin CI (som RIGHTS-SET-kontrakten).
