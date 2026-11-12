# EIRA Fleet Rights API 1.0

**Status:** Godkendt af ejer 8. november 2026. Normativ.
**Version:** 1.3 (8. november 2026: 1.1 rod- og driftsnøgler og enrollment version 2; 1.2 enroll, §8, og sync-planlægning, §7. 11. november 2026: 1.3 enhedsnøglen dannes i TPM'en og kan ikke eksporteres; managed kræver TPM 2.0, §8 og §6 pkt. 1a)
**Defineret af:** `eira-os`. Fleet implementerer serversiden; eira-os afhænger ikke af, hvordan Fleet er bygget.
**Grundlag:** [EIRA-RIGHTS-SET-1.3](EIRA-RIGHTS-SET-1.0.md) (sættet), [ADR-0003](../docs/decisions/ADR-0003-rettigheder-fra-fleet.md), Fleet Agent Protocol v0.1 (transport og enroll).

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
- **Rodnøgler fastgøres ved enroll** (§5), aldrig i rettighedssæt eller desired state. Driftsnøgler, der signerer sæt, kommer i desired state, men kun som certifikater signeret af en rod (RIGHTS-SET §3.1). Et sæt signeret med en anden nøgle afvises (`unknown_key_id`, `bad_signature` eller `key_revoked`).
- **Fleet utilgængelig eller i strid med kontrakten** ændrer aldrig det aktive sæt. Offline er en normal tilstand (RIGHTS-SET §5.1); agentens kontakt til Fleet afhænger aldrig af sættet.
- **Tillidsgrænse: root er udenfor.** Tillidsroden på enheden er `/etc/eira/enrollment.json` (root-ejet) og den installerede kode under `/usr/lib/eira-os`. Den, der har root på enheden, kan skrive sit eget anker ind, ændre verifikatoren eller rette i cachen efter verifikationen. **På en enhed, hvor nogen har root, er resten af denne kontrakt ikke en sikkerhedsgrænse.** Den beskytter mod fejl, mod programmer der kører som brugeren og mod alt på netværket, ikke mod root. Derfor er "ingen stående lokal admin, kun midlertidig Fleet-grant" (ADR-0003) den kontrol, der bærer managed mode, og §6 punkt 1 er den vigtigste åbne beslutning.

## 3. Kald

### 3.1 `GET /v1/desired-state?rights_version=N`

- `rights_version` er versionen af enhedens aktive sæt. Udelades, når enheden intet sæt har.
- Har Fleet et nyere sæt, indeholder svaret `rights_set`: **base64url uden padding af de præcise signerede bytes**. Sættet indlejres aldrig som JSON-objekt, så ingen JSON-parser mellem udsteder og verifikator kan omordne, fjerne dubletter eller normalisere det.
- **Kun kanonisk base64url:** gen-kodning af de dekodede bytes skal give præcis den modtagne streng. Ellers kan to wire-strenge være samme sæt, og noget, der logger eller deduplikerer på strengen, ville se ét sæt som to. Længden er højst 1.398.102 tegn (1 MiB ukodet); grænsen udledes ét sted (`MAX_ENCODED_LENGTH`) og er bundet til OpenAPI-filen af en test.
- Intet nyere: `rights_set` udelades eller er `null`.
- `rights_keys`: rodsignerede certifikater for tenantens driftsnøgler, altid den fulde aktuelle liste (højst 16). Udeladt = uændret.
- `rights_revocations`: den rodsignerede tilbagekaldelsesliste. Kun en nyere (højere sekvens, kun voksende) erstatter den gemte.
- Agenten behandler nøgler **før** sættet i samme svar: en nyligt certificeret nøgle virker straks, og en tilbagekaldelse gælder, før noget sæt ses på. Et ugyldigt certifikat bliver aldrig et anker, så en dårlig nøgleliste kan kun fjerne tillid, aldrig give den.
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
| `missing` | `signing_key_revoked` | nøglen bag det aktive sæt er tilbagekaldt; venter på et sæt signeret med en ny |
| `missing` | `signing_key_expired` | nøglen bag det aktive sæt er udløbet |

  `missing` skal sættes op; `misconfigured` er en fejl.
- `audit` (valgfri, OpenAPI 1.3): gatens seneste audit-anker `{seq, head, at}` (GATE-KERNEL bilag A pkt. 2). Fleet gemmer hvert par pr. enhed, alarmerer, hvis `seq` falder eller et kendt head ændres, og kan eksportere dem til `eira-audit-verify --anchors`.
- `audit_seal` (valgfri, OpenAPI 1.4): journalens FSS-verifikationsnøgle `{verify_key, interval, machine_id}` (GATE-KERNEL bilag A pkt. 2). Sendes kun, mens nøglen venter på overdragelse, og slettes på enheden efter et 2xx-svar. Nøglen kan genskabe forseglingsnøglerne: Fleet skal opbevare den som en hemmelighed og kun bruge den til at verificere enhedens journal.
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
  "eira_enrollment": "2",
  "tenant_id": "kk",
  "device_id": "dev-0001",
  "fleet_url": "https://fleet.kk.example",
  "rights_roots": {"kk-root-2026": {"public_key": "<base64url Ed25519>", "not_after": "2031-01-01T00:00:00Z"}}
}
```

- `rights_roots`: mindst én rod, hver med `not_after`; `fleet_url` skal være `https://`. Version 1 (`rights_anchors`) afvises.
- En rod signerer aldrig sæt. Den certificerer driftsnøgler og signerer tilbagekaldelseslisten (RIGHTS-SET §3.1). Skift af rod kræver re-enroll.
- `not_after` vurderes i enhedens effektive tid ved verifikation, aldrig mod et dokuments egne tidsfelter, som den, der har lækket en nøgle, kan tilbagedatere.
- **Findes filen ikke**, er enheden privat og bruger bundlens standardsæt.
- **Findes filen, men er den ugyldig**, er det en fejl, aldrig et fald tilbage til privat tilstand: standardsættet anvendes ikke, og enheden har ingen rettigheder, indtil enrollment er rettet.
- **Gaten vejer cachen mod enrollment ved hver beslutning**, ikke kun når et sæt anvendes (tabellen i §3.3). Et cachet standardsæt og `owner_admin` overlever derfor ikke enrollment, og en ødelagt eller fjernet enrollment-fil fjerner rettigheder, som cachen stadig har.
- Nul rettigheder betyder ikke en død maskine (RIGHTS-SET §5.1): gaten starter, `gate.capabilities` viser tilstand og årsag, audit kan læses, og netværk og agentens kontakt til Fleet er substrat, ikke gate-handlinger. Der er ingen nødkonvolut med rettigheder.
- Nøglerotation sker ved, at enroll-flowet leverer et nyt anker på samme måde, aldrig inde i et rettighedssæt.

