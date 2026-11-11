# EIRA Rights Set 1.0 — kontrakt mellem Fleet og endpoint

**Status:** Godkendt af ejer 7. november 2026. Normativ.
**Version:** 1.2 (8. november 2026: 1.1 eget levetidsloft for `default`-sæt, §4.2, og standardsættets bygning, §5.2; 1.2 ankre udløber, `anchor_expired`, §3; 1.3 rod- og driftsnøgler, tilbagekaldelse, `key_revoked`, §3.1)
**Parter:** `eira-fleet-control` (udsteder) og `eira-os` (`eira-governance-agent` anvender, Gate håndhæver)
**Grundlag:** [ADR-0003](../docs/decisions/ADR-0003-rettigheder-fra-fleet.md), [GATE-KERNEL bilag A og B](GATE-KERNEL-1.0.md), Fleet Agent Protocol v0.1 (`eira-fleet-control`)

> Alle rettigheder i EiraOS sættes via Fleet's rettigheds-API. Endpointet håndhæver dem og er aldrig autoritativ kilde til rettigheder.

**Kontrakten er eksekverbar.** Teksten her er normativ, men det er disse fire filer tilsammen, der er kontrakten:

| Fil | Rolle |
|---|---|
| `specs/EIRA-RIGHTS-SET-1.0.md` | normativ tekst (dette dokument) |
| `app/rights/eira-rights-set-1.0.schema.json` | struktur (JSON Schema 2020-12); ligger ved verifikatoren, så den følger med i pakken |
| `app/rights/contract.py` | referenceverifikator: `verify` (§4) og `authorize` (§6) |
| `tests/vectors/rights-set/*.json` | gyldige og ugyldige sæt med forventet udfald, kørt af `tests/test_rights_set_contract.py` |

Kontrakten ligger i `eira-os`, fordi verifikatoren er her. `eira-fleet-control` tager den som en pinnet, versioneret afhængighed og kører **de samme vektorfiler** mod sin udsteder i CI. Driver de to sider fra hinanden, fejler CI på mindst én af siderne. Vektorerne genereres med `scripts/gen_rights_vectors.py` (testnøgler fra faste seeds; aldrig tillidsankre på en rigtig enhed) og committes.

---

## 1. Hvad et rettighedssæt er

Et **rettighedssæt** er ét signeret dokument, der fuldt ud beskriver, hvad principaler må på én enhed. Det erstatter altid det forrige sæt helt. Der findes ingen delta, ingen lokal sammenfletning og ingen lokale tilføjelser.

| Begreb | Kilde | Eksempel |
|---|---|---|
| Principal og grupper (*hvem*) | Identitetsudbyderen / `identityd` | `did:eira:<provider-id>.<subjekt>` ([EIRA-IDENTITY 1.0](EIRA-IDENTITY-1.0.md), samme form som EDP-deltagere; fx `did:eira:entra.<oid>` for en installation med Entra), gruppenavne fra den konfigurerede gruppe-claim |
| Grant og deny (*hvad*) | Fleet, via skabelon | `edp:commitment_proposed` på `obj:sag:*` for `group:laerere` |
| Håndhævelse | Gate (lag 4 og 6) | `REJECT E_UNAUTHORIZED` |

Grupper giver ingen rettigheder i sig selv. Gaten må aldrig oversætte en gruppe til en rettighed; det må kun en grant i et gyldigt sæt.

## 2. Wire-format

Formatet er JSON (UTF-8), fordi Fleet Agent Protocol er JSON over HTTPS.

**Begrænset profil** (overtrædelse giver `malformed`):
- ingen floats (heller ikke `42.0`), ingen `NaN`/`Infinity`, ingen `null`,
- ingen dobbelte nøgler — ellers kan to parsere se to forskellige sæt bag samme signatur,
- kun ASCII i nøgler, tekstværdier i Unicode NFC,
- dokumentet er højst 1 MiB.

Tidspunkter skrives altid som UTC med sekundpræcision: `YYYY-MM-DDTHH:MM:SSZ`. Én skrivemåde pr. tidspunkt, så kanonisk JSON er entydig.

