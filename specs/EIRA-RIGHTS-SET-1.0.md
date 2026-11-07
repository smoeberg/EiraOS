# EIRA Rights Set 1.0 — kontrakt mellem Fleet og endpoint

**Status:** UDKAST til ejerens godkendelse. Ikke bindende, før det er godkendt.
**Version:** 1.0-draft
**Parter:** `eira-fleet-control` (udsteder) og `eira-os` (`eira-governance-agent` anvender, Gate håndhæver)
**Grundlag:** [ADR-0003](../docs/decisions/ADR-0003-rettigheder-fra-fleet.md), [GATE-KERNEL bilag A og B](GATE-KERNEL-1.0.md), Fleet Agent Protocol v0.1 (`eira-fleet-control`)

> Alle rettigheder i EiraOS sættes via Fleet's rettigheds-API. Endpointet håndhæver dem og er aldrig autoritativ kilde til rettigheder.

Dokumentet ligger under `specs/` (Open Architecture-kontrakter), fordi begge projekter skal implementere det. Fleet Agent Protocol henviser hertil (§9).

---

## 1. Hvad et rettighedssæt er

Et **rettighedssæt** er ét signeret dokument, der fuldt ud beskriver, hvad principaler må på én enhed. Det erstatter altid det forrige sæt helt. Der findes ingen delta, ingen lokal sammenfletning og ingen lokale tilføjelser.

| Begreb | Kilde | Eksempel |
|---|---|---|
| Principal og grupper (*hvem*) | Entra / `identityd` | `entra:oid:9f3…`, `group:laerere` |
| Grant og deny (*hvad*) | Fleet, via skabelon | `edp:commitment_proposed` på `obj:sag:*` for `group:laerere` |
| Håndhævelse | Gate (lag 4 og 6) | `REJECT E_UNAUTHORIZED` |

Grupper giver ingen rettigheder i sig selv. Gaten må aldrig oversætte en gruppe til en rettighed; det må kun en grant i et gyldigt sæt.

## 2. Wire-format

Formatet er JSON (UTF-8), fordi Fleet Agent Protocol er JSON over HTTPS.