## 7. Transport (`app/rights/transport.py`)

`HttpsFleetRightsClient` implementerer `FleetRightsClient` med standardbiblioteket (`ssl`, `http.client`), så pakken ikke får nye afhængigheder. Transporten sikrer forbindelsen; om et sæt må bruges, afgør stadig `contract.verify`.

| Krav | Sådan |
|---|---|
| Kun den enrollede Fleet | Adressen kommer fra `fleet_url` i enrollment. Værtsnavnet skal passe til serverens certifikat. Omdirigeringer følges aldrig. |
| Kun Fleets CA | Systemets tillidslager indlæses ikke, så en offentlig CA kan ikke gå i god for en falsk Fleet. |
| mTLS | Enhedscertifikatet fra enroll; TLS 1.2 eller nyere. Signaturen i håndtrykket laves af TPM'en via OpenSSL-provideren `tpm2-openssl` (§8). |
| Tenant-token | `Authorization: Bearer`, når enroll har efterladt et token. Et token med linjeskift afvises. |
| Afgrænset | 15 s timeout og højst 4 MiB svar. Uden for API'et → `ProtocolViolation`; utilgængelig → `FleetError` (offline). |

**Filer, som enroll efterlader** (`/etc/eira/fleet/`):

| Fil | Ejer og rettigheder | Indhold |
|---|---|---|
| `ca.pem` | root, 0644 | Fleets server-CA, den eneste betroede rod |
| `device.crt` | root, 0644 | enhedscertifikatet |
| `device.key` | root:eira, 0640 | TPM'ens indpakkede nøgleblob (TSS2) for enhedens P-256-nøgle. Kan kun bruges med denne enheds TPM; den private nøgle findes ikke i filen (§8) |
| `tenant.token` | root:eira, 0640 | tenant-token (valgfri) |

**Kommando:** `eira-rights-apply sync` kører én runde (§4) og derefter et heartbeat. Exit: 0 i orden, 1 sæt afvist, 2 ikke enrolled eller fejlkonfigureret, 3 offline.

**Planlægning:** `eira-rights-sync.timer` starter `eira-rights-sync.service` 2 minutter efter boot og derefter hvert 15. minut med op til 3 minutters tilfældig forsinkelse. Unit'en kører kun på en enrolled enhed (`ConditionPathExists=/etc/eira/enrollment.json`), som brugeren `eira`, med samme hærdning som daemonerne, skrivning kun til `/data/rights` og sin egen AppArmor-profil (læser Fleet-filerne, skriver dem aldrig). Efter to eller flere runder offline springer agenten timer-ticks over efter `next_poll` (op til 6 timer). Exit 1 og 3 er normale udfald, ikke fejl.

## 8. Enroll (`eira-enroll`, `app/rights/enroll.py`)

**Invitationen** gives til enheden af IT ad deres egen kanal (USB, provisioneringsimage). Den er ikke en API-besked:

```json
{"eira_enroll_invite": "1", "fleet_url": "https://fleet.kk.example", "ca": "<PEM: Fleets server-CA>",
 "enroll_token": "<engangs-token>", "expires_at": "2026-11-15T00:00:00Z"}
```

**Forløbet** (`eira-enroll INVITATION.json`, som root):