Inden for profilen er **kanonisk JSON** = RFC 8785 (JCS). I Python svarer det til `json.dumps(sort_keys=True, separators=(",", ":"), ensure_ascii=False)`.

```json
{
  "eira_rights": "1",
  "rights_set_id": "0190f5a0-0000-7000-8000-00000000abcd",
  "kind": "managed",
  "tenant_id": "kk",
  "device_id": "c0a8…",
  "version": 42,
  "issued_at": "2026-11-07T11:00:00Z",
  "expires_at": "2026-11-10T11:00:00Z",
  "template": {"id": "skoleforvaltning-laerer", "version": "3"},
  "issued_by": {"api_call_id": "req-7f3a", "fleet": "fleet.kk.dk"},
  "grants": [
    {
      "subject": {"group": "laerere"},
      "scope": "obj:sag:*",
      "actions": ["edp:utterance", "edp:commitment_proposed", "edp:commitment_accepted"]
    },
    {
      "subject": {"group": "laerere"},
      "scope": "device:local",
      "actions": ["system:power.request_action"]
    },
    {
      "subject": {"principal": "did:eira:entra.9f3…"},
      "scope": "obj:sag:42",
      "actions": ["edp:value_transfer_requested"],
      "expires_at": "2026-11-07T15:00:00Z",
      "required_assurance": "eid_high"
    }
  ],
  "denies": [
    {"subject": {"group": "vikarer"}, "scope": "device:local", "actions": ["system:power.request_action"]}
  ],
  "signature": {"alg": "ed25519", "key_id": "fleet-kk-2026-11", "value": "<base64url, 64 bytes>"}
}
```

### 2.1 Felter

| Felt | Regel |
|---|---|
| `eira_rights` | `"1"`. Ukendt version afvises |
| `kind` | `managed` (tenant og device) eller `default` (bundlens standardsæt, se §5) |
| `tenant_id`, `device_id` | Skal matche enhedens enroll-identitet. For `default` er `tenant_id` lig `"unmanaged"`, og `device_id` lig `"*"` |
| `version` | Heltal ≥ 1. Strengt stigende pr. (`tenant_id`, `device_id`) |
| `issued_at`, `expires_at` | UTC (`…Z`), `issued_at` < `expires_at`. `expires_at` er TTL'en og sættes af Fleet pr. tenant/skabelon. `expires_at - issued_at` må højst være loftet i §4.2 |
| `template`, `issued_by` | Obligatoriske. De bruges kun til audit og påvirker aldrig autorisationen |
| `grants`, `denies` | Lister (må være tomme). Ukendte felter afvises overalt |

### 2.2 Grant og deny

| Felt | Regel |
|---|---|
| `subject` | Præcis én af:<br>• `{"group": "<id>"}` — en gruppe fra `identityd`<br>• `{"principal": "<id>"}` — en principal fra `identityd`<br>• `{"authenticated": true}` — enhver autentificeret principal på enheden |
| `scope` | `device:local`, `obj:<type>:<id>` eller `obj:<type>:*`. Ingen andre jokertegn |
| `actions` | Handlingsnøgler fra gatens registry, dvs. `edp:<action.type>` eller `system:<operation>`. **Ingen `*`.** Skabeloner udvides i Fleet, ikke på endpointet. En ukendt nøgle gør hele sættet ugyldigt |
| `expires_at` | Valgfri, for en midlertidig grant (step-up). Skal ligge før sættets `expires_at` |
| `required_assurance` | Valgfri. Kan kun *skærpe* gatens policy-krav, aldrig lempe dem |

**Deny vinder altid over grant.** Gatens policy-registry, dvs. reversibilitet, origin, assurance og grænser, gælder stadig. Et rettighedssæt kan ikke tillade noget, som policy forbyder.

## 3. Signatur