**Begrænset profil:**
- ingen floats og ingen `null` i grants,
- kun ASCII i nøgler,
- tekstværdier i Unicode NFC,
- dokumentet er højst 1 MiB.

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
      "subject": {"principal": "entra:oid:9f3…"},
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
| `issued_at`, `expires_at` | RFC 3339 med tidszone, og `issued_at` < `expires_at`. `expires_at` er TTL'en |
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
  u8 len(DOMAIN) || DOMAIN="EIRAOS-RIGHTS-V1" || kanonisk JSON af sættet uden "signature"
  ```
  `alg` og `key_id` er en del af det signerede input, fordi de ligger i sættet uden for `signature.value`. Kun `signature.value` fjernes før signering.
- Tillidsankre:
  - **`managed`:** tenantens Fleet-nøgle, leveret ved enroll over mTLS og fastgjort som Fleet URL pinning (Agent Protocol §2.1).
  - **`default`:** Fleet's release-nøgle, samme anker som bundles.
- Nøglerotation sker via `key_id`. Et ukendt `key_id` gør sættet ugyldigt.

## 4. Anvendelse på endpointet (`eira-governance-agent`)

Agenten er den eneste skriver til gatens rettighedscache. Gaten har ingen IPC-metode og ingen admin-vej til at tildele rettigheder.

Et nyt sæt anvendes kun, hvis **alle** disse er opfyldt:
1. Signaturen er gyldig med et kendt anker for sættets `kind`.
2. `tenant_id` og `device_id` matcher enhedens enroll-identitet. For `default` gælder det kun, når enheden ikke er enrolled.
3. `version` er højere end det aktive sæts. Samme version med samme indholdshash er en idempotent no-op, men samme version med andet indhold er en fejl.
4. `issued_at` ≤ nu < `expires_at`, med en tolerance for urforskydning på 5 minutter.
5. Alle handlingsnøgler findes i gatens registry for den installerede gate-version.

Sættet anvendes **atomart**: hele cachen erstattes i én transaktion. `rights_set_id`, `version`, `template`, `issued_by` og indholdshashet gemmes. Hvis et af kravene ikke er opfyldt, anvendes intet. Det aktive sæt forbliver aktivt, og fejlen rapporteres via `POST /v1/report/apply-result` og audit-loggen.

## 5. Kilde pr. situation (ADR-0003)

| Situation | Kilde |
|---|---|
| Managed og online | Seneste `managed`-sæt fra Fleet |
| Managed og offline | Det aktive `managed`-sæt indtil `expires_at` |
| Managed, sættet er udløbet eller mangler | **Ingen grants** (se åbent punkt 1) |
| Unmanaged eller privat | Bundlens `default`-sæt, signeret af Fleet ved release |
| Unmanaged, som enrolles senere | `managed`-sættet erstatter `default`-sættet og kan ikke gå tilbage |

**`default`-sættet** er minimalt (fx skabelonen `personal`), versioneret pr. bundle-release og kan ikke udvides lokalt. Det ligger read-only i pakken under `/usr/share/eira-os/rights/default.json`.

## 6. Håndhævelse i gaten

- **Lag 6** tillader en handling for principal *P* på scope *S*, hvis tre ting gælder i det aktive, ikke-udløbne sæt: en grant matcher (*P* eller en af *P*'s grupper fra `identityd`, eller `authenticated`), handlingsnøglen og scope matcher, og ingen deny matcher. Grantens `required_assurance` lægges oven i policyens krav.
- **Domæne (lag 4):** Medlemskab af en samtale er samtaledata, ikke en rettighed. Det kommer fra samtalelaget. `device:local` kræver mindst én gyldig grant på `device:local`.
- **Audit:** Hver gate-beslutning registrerer `rights_set_id`, `version`, `template.id` og `issued_by.api_call_id`. Ved en PASS registreres også, hvilken grant der autoriserede handlingen.
- **Udløb midt i en handling:** Lag 6 tjekkes igen umiddelbart før udførelse (GATE-KERNEL §3.6). Er sættet udløbet, giver det `REJECT`.

## 7. Fleet Agent Protocol v0.2 (ændringer i `eira-fleet-control`)

- `GET /v1/desired-state` får feltet `rights_set`, som indeholder et sæt efter denne kontrakt, eller er udeladt, når intet er ændret.
- `POST /v1/report/apply-result` rapporterer `rights_set_id`, `version` og `result` (`applied`, `rejected:<årsag>` eller `noop`).
- Heartbeat'en får `rights_version` og `rights_expires_at`, så Fleet Console kan vise enheder, der er ved at udløbe.

## 8. Tests, der skal bestå, før kontrakten er "færdig"

1. Et sæt med forkert signatur, ukendt `key_id`, forkert tenant/device, lavere version, udløbet `expires_at`, en ukendt handlingsnøgle, `*` i `actions`, et ukendt felt eller en float afvises, og det aktive sæt er uændret.
2. Samme version med andet indhold afvises. Samme version med samme indhold er en no-op.
3. Deny vinder over grant.
4. En gruppe uden grant giver ingen rettighed.
5. `required_assurance` kan skærpe, men ikke lempe.
6. Et udløbet sæt giver `REJECT` i lag 6, også mellem claim og udførelse.
7. Et `default`-sæt afvises på en enrolled enhed.
8. Gaten har ingen IPC-metode, der skriver til rettighedscachen. Det bevises af metodeklassifikationstesten.
9. Audit-poster indeholder rettighedssættets id og version.

## 9. Åbne punkter til ejer

1. **Når et `managed`-sæt udløber:** Udkastet siger *ingen grants*, så beskyttede handlinger låses, mens læsning fortsætter. Alternativet er at falde tilbage til bundlens `default`-sæt. Det er mere brugervenligt, men giver en managed maskine "privat"-rettigheder. Anbefaling: ingen grants.
2. **TTL:** Fleet MVP har en offline-buffer på højst 72 timer. Skal `expires_at` for `managed` være højst 72 timer, eller være en tenant-indstilling?
3. **Hvor kontrakten ligger:** Udkastet foreslår `eira-os/specs/`, med henvisning fra `eira-fleet-control`. Alternativet er det modsatte.