1. Enheden danner sit nøglepar **i TPM'en**: ECDSA P-256 med `fixedTPM` og `fixedParent`, så nøglen ikke kan eksporteres eller dubleres. Kun TPM'ens indpakkede blob skrives til disk (`device.key`), og kun en CSR sendes. Har enheden ingen TPM 2.0, afbrydes enroll med exit 2 og beskeden, at managed kræver TPM 2.0 (§6 pkt. 1a); intet skrives.
2. `POST /v1/enroll` over TLS, der kun stoler på invitationens CA (endnu ingen klientcertifikat). Med sendes token, CSR, `machine_hash` (sha256 af `/etc/machine-id` med præfiks, ikke det rå id) og værtsnavn.
3. Svaret kontrolleres, før noget skrives: samme `fleet_url` som invitationen; et enhedscertifikat udstedt af invitationens CA til *denne* nøgle, gyldigt nu og til klientgodkendelse; gyldige `rights_roots`; et token uden linjeskift.
4. Filerne i `/etc/eira/fleet/` skrives først, hver atomart og med rettighederne fra §7; `/etc/eira/enrollment.json` skrives **til sidst**. Det er den fil, der gør enheden managed, så et nedbrud undervejs efterlader en privat enhed, aldrig en halvt managed.
5. En første sync startes med det samme.

En enhed, der allerede er enrolled, afvises: gen-enroll er en bevidst handling (fjern enrollment først). Fra næste beslutning gælder standardsættet og `owner_admin` ikke længere (§5, `awaiting_managed_set`).

## 6. Besluttet (8. november 2026)

1. **Tillidsrod mod root — besluttet: transporten bygges nu med §2's grænse; attestation bliver et senere krav.** At signere enrollment-filen med en TPM-forseglet nøgle eller lægge ankeret i TPM NVRAM gør ikke root til en grænse: root kan stadig ændre koden, der kontrollerer TPM-signaturen, eller rette i cachen efter verifikationen. Det giver først mening med en målt og uforanderlig kæde (Secure Boot, `dm-verity` på `/usr`, PCR-målinger) **og** remote attestation, hvor Fleet verificerer et TPM-quote ved enroll og heartbeat, før det udsteder sæt. Så flyttes kontrollen til Fleet, som kan opdage en ændret enhed. Beslutning: transporten bygges nu med §2's ærlige grænse; attestation lægges ind i enroll og heartbeat som et senere krav, sammen med en uforanderlig `/usr`.
1a. **Klonbeskyttelse — besluttet 11. november 2026, i 1.0.** Pkt. 1 handler om root på den kørende enhed. Kloning er et andet angreb: disken kopieres og startes på anden hardware. Det kræver hverken målt opstart eller attestation at lukke: enhedsnøglen dannes i TPM'en og kan ikke eksporteres (§8 trin 1), så en kopi af disken kan ikke gennemføre mTLS-håndtrykket og får intet nyt fra Fleet. Managed kræver derfor TPM 2.0. Det gør **ikke** root til en grænse; root kan bruge nøglen gennem TPM'en, så længe enheden kører, og pkt. 1 gælder uændret. Følge for `eira-fleetd`: dets egen enhedsgodkendelse (token og nøgle sammenlignet som tekst) er ikke klonsikker og må kun bruges til det, EIRA-CONTEXT §10 tillader; enhedsgodkendelse over for Fleet sker med mTLS og TPM-nøglen.
2. **Nøglerotation — besluttet og indført i 1.1: rod- og driftsnøgler (RIGHTS-SET §3.1).** Reviewet foreslår et nyt ankersæt signeret af det forrige anker. Det løser planlagt rotation, men ikke kompromittering: den, der har lækket det gamle anker, kan selv signere sig et nyt. Beslutning: to niveauer. Enrollment fastgør tenantens **rod-nøgle** (offline, langlivet, i HSM), og roden udsteder kortlivede **driftsnøgler** med `not_after` som nøglecertifikater, leveret via desired state. En lækket driftsnøgle tilbagekaldes af roden uden re-enroll; kun en lækket rod kræver re-enroll.
3. **Besluttet 12. november 2026:** kontrakten (denne tekst, OpenAPI-filen og vektorerne) findes kun i `eira-os`. `eira-fleet-control` har ingen kopi, men peger på et tag i `eira-os` og kører OpenAPI-testene og vektorerne derfra i sin CI.
4. **Åbent: to veje ved første opstart** (ADR-0005 K6). Enroll sker i dag efter installationen med en invitationsfil (§8). Enroll fra installeren med en kort kode kræver et nyt endpoint og et tillidsanker, før enheden kender Fleets CA (ADR-0005 O-8). Desired state skal også bære `device_mode` (`closed` | `open`, EIRA-CONTEXT §10), som endnu ikke står i OpenAPI-filen. Fleets eneste rolle for private kontekster er dette flueben: de får pakkens standardsæt uden `system:`-handlinger, og Fleet udsteder intet for dem (ADR-0005 O-9, besluttet).