- Algoritmen er Ed25519, og samme signaturkontrakt som Phase 0 genbruges med eget domæne.
- Det signerede input er:
  ```
  u8 len(DOMAIN) || DOMAIN="EIRAOS-RIGHTS-V1" || kanonisk JSON af sættet, hvor signature.value er fjernet
  ```
  `alg` og `key_id` er en del af det signerede input, fordi de ligger i sættet uden for `signature.value`. Kun `signature.value` fjernes før signering.
- Tillidsankre:
  - **`managed`:** en af tenantens **driftsnøgler**, certificeret af en rodnøgle (§3.1).
  - **`default`:** en engangsnøgle pr. pakke-build; ankeret ligger i samme pakke (§5.2).
- Et ukendt `key_id` gør sættet ugyldigt (`unknown_key_id`).
- Et `managed`-anker udløber med sit certifikat. Efter `not_after` (målt i verifikatorens effektive tid, §4.1) afvises sæt signeret med nøglen som `anchor_expired`. Udløbet vurderes aldrig mod sættets `issued_at`: den, der har lækket en nøgle, kan tilbagedatere.
- En tilbagekaldt driftsnøgle afviser sæt som `key_revoked`.

### 3.1 Rod- og driftsnøgler (`app/rights/keys.py`)

To niveauer, så en lækket signeringsnøgle kan trækkes tilbage uden at røre enheden:

| Nøgle | Fastgjort | Må signere | Levetid |
|---|---|---|---|
| **Rod** | ved enroll i `/etc/eira/enrollment.json` (`rights_roots`) | kun driftsnøglecertifikater og tilbagekaldelseslisten, **aldrig** et rettighedssæt | `not_after` i enrollment; skift kræver re-enroll |
| **Drift** | via rodcertifikat i desired state | rettighedssæt | højst 90 dage (`MAX_KEY_LIFETIME`) |

**Driftsnøglecertifikat** (domæne `EIRAOS-RIGHTS-KEY-V1`, samme signatur- og kanoniseringsregler som sæt):

```json
{"eira_rights_key": "1", "key_id": "kk-ops-2026-11", "public_key": "<base64url Ed25519>", "tenant_id": "kk",
 "not_before": "2026-11-01T00:00:00Z", "not_after": "2027-01-15T00:00:00Z",
 "signature": {"alg": "ed25519", "key_id": "<rod-id>", "value": "<base64url>"}}
```

Gyldigt, når: udsteder er en fastgjort, ikke udløbet rod; signaturen holder; `tenant_id` er enhedens; levetiden ≤ 90 dage; `not_before` − 5 min. ≤ *nu* < `not_after`; `key_id` er ikke en rods id; ingen ekstra felter.

**Tilbagekaldelsesliste** (domæne `EIRAOS-RIGHTS-REVOKE-V1`), signeret af en rod:

```json
{"eira_rights_revocations": "1", "tenant_id": "kk", "sequence": 3, "issued_at": "…", "revoked": ["kk-ops-2026-08"],
 "signature": {"alg": "ed25519", "key_id": "<rod-id>", "value": "<base64url>"}}
```

- `sequence` stiger; samme sekvens med andet indhold er en konflikt; listen kan kun vokse (en tilbagekaldelse er permanent). En liste, der ikke overholder det, ignoreres, og den gemte gælder.
- **En tilbagekaldt nøgle tager sine sæts rettigheder med sig:** gaten tjekker ved hver beslutning, at nøglen bag det aktive sæt stadig er certificeret og ikke tilbagekaldt (`signing_key_revoked`, `signing_key_expired`).
- **Rotation:** roden certificerer en ny driftsnøgle, Fleet signerer med den, og den gamle tilbagekaldes. Enheden følger uden re-enroll.
- **Kompromittering:** en lækket driftsnøgle tilbagekaldes af roden. En lækket rod kræver re-enroll; derfor holdes roden offline (HSM) og bruges sjældent.

Vektorer: `tests/vectors/rights-keys/` (certifikater og lister, gyldige og ugyldige), kørt af `tests/test_rights_keys.py` og af Fleet's CI.

## 4. Anvendelse på endpointet (`eira-governance-agent`)

