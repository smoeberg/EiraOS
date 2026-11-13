# EIRA Context 1.0 — kontekster, lagring og synkronisering

**Status:** Accepteret af ejer 11. november 2026. Normativ. Testplan: [EIRA-CONTEXT-1.0-TESTPLAN](EIRA-CONTEXT-1.0-TESTPLAN.md).
**Version:** 0.3 (11. november 2026: rev. 0.2 ikke-deterministisk blokkryptering med AAD, skelnen mellem identifikatorer; rev. 0.3 fejlkoder for blokke, manifest-kollision og hjem uden opret-hvis-fraværende, fundet under testplanen; invarianterne R-1 og F-1; `/proc` med `hidepid=invisible`; invariant A-1; Fleet-sync bærer ikke brugerdata; enhedens nøgler i TPM'en (§5.0), P-256 i stedet for Ed25519/X25519)
**Grundlag:** [ADR-0005](../docs/decisions/ADR-0005-kontekster-og-datas-hjem.md) (K1–K11), [ADR-0004](../docs/decisions/ADR-0004-gui-arkitektur-vendor-neutral.md) D1, [ADR-0006](../docs/decisions/ADR-0006-livets-indbakke.md) L5 (glimt)
**Berører:** ny `eira-contextd` (rod-formidler), `identityd`, gaten, graphd, samtalelaget, den neutrale skal, compositoren, `eira-governance-agent`/Fleet, RIGHTS-SET (revision, §10)

Kontrakten gør ADR-0005 konkret: hvad en kontekst er som data, hvordan den lever på en enhed, hvordan dens data krypteres, gemmes og synkroniseres, og hvad ID-hjemmet indeholder. Den definerer ikke Web App Manager, livets indbakke eller adapterkontrakten; de bygger oven på den.

---

## 1. Begreber og identifikatorer

**Ingen identifikator må bruges i stedet for en anden** (rev. 0.2):

| Identifikator | Hvad den er | Rækkevidde |
|---|---|---|
| `context_id` | Kontekstens semantiske identitet | Global: Fleet, ID-hjemmet, kontekst-hjemmet, rettighedssæt |
| `identity` (`did:eira:…`) | Hvem der er logget ind (EIRA-IDENTITY) | Global |
| `device_id` | Enhedens identitet | Global |
| `tenant_id` | Organisationen, der styrer (governance) | Global |
| Linux-UID | Kernens isolationsprimitiv for én kontekst på én enhed | **Kun lokal.** Forlader aldrig enheden og optræder aldrig i data, protokoller, audit uden for enheden eller rettighedssæt |

Hvor koden har en UID (fx fra `SO_PEERCRED`) og skal bruge en kontekst, slår den `context_id` op i `eira-contextd`s lokale tabel. Opslaget er det eneste sted, de to mødes.

| Begreb | Identifikator | Form |
|---|---|---|
| Kontekst | `context_id` | `ctx_` + 26 tegn base32 (128 bit tilfældigt). Ændres aldrig. **Kontekstens eneste identifikator** i Fleet, ID-hjemmet og kontekst-hjemmet. Den er ikke hemmelig: sikkerheden ligger i nøglerne (§5), ikke i id'et |
| Identitet | `identity` | `did:eira:<provider-id>.<subjekt>` (EIRA-IDENTITY) |
| Enhed | `device_id` | Fingeraftryk (SHA-256) af enhedens offentlige signeringsnøgle (§5.0) |
| Person | – | Har **ingen** identifikator i EiraOS ud over sine identiteter og (valgfrit) sit ID-hjem-pseudonym (§9). Organisationer kan ikke koble kontekster til en person (K2) |

## 2. Kontekst-posten

En kontekst beskrives af en **kontekst-post**. Posten ligger i kontekstens hjem (krypteret, §6) og, for organisationskontekster, hos Fleet. Enheden har en krypteret cache (§4).

```json
{
  "eira_context": "1",
  "context_id": "ctx_…",
  "display_name": "Bestyrelse, badmintonklubben",
  "kind": "organisation",
  "identity": {"provider_id": "klub-idp", "subject_hint": null},
  "governance": {"source": "fleet", "tenant_id": "…"},
  "home": {"type": "s3", "endpoint": "https://…", "bucket": "…", "prefix": "<pseudo>"},
  "policy": {
    "max_offline_days": 7,
    "glimt_allowed": true,
    "glimt_level": "activity",
    "forget_after_days": 30,
    "versions": {"keep_days": 30, "trash_days": 30},
    "devices": "personal_and_managed"
  },
  "created_at": "…"
}
```

| Felt | Regel |
|---|---|
| `kind` | `organisation` (styret af en organisations Fleet) eller `personal` (styret af personen) |
| `identity.provider_id` | Udbyderen, personen logger ind med for at låse konteksten op. En bestyrelseskontekst uden egen udbyder bruger personens private udbyder (ADR-0005, "Begreber") |
| `governance.source` | `fleet` (rettigheder og politik fra organisationen), `person` eller `guardian` (barnets kontekst, styret af værgernes signerede regler, ADR-0005 K12) |
| `home` | Kontekst-hjemmet (K3). `type` er `s3` eller `webdav` (K8 lag 1). `prefix` er et pseudonym, så hjemmet ikke ser kontekstens navn |
| `policy.max_offline_days` | K4/K10. Standard 7 for `personal`. Sat af Fleet for `organisation` |
| `policy.glimt_allowed` | ADR-0006 L5. En organisation kan forbyde glimt fra sin kontekst |
| `policy.glimt_level` | `activity` (antal og tidspunkt) eller `calendar` (derudover tid og sted for aktiviteter). Standard `activity`; fællesskaber kan sætte `calendar` |
| `policy.forget_after_days` | §4.3. Standard 30, 1–90 |
| `policy.versions` | §7. Standard `keep_days` 30 og `trash_days` 30. Organisationer sætter egne værdier via Fleet |
| `policy.devices` | `managed_only` (kun enheder enrolled hos organisationen) eller `personal_and_managed` |

`display_name` ligger kun i den krypterede post. Det må aldrig stå i klartekst hos hjemmet, i ID-hjemmet eller i en anden konteksts data.

## 3. OS-model: én Linux-bruger pr. kontekst (K7)

### 3.1 Brugere

| Bruger | UID | Rolle |
|---|---|---|
| `eira-shell` | systembruger | Den neutrale skal. Autologges af greetd (K9). Kører compositor og Eira-skallen. Har **ingen** adgang til nogen konteksts data |
| `eira-c-<kort-id>` | fra et reserveret interval (O-1) | Én pr. kontekst pr. enhed. Ejer kontekstens lokale kopi og kører kontekstens processer (Eira UI-delen, webapps, adaptere). Ingen adgangskode, ingen login-shell |
| `eira-contextd` | root, snævert begrænset (AppArmor, systemd-hærdning) | Opretter, låser op, låser og fjerner kontekst-brugere. Det eneste sted, der har rettighed til at oprette Linux-brugere |

Personer ser aldrig Linux-brugere. `eira-c-<kort-id>` afledes af `context_id`, men afslører ikke `display_name`.

**Linux-UID'en er kun lokal** (besluttet, O-1): den er det tal, kernen på én enhed bruger til at adskille filer og processer, og den er forskellig fra enhed til enhed. `eira-contextd` tildeler den fra et reserveret interval og holder koblingen `context_id` → UID lokalt. Koblingen forlader aldrig enheden, og UID'en bruges aldrig som identifikator uden for enheden. Intervallet vælges, så det ikke kolliderer med systemd's reserverede intervaller (dynamiske brugere 61184–65519, homed 60001–60513, containere fra 524288); det præcise interval fastlægges i testplanen mod Ubuntu 26.04.

### 3.2 Hvad hver kontekst-bruger har

- Eget hjemmekatalog i en egen LUKS2-volumen (`/var/lib/eira/contexts/<kort-id>.luks`, monteret med mode `0700`), krypteret i hvile med kontekstens nøgle (§5.3).
- Egen `systemd --user`-instans (startet af `eira-contextd` via `user@<uid>.service`), egen D-Bus-sessionsbus og egen PipeWire-instans.
- **Egen Wayland-socket**, oprettet af compositoren med `wp_security_context_v1` og mærket med `context_id`. Compositoren ved dermed, hvilken kontekst hvert vindue tilhører (ADR-0004 D6). Ingen kontekst-bruger kan forbinde til compositorens hovedsocket.
- Lyd ud og notifikationer går gennem en snæver formidler i skallen. Udklipsholder og fil-deling mellem kontekster findes ikke (K2, ADR-0006 L5).

### 3.3 Grænser, der testes

En kontekst-bruger kan ikke læse en anden konteksts filer, sende signaler til dens processer, ptrace dem, forbinde til dens D-Bus eller Wayland-socket eller læse dens udklipsholder. Skal-brugeren kan ingen af delene over for nogen kontekst.

**Processer er usynlige på tværs af brugere** (besluttet af ejer). `/proc` monteres for hele systemet med `hidepid=invisible`, så hver bruger kun ser sine egne processer. Uden det kan enhver bruger læse alle processers kommandolinje og dermed se, hvilke webapps og URL'er en anden kontekst kører. Systemtjenester, der skal se alle processer (fx polkit), undtages via gruppen `eira-procview` (`gid=`). Gruppen har ingen personlige brugere, kontekst-brugere eller `eira-shell` som medlemmer. Kontekst-tjenesterne (`user@<uid>.service`) får desuden `ProtectProc=invisible` som ekstra lag.

## 4. Livscyklus på en enhed

```
       (login/udlevering)          (lås op)            (lås / dvale / log ud)
ukendt ──────────────► til stede ──────────► åben ◄────────────────────► låst
                          │                                                │
                          │◄────────────── (ubrugt > N dage, §4.3) ────────┤
                          ▼                                                │
                       fjernet ◄──────────── (tilbagekaldt, §8) ───────────┘
```

| Tilstand | På enheden | Kontekst-brugerens processer |
|---|---|---|
| **ukendt** | Intet | – |
| **til stede** | Krypteret lokal kopi, låst. Enheden kan ikke læse den | Ingen |
| **åben** | Kopi låst op. Synkroniserer, når der er net | Kører |
| **låst** | Kopien låst. Nøglen er kun forseglet i TPM'en (§5.2) | Stoppet |
| **fjernet** | Alt slettet, nøgler fjernet fra TPM'en, Linux-brugeren slettet | – |

### 4.1 Første login på en enhed

0. Ved første opstart er enheden enten tilknyttet en organisation (enrolled hos Fleet) eller oprettet med et Eira ID (ADR-0005 K6, "To veje ved første opstart"). På en åben organisationsenhed kan personer desuden tilknytte deres private Eira ID.
1. Personen logger ind i skallen med en identitet (EIRA-IDENTITY).
2. Skallen finder personens kontekster: fra ID-hjemmet (§9) eller, på en lukket organisationsenhed, fra Fleet (K11). På en åben organisationsenhed kommer organisationens kontekster fra Fleet og personens private kontekster fra ID-hjemmet.
3. For hver kontekst, personen vælger at åbne: `eira-contextd` opretter kontekst-brugeren, henter den krypterede post og kontekstens nøgle **pakket til denne enhed** (§5.1), forsegler nøglen i TPM'en og starter synkronisering.
4. Kræver konteksten en anden identitet end den, der blev brugt ved log ind (fx arbejde), logger personen ind med den, før konteksten åbnes.

### 4.2 Oplåsning offline (K4)

En kontekst i tilstanden **låst** kan låses op uden net, hvis:
- dens nøgle er forseglet i enhedens TPM, og forseglingen kræver personens lokale oplåsning (PIN eller biometri via TPM-politik); og
- seneste verificerede online-kontakt med kontekstens hjem og udbyder ikke er ældre end `policy.max_offline_days`.

Tiden måles som i RIGHTS-SET §4.1 ("uret må ikke kunne skrues tilbage"): seneste kendte tid fra hjemmets signerede svar er en nedre grænse, og et lokalt ur, der går baglæns, forlænger ikke perioden. Er perioden udløbet, kan konteksten kun åbnes online.

### 4.3 Glemsel (K11 / O-5 i ADR-0005)

En kontekst, der ikke har været åben i `policy.forget_after_days` dage, fjernes fra enheden (besluttet, O-2). Data findes stadig i kontekstens hjem; kun enhedens kopi forsvinder og synkroniseres igen ved næste åbning. Enheden husker intet læsbart om konteksten bagefter.

| Kontekst | Standard | Kan ændres af |
|---|---|---|
| `organisation` | 30 dage | Organisationen via Fleet (1–90 dage) |
| `personal` | 30 dage | Personen (1–90 dage) |

## 5. Nøgler

### 5.0 Enhedens nøgler (besluttet af ejer)

Hver enhed har to nøglepar på kurven **P-256**: en signeringsnøgle (ECDSA) og en nøgle til nøgleudveksling (ECDH). P-256 er valgt, fordi TPM 2.0 understøtter den overalt; Ed25519 og X25519 understøttes ikke af almindelige TPM'er.

- **Nøglerne dannes i TPM'en og kan ikke eksporteres** (`fixedTPM`, `fixedParent`). På disken ligger kun TPM'ens indpakkede nøgleblob, som er ubrugelig uden netop denne TPM. En klonet disk kan derfor hverken signere, dekryptere eller bevise, at den er enheden (invariant A-1).
- Samme signeringsnøgle bruges til manifester (§6.3), til mTLS mod Fleet (EIRA-FLEET-RIGHTS-API §8) og som grundlag for `device_id`.
- **Hvad det beskytter mod:** kloning og tyveri af disken. **Ikke** root på den kørende enhed: den, der har root, kan bruge nøglen via TPM'en, så længe enheden kører. Det kræver målt opstart og remote attestation og er udskudt (EIRA-FLEET-RIGHTS-API §6 pkt. 1).

**Enheder uden TPM 2.0** (besluttet af ejer):

- Kan **ikke** være organisationsenheder. Tilmelding til Fleet afvises (`E_CONTEXT_POLICY`), og organisationskontekster kan ikke åbnes.
- Kan bruges til **personlige** kontekster. Nøglerne ligger da i en fil, krypteret med en nøgle afledt af personens oplåsning (Argon2id). Skallen viser tydeligt, at enheden ikke er beskyttet mod kloning, og enhedslisten (§8) mærker enheden `key_protection: "file"`, så personens andre enheder kan se det.

### 5.1 Nøglehierarki pr. kontekst

| Nøgle | Hvad | Hvor |
|---|---|---|
| **CMK** (context master key) | 256 bit tilfældigt. Åbner kontekstens data | Aldrig i klartekst uden for en åben kontekst på en enhed |
| CMK pakket til enhed | CMK krypteret til enhedens ECDH-nøgle (HPKE, RFC 9180, `DHKEM(P-256, HKDF-SHA256)`/`HKDF-SHA256`/`ChaCha20Poly1305`). Udpakningen sker i TPM'en (`TPM2_ECDH_ZGen`) | `keys/devices/<device_id>` i kontekstens hjem |
| CMK pakket til genoprettelse | CMK krypteret til genoprettelsestjenestens frigivelse (K5, §7) | `keys/recovery` i kontekstens hjem (kun `personal`) |
| CMK pakket til organisationen | CMK krypteret til organisationens escrow-nøgle | `keys/org` i kontekstens hjem (kun `organisation`, K5) |
| Afledte nøgler | HKDF-SHA256 fra CMK med faste etiketter (§6) | Afledes ved brug, gemmes ikke |

Enhedens nøgler ligger i TPM'en og kan ikke eksporteres (§5.0).

### 5.2 Forsegling på enheden

Når en kontekst åbnes første gang på en enhed, forsegles CMK i TPM'en til (a) netop denne TPM og (b) personens lokale oplåsning (PIN eller biometri via TPM-politik). Låses konteksten, fjernes CMK fra hukommelsen; kun forseglingen bliver. Binding til målt opstart (PCR-politik) kommer med målt opstart og attestation (EIRA-FLEET-RIGHTS-API §6 pkt. 1) og er ikke et krav i 1.0.

### 5.3 Lokal kopi i hvile: LUKS2 pr. kontekst (besluttet, O-5)

- Hver kontekst har sin egen LUKS2-volumen (fil-baseret, vokser efter behov). Den åbnes med en nøgle afledt af CMK (`eira-ctx-local-v1`) og lukkes, når konteksten låses.
- LUKS2 er valgt frem for kryptering pr. katalog (fscrypt), fordi den også skjuler filstørrelser, tidsstempler og katalogstruktur. Det er samme model, som systemd-homed bruger til krypterede hjem pr. bruger.
- Under kontekstvolumenerne ligger fuld diskkryptering bundet til TPM'en.
- Uden CMK kan selv root ikke læse en låst kontekst. En åben kontekst på en kørende enhed er ikke beskyttet mod root (jf. trusselsmodellen i EIRA-CONSENT-AGENT §9).

### 5.4 Organisationens nøgle (escrow)

- Hver organisationskontekst har **sin egen** escrow-nøgle (besluttet af ejer). `keys/org` er CMK pakket til den. En kompromitteret escrow-nøgle åbner derfor kun én medarbejders kontekst, ikke alle.
- Escrow-nøglerne opbevares i Fleet (besluttet af ejer), med tre værn (besluttet af ejer):
  1. **Særskilt rolle:** kun medarbejdere med Fleet-rollen *nøgleforvalter* kan bruge en escrow-nøgle. Rollen følger ikke automatisk med anden Fleet-adgang (fx support eller enhedsadministration).
  2. **Fire øjne:** brug kræver godkendelse fra to forskellige nøgleforvaltere. Den ene kan ikke være den medarbejder, hvis kontekst åbnes.
  3. **Besked til medarbejderen:** medarbejderen får besked om, at konteksten er åbnet (hvem, hvornår, begrundelse), medmindre organisationen registrerer en lovlig grund til udsættelse (fx en verserende sag). Udsættelsen er tidsbegrænset og selv auditeret.
- Enhver brug af en escrow-nøgle (udpakning af en CMK) er en auditeret hændelse i Fleet med hvem (begge godkendere), hvornår, hvilken kontekst og begrundelse.

### 5.5 Rotation

CMK roteres ved tilbagekaldelse af en enhed (§8) og på organisationens anmodning. Ny CMK (og ny pakning til escrow-nøglen) bruges til alt nyt; gamle blokke genkrypteres i baggrunden. Indtil da kan den tilbagekaldte enhed i princippet læse det, den allerede havde (det kan ikke undgås), men intet nyt.

## 6. Lagerformat (K8 lag 2) — åbent og dokumenteret

Formatet er en del af exit-garantien: alt i dette afsnit skal kunne læses med åbne værktøjer og personens (eller organisationens) CMK, uden EiraOS.

### 6.1 Layout i kontekst-hjemmet

```
<prefix>/
  context                  krypteret kontekst-post (§2)
  keys/devices/<device_id> CMK pakket til en enhed (HPKE)
  keys/recovery            CMK pakket til genoprettelse (kun personal)
  keys/org                 CMK pakket til organisationen (kun organisation)
  keys/devices.signed      liste over enhedernes offentlige nøgler, signeret (§8)
  blocks/<aa>/<block_id>   krypterede blokke
  manifests/<device_id>/<seq>  krypterede, signerede manifester, ét pr. synkroniseringspunkt
```

Alt er **kun tilføjelse**: en blok eller et manifest overskrives aldrig. Det gør synkronisering mod "dum" lagring sikker uden låse (§7).

**Lagerkrav (H-1, normativt):** skrivning til `blocks/…` og `manifests/…` SKAL være atomisk *opret-hvis-fraværende*. Et eksisterende objekt må aldrig overskrives, heller ikke med en ellers gyldig chiffertekst. Konkret:

- **S3:** `PutObject` med `If-None-Match: *`; svaret `412 Precondition Failed` betyder "findes allerede" og er ikke en fejl for en blok, men en fejl for et manifest (så har en anden skrevet samme `<device_id>/<seq>`).
- **WebDAV/HTTP:** `PUT` med `If-None-Match: *` (RFC 9110 §13.1.2) med samme betydning.
- Et hjem, der ikke kan garantere opret-hvis-fraværende, understøttes ikke. EiraOS tjekker det, når et hjem tilknyttes: skriv A til en prøvesti, skriv B til samme sti med `If-None-Match: *`, og læs tilbage. Kun svaret `412` *og* A ved tilbagelæsning godkender hjemmet. Ellers `E_CONTEXT_HOME_UNSUPPORTED`.

For blokke er konsekvensen af et overskrevet objekt begrænset (begge chiffertekster dekrypterer til samme klartekst, B-1), men for manifester ville det være omskrivning af historikken. Derfor gælder kravet begge.

### 6.2 Blokke

- Filer opdeles med FastCDC (min 256 KiB, gennemsnit 1 MiB, maks 4 MiB). Små filer er én blok.
- `block_id` = hex(HMAC-SHA256(K_id, klartekst)), hvor `K_id` = HKDF(CMK, `eira-ctx-blockid-v1`). Id'et bruges til adressering og deduplikering. Hjemmet kan ikke afgøre, om to kontekster har samme indhold.
- **Normativ regel (B-1):** `block_id` beregnes af præcis den klartekst, der krypteres i samme operation, i den funktion, der krypterer. Det må aldrig tages fra en filsti, metadata, et sekvensnummer, et tidligere id eller et argument fra kalderen. Krypteringsfunktionen tager kun klarteksten (og konteksten) som input og returnerer selv `block_id`.
- **Kryptering er ikke-deterministisk** (rev. 0.2). Hver kryptering, også af en blok med et kendt `block_id`, bruger frisk tilfældighed:

  ```
  salt       = 32 tilfældige bytes (CSPRNG)
  nonce      = 12 tilfældige bytes (CSPRNG)
  block_key  = HKDF-SHA256(CMK, salt, info = "eira-ctx-block-v2" ‖ block_id)
  aad        = "eira-ctx-block-v2" ‖ context_id ‖ block_id
  ciphertext = ChaCha20-Poly1305(block_key, nonce, klartekst, aad)
  blok       = version(1) ‖ salt(32) ‖ nonce(12) ‖ ciphertext
  ```

- **Hvorfor:** sikkerheden må ikke hvile på en implicit invariant. Rev. 0.1 brugte en nøgle afledt af `block_id` og en fast nonce. Det var korrekt, så længe `block_id` altid var HMAC af præcis den klartekst, der blev krypteret. Én implementeringsfejl (fx et id taget fra en sti eller et sekvensnummer i stedet for indholdet) ville give genbrug af nøgle og nonce i ChaCha20-Poly1305 (RFC 8439 §4), som afslører klartekst og tillader forfalskning. Med frisk salt og nonce pr. kryptering er hver nøgle brugt én gang, uanset hvordan id'et dannes.
- **AAD** binder chifferteksten til kontekst og blok, så en blok ikke kan flyttes til en anden kontekst eller et andet id uden at dekrypteringen fejler.
- **Ved læsning** genberegnes HMAC af klarteksten og sammenlignes med `block_id`. Afvigelse er `E_CONTEXT_INTEGRITY`.
- **Deduplikering** sker på `block_id`: findes blokken allerede i hjemmet, uploades den ikke igen. To enheder, der samtidig uploader samme blok, giver to gyldige chiffertekster under samme id; den først skrevne bevares (kun tilføjelse), og begge dekrypterer til samme klartekst.
- Biblioteker: ChaCha20-Poly1305 og HKDF-SHA256 findes i alle gængse biblioteker (også `cryptography`, som `app/fleet/e2ee.py` bruger), så formatet kan læses med åbne værktøjer (exit-garantien).

### 6.3 Manifester

Et manifest beskriver kontekstens tilstand set fra én enhed på ét tidspunkt:

```json
{
  "eira_manifest": "1",
  "context_id": "ctx_…", "device_id": "…", "seq": 42, "parents": ["<device>/<seq>", "…"],
  "issued_at": "…",
  "files": [{"path": "Referater/2026-11-20.odt", "blocks": ["…"], "size": 48213, "mtime": "…", "deleted": false}],
  "documents": [{"id": "graph", "automerge_heads": ["…"], "blocks": ["…"]}],
  "merkle_root": "…"
}
```

- `merkle_root` er roden af et Merkle-træ over alle `block_id` i manifestet. Det beviser, at intet er udeladt eller byttet.
- Manifestet krypteres med samme konstruktion som en blok (§6.2, frisk salt og nonce), med `info`/`aad`-etiketten `eira-ctx-manifest-v2` og manifestets sti (`<device_id>/<seq>`) i stedet for `block_id`. Det signeres med enhedens signeringsnøgle (ECDSA P-256, §5.0) over chifferteksten. En læser godtager kun manifester fra enheder på den signerede enhedsliste (§8).
- `parents` peger på de manifester, enheden havde set; det giver en DAG, som sammenfletning bygger på (§7).

### 6.4 Strukturerede data

Universet (graphd), samtaler og andre strukturerede data er Automerge-dokumenter (K8 lag 3). Deres ændringer gemmes som blokke og refereres fra `documents` i manifestet. Formatet er Automerges eget, åbent dokumenterede binære format.

### 6.5 Referenceværktøj

`eira-context-export` (separat, åbent repo) læser et kontekst-hjem med en CMK eller genoprettelsesnøgle og skriver almindelige filer og JSON-eksport af Automerge-dokumenterne. Det er en del af leverancen, ikke et senere ønske.

### 6.6 Præciseringer fra implementeringen (F2.1)

Disse detaljer var ikke fastlagt præcist nok til at implementere efter. De ændrer ingen semantik; de gør formatet entydigt, så det kan genimplementeres (exit-garantien). Referencen er `app/context/` og `tools/eira-context-export/`; vektorerne ligger i `tests/vectors/context/`.

- **Bytes i nøgleafledning og AAD:** alle strenge er UTF-8 og sættes sammen uden separator. `block_id` er 64 små hex-tegn, og `context_id` har fast længde, så sammensætningen er entydig. `K_id` = HKDF-SHA256(CMK, intet salt, `eira-ctx-blockid-v1`). Versionsbyten er `0x02`.
- **Manifestets kuvert:** manifestet er kanonisk JSON (sorterede nøgler, separatorerne `,` og `:`, UTF-8), forseglet som en blok med etiketten `eira-ctx-manifest-v2` og navnet `<device_id>/<seq>`. Det gemte objekt er `længde(sig)` (2 bytes big-endian) ‖ `sig` ‖ forseglingen, hvor `sig` er DER ECDSA-P256-SHA256 over forseglingen. Et manifest beskriver hele tilstanden fra den enhed (ikke en ændring), og det har præcis felterne i §6.3, intet andet (`specs/schemas/eira-context-manifest-1.schema.json`).
- **Merkle-træet:** blade = SHA-256(`0x00` ‖ `block_id`-bytes) i manifestets rækkefølge (alle filers blokke i filrækkefølge, derefter dokumenternes); knuder = SHA-256(`0x01` ‖ venstre ‖ højre); en ulige knude føres uændret op; roden af ingen blokke er SHA-256 af den tomme streng. Rækkefølgen tæller, så blokke ikke kan byttes.
- **Kontekst-posten** (`context`) forsegles med etiketten `eira-ctx-record-v2` og navnet `context` (`specs/schemas/eira-context-record-1.schema.json`).
- **Enhedslisten** (`keys/devices.signed`) er JSON: `{"list": {…}, "signer": "<device_id>" | "org", "signature": "<base64 DER>"}`, hvor signaturen dækker kanonisk JSON af `list` (`specs/schemas/eira-context-devices-1.schema.json`). `device_id` = SHA-256 af den offentlige nøgle i DER SubjectPublicKeyInfo. En organisationskontekst's liste signeres af organisationens nøgle; en personlig konteksts af en enhed på den gældende liste; den første liste i en personlig kontekst godtages, hvis en enhed på listen selv har signeret den. En ny liste skal have et højere `version`.
- **Stier i manifester** er relative og må ikke indeholde `..`, tomme segmenter, `\` eller NUL. En læser afviser andre (eksportværktøjet skriver aldrig uden for sin uddatamappe).
- **FastCDC** bruger en fast gear-tabel: `GEAR[i]` = de første 8 bytes (big-endian) af SHA-256(`eira-ctx-gear-v1` ‖ i), normalisering niveau 2 omkring 2^20. Grænserne har kun betydning for deduplikering; en læser sætter blot en fils blokke sammen.

## 7. Synkronisering

- **Skrive:** en åben kontekst lægger nye blokke op, derefter et nyt manifest med `seq` + 1. Fejler noget undervejs, er der højst efterladt ubrugte blokke.
- **Læse:** enheden henter nye manifester fra alle enheder på enhedslisten og fletter dem:
  - **Filer:** samme sti ændret i to manifester, der ikke er hinandens forfædre, giver begge versioner og et synligt **konfliktobjekt** i universet. Intet overskrives stille (K4).
  - **Strukturerede data:** Automerge fletter deterministisk.
  - **Sletning:** en sletning vinder kun over versioner, den har set (via `parents`).
- **Versioner og papirkurv** (besluttet, O-3): versioner tyndes ud over tid: alle versioner det første døgn, én pr. dag i den første måned, derefter én pr. uge, inden for `policy.versions.keep_days`. Slettede filer ligger i papirkurven i `trash_days`. Standard 30 dage for begge; organisationer sætter egne værdier via Fleet.
- **Oprydning:** blokke, som ingen bevaret version eller fil i papirkurven peger på, kan slettes af en enhed med skriveret.
- **Versionshistorik er ikke arkivering:** en organisations pligt til journalisering og arkivering ligger i dens egne systemer (fx ESDH), ikke i kontekstens synkronisering.
- **Offline:** alt foregår mod den lokale kopi; synkronisering sker, når der er net (K10).

## 8. Enheder og tilbagekaldelse

- `keys/devices.signed` er listen over enheder, der må læse og skrive konteksten. Hver post har enhedens offentlige nøgler og `key_protection` (`"tpm"` eller `"file"`, §5.0); en organisationskontekst godtager kun `"tpm"`. Listen signeres af:
  - for `organisation`: organisationens nøgle via Fleet (samme rod- og driftsnøgler som RIGHTS-SET §3.1);
  - for `personal`: en af personens eksisterende enheder (første enhed signerer sig selv ved oprettelse; genoprettelse (ADR-0005 K5) kan starte en ny liste).
- **Tilbagekaldelse:** enheden fjernes fra listen, dens `keys/devices/<device_id>` slettes, og CMK roteres (§5.5). Næste gang den tilbagekaldte enhed er online, ser den, at den ikke er på listen, og fjerner konteksten (§4). Er den offline, låses konteksten senest, når `max_offline_days` udløber.

### 8.1 Udmelding (en enhed fjerner sig selv)

- En enhed må signere en enhedsliste, hvis den eneste ændring er, at den selv er fjernet. Kontekstens hjem og de øvrige enheder godtager en sådan liste, selv om enheden ikke ellers må ændre listen. Den kan kun formindske adgangen.
- Udmelding sker, når Fleet sender *tilbagekald enhed* (ADR-0005 K6, "Aflevering"), og når personen selv vælger at fjerne enheden. Enheden melder sig ud af alle sine kontekster, organisationens og de private, og går derefter til tilstanden *fjernet* (§4).
- CMK roteres af den næste af kontekstens øvrige enheder, der er online (§5.5). Den udmeldte enhed roterer ikke selv.
- Fleet får ikke oplyst, hvilke private kontekster enheden meldte sig ud af; kvitteringen til Fleet siger kun, at udmeldingen er gennemført.

## 9. ID-hjemmet (K11)

Specificeres i detaljer i en separat kontrakt (EIRA-ID-HOME). Denne kontrakt fastlægger kun, hvad det må indeholde:

```json
{
  "eira_id_home": "1",
  "account": "<pseudonym, afledt af eID pr. tjeneste>",
  "devices": ["<offentlig P-256-signeringsnøgle>", "…"],
  "sealed": "<blok krypteret med personens nøgle: liste over {context_id, home} for personens kontekster>"
}
```

- `sealed` kan kun åbnes på personens enheder. Eira ser en uigennemsigtig blok og dens størrelse.
- Ingen `display_name`, ingen organisationsnavne, ingen CMK i nogen form.
- På en lukket organisationsenhed bruges ID-hjemmet ikke (K11): listen kommer fra Fleet.

## 10. Fleet og rettigheder

**Fleet bærer styring, ikke brugerdata** (besluttet af ejer). Brugerdata synkroniseres udelukkende gennem kontekstens hjem (§6, §7) med én CMK pr. kontekst, rotation og tilbagekaldelse (§5.5, §8). Den nuværende Fleet-synkronisering (`sync.*` i `eira-fleetd`) bruger én fælles nøgle for alle enheder uden afgrænsning pr. kontekst og uden rotation. Den må ikke bære brugerdata i 1.0 og udfases for brugerdata, når kontekst-synkroniseringen findes. Fleet bærer kun det, der står i dette afsnit: kontekst-poster, enhedslister, politik, rettighedssæt og enhedens tilstand.

Fleet leverer pr. organisationskontekst: kontekst-posten (§2), enhedslisten (§8), politik (`max_offline_days`, `glimt_allowed`, `devices`) og hjemmet (K3), samt for enheder: `device_mode` = `closed` | `open` (K6).

**Revision krævet af RIGHTS-SET:** et rettighedssæt bindes i dag til (`tenant_id`, `device_id`). Med kontekster skal det kunne bindes til (`tenant_id`, `context_id`) og gælde på enhver enhed på kontekstens enhedsliste. Gaten vælger sæt efter den kontekst, kaldet kommer fra: peer-UID'en fra `SO_PEERCRED` slås op i `eira-contextd`s lokale tabel (§1), og sættet vælges på `context_id`. UID'en bruges aldrig selv som nøgle i et rettighedssæt. Revisionen af RIGHTS-SET er et separat dokument.

**Private kontekster på en åben organisationsenhed** (ADR-0005 O-9): organisationens sæt gælder kun organisationens kontekster, og pakkens standardsæt gælder ikke på en enrolled enhed (EIRA-FLEET-RIGHTS-API §3.3, `awaiting_managed_set`). Besluttet (ADR-0005 O-9): den får pakkens standardsæt uden `system:`-handlinger på `device:local`. Fleet udsteder intet for private kontekster og må ikke få oplyst, hvilke der findes på enheden; det ser kun `device_mode`. Indtil revisionen findes, har en privat kontekst på en enrolled enhed ingen rettigheder til gate-handlinger.

## 11. Glimt (ADR-0006 L5)

- Hver åben kontekst må, hvis `policy.glimt_allowed`, sende til skallen:
  - **aktivitet:** `{context_id, count, since}`;
  - **kalender** (kun hvis `policy.glimt_level` = `calendar`): `{context_id, start, end, place}`, hvor `place` er en kort stedangivelse uden personoplysninger.
- Skallen slår `display_name` op i sin egen krypterede cache, der kun findes, mens personen er logget ind.
- Intet andet felt er tilladt. Skallen afviser beskeder med andre felter, og kalender-glimt fra en kontekst med `glimt_level` = `activity`.
- En låst kontekst sender ikke glimt (dens processer kører ikke). Glimt fra låste kontekster findes ikke i 1.0 (O-4): det ville kræve, at hjemmet kan tælle nye manifester og dermed ser personens aktivitetsmønstre.

### 11.1 Overfør glimt (ADR-0005 K12)

Skallen kan på personens anmodning oprette en begivenhed i en anden åben kontekst ud fra et kalender-glimt. Kun `start`, `end` og `place` fra glimtet overføres; titlen indtastes af personen. Handlingen går gennem gaten i målkonteksten. Kildekonteksten får ingen besked og ingen data retur.

## 11a. Værgestyret kontekst: håndhævelse (ADR-0005 K12)

En kontekst med `governance.source = guardian` har et regeldokument signeret af værgernes enhedsnøgler (samme signaturform som enhedslisten, §8). Det ligger i familiens hjem. Reglerne håndhæves af kernen og af komponenter, EiraOS ejer, aldrig af skallen alene. Barnets kontekst er en Linux-bruger (§3), og al håndhævelse knytter sig til den:

| Regel | Håndhæves af |
|---|---|
| Tidsrum og sengetid | `eira-contextd` låser konteksten uden for tidsrummet (§4). Processerne stoppes |
| Webapps | Web App Manager starter kun tilladte (under 13) eller ikke-spærrede (13–17) webapps |
| Programmer | AppArmor-profil for kontekst-brugeren. Under 13: ingen terminal og kun tilladte programmer. Aldersmærkning fra programmernes AppStream-metadata (OARS) kan bruges som udgangspunkt |
| Installation | Kontekst-brugere kan aldrig installere systemprogrammer |
| Internetfiltrering | nftables-regler pr. kontekst-brugerens UID tvinger al DNS gennem enhedens filtrerende resolver og spærrer kendte krypterede DNS-endpoints (DoH/DoT) uden om den. Gælder alle programmer, ikke kun webapps |
| Køb og handlinger med konsekvens | Gaten, med værgens godkendelse som andet sæt øjne |

**Internetfiltrering: kilde.** Filterkilden er udskiftelig (ADR-0004 D1) og vælges i reglerne:

- **Standard (besluttet af ejer):** DNS4EU Public Service, variant *Protective + Child Protection* (EU-medfinansieret, drevet af et europæisk konsortium), altid over krypteret DoH/DoT. Bruges fra 1.0.
  - **Afklaring i gang:** DNS4EU's vilkår beskriver den offentlige tjeneste som rettet mod den enkelte borger og ikke kommerciel brug. At barnets enhed forespørger direkte på familiens vegne afklares med operatøren. Viser svaret, at det ikke er tilladt, skiftes standarden til alternativet nedenfor uden ændring af reglernes format.
- **Alternativ uden ekstern forespørgsel:** lokal filtrering i enhedens resolver med åbne kategorilister (fx UT1-listerne fra Université Toulouse Capitole, som bruges bredt i skoler). Licens og opdateringsvej skal afklares. Kan vælges i reglerne allerede i 1.0.
- **Begrænsning, der skal stå i brugerfladen:** DNS-filtrering spærrer domæner, ikke indhold inden for et tilladt domæne.

**Brugsoverblik.** Barnets enhed skriver et overblik (tid pr. dag, hvilke webapps, programmer og kontekster) krypteret til værgernes nøgler i familiens hjem. Det indeholder aldrig indhold.

**Værgens webvisning** (besluttet af ejer). Værger skal kunne bruge deres nuværende telefon: de ser overblikket og ændrer reglerne fra en browser uden at installere noget:

- Webvisningen er en statisk webapp. Den henter de krypterede data direkte fra familiens hjem og dekrypterer dem **i værgens browser**. Den, der leverer webappen (Eira eller familien selv), kan ikke læse reglerne eller overblikket (ID-hjemmet, K11, berøres ikke).
- Værgens nøgle i browseren afledes af en passkey via WebAuthn PRF-udvidelsen, så ingen adgangskode eller nøglefil skal gemmes på telefonen.
- Ændrede regler signeres i browseren med en nøgle, der er registreret som en af værgens enheder (§8).

## 12. Fejlkoder

| Kode | Hvornår |
|---|---|
| `E_CONTEXT_UNKNOWN` | Konteksten findes ikke for denne person/enhed |
| `E_CONTEXT_LOCKED` | Handling kræver en åben kontekst |
| `E_CONTEXT_OFFLINE_EXPIRED` | Offline-perioden er udløbet; online-oplåsning kræves (§4.2) |
| `E_CONTEXT_DEVICE_REVOKED` | Enheden er ikke på kontekstens enhedsliste (§8) |
| `E_CONTEXT_IDENTITY_REQUIRED` | Konteksten kræver login med en anden identitet (§4.1) |
| `E_CONTEXT_HOME_UNREACHABLE` | Hjemmet svarer ikke; arbejder videre lokalt (ikke en fejl for brugeren, men logges) |
| `E_CONTEXT_INTEGRITY` | Manifest med ugyldig signatur, ukendt enhed, Merkle-afvigelse eller en sti (`<device_id>/<seq>`), der allerede findes. Blok, der ikke kan dekrypteres (AEAD-fejl), eller hvis klartekst ikke matcher `block_id`. Objektet ignoreres og hændelsen auditeres |
| `E_CONTEXT_HOME_UNSUPPORTED` | Hjemmet kan ikke garantere opret-hvis-fraværende (§6.1) og afvises ved tilknytning |
| `E_CONTEXT_POLICY` | Fleet-politik forbyder handlingen (fx åben kontekst på en lukket enhed) |

## 12a. Invarianter, testplanen skal dække

Testplanen (separat dokument) skal have mindst én test pr. invariant, og hver test skal fejle, hvis invarianten brydes (mutationstjek):

| # | Invariant | Afsnit |
|---|---|---|
| B-1 | `block_id` beregnes af præcis den krypterede klartekst. Testene skal mindst dække: (a) klartekst → `block_id` → kryptér → dekryptér → samme `block_id`; (b) ændret chiffertekst → AEAD-fejl; (c) en blok, der læses under et andet id end HMAC'en af dens klartekst → `E_CONTEXT_INTEGRITY`; (d) krypteringsfunktionens signatur kan ikke modtage et id fra kalderen (statisk tjek); (e) samme klartekst krypteret to gange → samme `block_id`, forskellig salt, nonce og chiffertekst | §6.2 |
| B-2 | Salt og nonce er friske pr. kryptering: to krypteringer af samme klartekst giver forskellige chiffertekster | §6.2 |
| B-3 | AAD binder til `context_id` og `block_id`: en blok flyttet til en anden kontekst eller et andet id kan ikke dekrypteres | §6.2 |
| H-1 | Opret-hvis-fraværende: to enheder uploader samtidig hver sin uafhængigt krypterede udgave af samme blok; det lagrede objekt ændres ikke efter første skrivning, og begge udgaver dekrypterer til samme klartekst. Et manifest med et eksisterende `<device_id>/<seq>` afvises. Et hjem uden opret-hvis-fraværende afvises ved tilknytning | §6.1 |
| M-1 | Et manifest fra en enhed uden for den signerede enhedsliste, eller med Merkle-afvigelse, ignoreres og auditeres | §6.3, §8 |
| S-1 | Samtidige ændringer af samme fil giver to versioner og et konfliktobjekt; intet overskrives | §7 |
| U-1 | Linux-UID forekommer aldrig i data, manifester, protokolbeskeder, audit uden for enheden eller rettighedssæt | §1 |
| I-1 | En kontekst-bruger kan hverken se processer, læse filer, signalere processer, ptrace, forbinde til D-Bus eller Wayland-socket for en anden kontekst; skal-brugeren kan intet af det over for nogen kontekst | §3.3 |
| O-1 | En udløbet offline-periode kan ikke forlænges ved at stille uret tilbage | §4.2 |
| G-1 | Skallen afviser glimt med andre felter end de tilladte, og kalender-glimt fra kontekster med `glimt_level` = `activity` | §11 |
| E-1 | Brug af en escrow-nøgle kræver to forskellige nøgleforvaltere og giver en audithændelse og besked til medarbejderen | §5.4 |
| V-1 | En værgestyret kontekst låses uden for tidsrummet, og dens DNS kan ikke gå uden om filtret | §11a |
| X-1 | `eira-context-export` læser et kontekst-hjem med kun CMK og uden EiraOS (exit-garantien) | §6.5 |
| R-1 | En tilbagekaldt enhed kan ikke læse noget, der er skrevet efter rotationen; dens pakkede nøgle er fjernet; den fjerner konteksten, næste gang den er online, og låser den senest ved `max_offline_days`, hvis den er offline | §5.5, §8 |
| A-1 | Gendannelse eller kloning af en enheds data giver aldrig autoritet. En klonet disk på anden hardware kan hverken åbne kontekster, signere manifester, forbinde til Fleet (mTLS), få nye rettighedssæt eller bruge en samtykkenøgle, heller ikke hvis angriberen kender diskens gendannelsesnøgle. Et allerede cachet rettighedssæt gælder på klonen som på en enhed offline, til det udløber (RIGHTS-SET §5.1); det er den tilbageværende risiko og skal stå i trusselsmodellen. Autoritet på en ny enhed opstår kun ad den normale vej (§4.1, §8) | §5.0, §5.2, §8 |
| F-1 | En glemt kontekst efterlader intet læsbart på enheden: ingen forsegling i TPM'en, ingen LUKS-fil, ingen Linux-bruger, ingen kobling `context_id` → UID og intet `display_name` eller indhold uden for kontekstens volumen (journal, swap, `/tmp`, skallens cache) | §4.3 |

## 13. Uden for scope

- Root på en kørende enhed, en kompromitteret kerne (som EIRA-CONSENT-AGENT §9).
- Web App Manager, livets indbakke, adapterkontrakten (bygger på denne kontrakt).
- ID-hjemmets protokol og genoprettelsestjenesten i detaljer (EIRA-ID-HOME).
- EiraOS på telefonen (ADR-0006 L4b).

## 14. Afklaret (11. november 2026)

- **O-1 UID:** kun lokal; `context_id` er identifikatoren (§1, §3.1).
- **O-2 Glemsel:** 30 dage som standard, 1–90 dage (§4.3).
- **O-3 Versioner:** udtynding, 30 dage og 30 dages papirkurv som standard (§7).
- **O-4 Glimt fra låste kontekster:** ikke i 1.0 (§11).
- **O-5 Lokal kryptering:** LUKS2 pr. kontekst over fuld diskkryptering (§5.3).
- **O-6 Organisationens escrow:** én nøgle pr. kontekst i Fleet med nøgleforvalter, fire øjne og besked til medarbejderen (§5.4).

Kontrakten har ingen åbne spørgsmål. Testplanen følger efter accept.