Agenten er den eneste skriver til gatens rettighedscache. Gaten har ingen IPC-metode og ingen admin-vej til at tildele rettigheder.

Et nyt sæt anvendes kun, hvis **alle** disse er opfyldt (i denne rækkefølge; første fejl er årsagen):
1. Profil (§2) og schema er overholdt.
2. Signaturen er gyldig med et kendt, ikke udløbet og ikke tilbagekaldt anker for sættets `kind` (§3.1). Intet felt bruges, før signaturen er kontrolleret.
3. `tenant_id` og `device_id` matcher enhedens enroll-identitet. Et `default`-sæt gælder kun, når enheden ikke er enrolled.
4. `expires_at - issued_at` ≤ loftet (§4.2), og `issued_at` − 5 min. ≤ *nu* < `expires_at`, hvor *nu* er den effektive tid (§4.1). Ingen grant eller deny må have `expires_at` efter sættets.
5. Alle handlingsnøgler findes i gatens registry for den installerede gate-version.
6. `version` er højere end det aktive sæts. Samme version med samme indholdshash er en idempotent no-op; samme version med andet indhold er en fejl.

Afvisningsårsagerne er faste strenge (`Reason` i `contract.py`) og rapporteres ordret i `apply-result`.

Sættet anvendes **atomart**: hele cachen erstattes i én transaktion. `rights_set_id`, `version`, `template`, `issued_by` og indholdshashet gemmes. Hvis et af kravene ikke er opfyldt, anvendes intet. Det aktive sæt forbliver aktivt, og fejlen rapporteres via `POST /v1/report/apply-result` og audit-loggen.

### 4.1 Effektiv tid — uret må ikke kunne skrues tilbage

Alle udløb i denne kontrakt — sættets, en grants og gatens samtykke-TTL — er værdiløse, hvis den, der vil forlænge dem, kan stille vægur-tiden tilbage. Agenten og gaten bruger derfor aldrig vægur-tiden alene, men den **effektive tid**:

```
effektiv_nu = max(vægur_nu, højvandsmærke, issued_at_aktivt + forløbet_siden_apply)
```

- **Højvandsmærke:** den højeste vægur-tid, agenten har set, gemt periodisk i en fil, som kun servicebrugeren `eira` kan skrive. Er vægur-tiden mere end 5 min. under mærket, auditeres `clock_rollback`, og mærket bruges.
- **Forløbet siden apply:** summen af `CLOCK_BOOTTIME`-tid siden sættet blev anvendt, akkumuleret på tværs af genstarter. Ved hver skrivning gemmes `(boot_id, boottime)`; ser agenten et nyt `boot_id`, lægges den sidst gemte værdi til summen, og tællingen starter forfra. `CLOCK_BOOTTIME` tæller også tid i suspend, så en lukket bærbar i en taske tæller med.
- **TPM:** Hvor en TPM 2.0 findes, kan dens `Clock` erstatte summen. Det er en skærpelse, ikke et krav i 1.0.

Det tilbageværende hul er tid, hvor maskinen er **slukket** og uret samtidig er stillet tilbage (fx i BIOS). Det kan kun TPM'en lukke. I privat tilstand (ADR-0003) har ejeren root og kan alligevel ændre alt; dér er §4.1 en beskyttelse mod fejl, ikke mod ejeren.

`contract.py` tager *nu* som parameter og læser aldrig selv et ur. Det er bevidst: kontrakten kan ikke falde tilbage til vægur-tid ved en fejl.

### 4.2 Levetidsloft

Fleet vælger `expires_at` pr. tenant og skabelon — det er Fleet, der kender driftsmønsteret (en elev-pc i tasken fra fredag til mandag, en lærer på ferie). Endpointet afviser ethvert sæt, hvor `expires_at - issued_at` overstiger et **loft kompileret ind i bundlen** (`MAX_TTL`):

| Art | Loft | Begrundelse |
|---|---|---|
| `managed` | 30 dage | Beskytter mod en stjålet eller glemt enhed; Fleet fornyer ved kontakt. |
| `default` | 400 dage | Fornyes kun via pakkeopdateringer. På en privat maskine har ejeren root, så et kort udløb beskytter ikke mod noget, men ville låse en maskine, der ikke er opdateret i en måned. 400 dage dækker en udgivelses supportperiode. |

Endpointet kan aldrig hæve et loft; en ny bundle kan sænke det. Et `managed`-sæt kan ikke låne `default`-loftet.

Fleet fornyer sættet ved hver kontakt (ny `version`, nyt `expires_at`), når mindre end halvdelen af levetiden er tilbage. Derfor er `expires_at` i praksis "sidste kontakt + TTL", og der er ikke brug for et særskilt nåde-begreb ved siden af.

## 5. Kilde pr. situation (ADR-0003)

| Situation | Kilde |
|---|---|
| Managed og online | Seneste `managed`-sæt fra Fleet |
| Managed og offline | Det aktive `managed`-sæt indtil `expires_at` |
| Managed, sættet er udløbet eller mangler | **Ingen grants** (§5.1) |
| Unmanaged eller privat | Bundlens `default`-sæt, signeret af Fleet ved release |
| Unmanaged, som enrolles senere | `managed`-sættet erstatter `default`-sættet og kan ikke gå tilbage |

### 5.1 Udløbet eller manglende sæt

Et udløbet sæt giver **nul rettigheder** for gate-handlinger. Det betyder ikke "ingen maskine":

- Gaten starter, audit kan læses, og status viser *hvorfor* handlinger er låst (`rights_expired`, med `expires_at` og sidste kontakt til Fleet).
- Det, der skal til for at komme online igen — login, netværk, tidssynkronisering og agentens eget kald til Fleet — er **ikke gate-handlinger**. Det hører til substratet (ADR-0003, "ét begreb hører til ét lag") og afhænger aldrig af rettighedssættet. Det er et krav til `eira-governance-agent`, som skal testes dér.
- Der er **ingen nødkonvolut** med grants. Et sæt, der giver rettigheder, når der ingen rettigheder er, udvider rettighederne; det kan ikke samtidig "kun formindske". Sluk og genstart sker med tænd/sluk-knappen via logind, ikke via gaten.

**`default`-sættet** er minimalt (skabelonen `personal`), versioneret pr. pakke og kan ikke udvides lokalt. Det ligger read-only i pakken under `/usr/lib/eira-os/rights/default.json` sammen med sit anker (`anchors.json`).

### 5.2 Standardsættets bygning og anvendelse

- **Bygning** (`scripts/build_default_rights.py`, kaldt af `debian/rules`): sættet signeres med en Ed25519-nøgle, der dannes til det ene build og aldrig skrives nogen steder. Sæt og anker ligger i samme pakke, så pakkens egen signatur (apt) er tillidsroden; en langlivet nøgle ville ikke beskytte mere, men være en hemmelighed, der kan lække. Følge: et `default`-sæt kan kun erstattes af en ny pakke.
- `version` og `issued_at` er den faktiske byggetid. `SOURCE_DATE_EPOCH` ignoreres med vilje: `dpkg-buildpackage` sætter den ud fra `debian/changelog`, hvilket ville give samme version med forskelligt indhold ved hvert build.
- **Indhold:** den indloggede bruger (`authenticated`) får alle gatens `edp:`-handlinger på `obj:sag:*` og alle `system:`-handlinger på `device:local`. Samtykke, rendering og audit gælder stadig for hver handling.
- **Anvendelse:** `eira-rights-apply apply-default` (`app/rights/agent.py`) kører som `ExecStartPre` i `eira-intentd.service`: samme bruger, sandkasse og AppArmor-profil, men en separat proces, så gaten ikke selv skriver rettigheder. Fejler den, starter gaten alligevel uden (nyt) sæt og fejler lukket. På en enrolled enhed (`/etc/eira/enrollment.json`) anvendes standardsættet ikke.
- Agenten vurderer sæt ved `max(vægur, cachens højvandsmærke)` (§4.1).

## 6. Håndhævelse i gaten

- **Lag 6** tillader en handling for principal *P* på scope *S*, hvis tre ting gælder i det aktive, ikke-udløbne sæt: en grant matcher (*P* eller en af *P*'s grupper fra `identityd`, eller `authenticated`), handlingsnøglen og scope matcher, og ingen deny matcher. Grantens `required_assurance` lægges oven i policyens krav.
- **Domæne (lag 4):** Medlemskab af en samtale er samtaledata, ikke en rettighed. Det kommer fra samtalelaget. `device:local` kræver mindst én gyldig grant på `device:local`.
- **Audit:** Hver gate-beslutning registrerer `rights_set_id`, `version`, `template.id` og `issued_by.api_call_id`. Ved en PASS registreres også, hvilken grant der autoriserede handlingen.
- **TTL ved hver beslutning:** `authorize` kontrollerer sættets og grantens udløb mod den effektive tid ved *hver* beslutning — ved `propose` og igen ved `confirm`, hvor gaten kører lag 1–4 og lag 6 på ny (GATE-KERNEL §3.6). Det er ikke nok, at agenten afviste et udløbet sæt ved apply.
- **Udløb midt i en handling:**
  - *Foreslået eller accepteret, ikke bekræftet:* `confirm` giver `REJECT E_UNAUTHORIZED`. Handlingen er aldrig udført, så der er intet at kompensere.
  - *Billet udstedt, executor i gang:* Udførelsen fuldføres, og resultatet auditeres. Lag 6 kontrolleres sidst *før* billetten udstedes; efter det tidspunkt afbryder et udløb ikke en handling halvvejs. Der indføres ingen kompensationsmekanik for dette tilfælde.

## 7. Levering fra Fleet

Hvordan et sæt kommer fra Fleet til enheden, og hvordan resultatet meldes tilbage, er defineret i [EIRA-FLEET-RIGHTS-API-1.0](EIRA-FLEET-RIGHTS-API-1.0.md) (desired state, apply-result, heartbeat og enrollment-filen).

## 8. Tests

Vektorerne i `tests/vectors/rights-set/` dækker (`apply-*.json`): gyldigt managed- og default-sæt, udløbet, endnu ikke gyldigt, lavere version, samme version med samme og med andet indhold, forkert device, forkert tenant, gyldig signatur over forkert domæne (`EIRAOS-EVENT-V1`), ændret efter signering, ukendt `key_id`, managed-sæt signeret med release-nøglen, manglende `template`, TTL over loftet, ukendt handlingsnøgle, `*` i `actions`, ukendt felt, float, dobbelt nøgle, grant der overlever sættet, default-sæt på enrolled enhed og managed-sæt på uenrolled enhed. `authorize.json` dækker: gruppe-grant, gruppe uden grant, deny vinder, jokertegn-grænser, midlertidig grant der udløber, skærpet assurance og udløbet sæt.

Krav, der testes, når agenten og gatens lag 6 bygges ovenpå (ikke del af vektorerne):
1. Et afvist sæt efterlader det aktive sæt uændret (atomar apply).
2. Gaten har ingen IPC-metode, der skriver til rettighedscachen (metodeklassifikationstesten).
3. Audit-poster indeholder rettighedssættets id og version, og ved PASS den autoriserende grant.
4. Effektiv tid (§4.1): et tilbagestillet ur forlænger hverken sæt, grant eller samtykke.
5. Agentens kontakt til Fleet virker med et udløbet sæt (§5.1).

## 9. Afklaret (7. november 2026)

1. **Udløb:** nul rettigheder for gate-handlinger, ingen nødkonvolut; substratet holder maskinen i live (§5.1). TTL håndhæves ved hver beslutning (§6).
2. **TTL:** Fleet sætter `expires_at` pr. tenant/skabelon under et kompileret loft på 30 dage (§4.2); udløb måles i effektiv tid (§4.1).
3. **Placering:** `eira-os`: tekst i `specs/`, schema og verifikator i `app/rights/`, vektorer i `tests/vectors/rights-set/`; pinnet og kørt i `eira-fleet-control` (indledning).
