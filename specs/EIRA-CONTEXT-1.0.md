# EIRA Context 1.0 — kontekster, lagring og synkronisering

**Status:** Udkast v0.1 til ejerens accept. **Ikke normativ**, før det er accepteret. Testplanen er et separat trin efter accept.
**Version:** 0.1 (11. november 2026)
**Grundlag:** [ADR-0005](../docs/decisions/ADR-0005-kontekster-og-datas-hjem.md) (K1–K11), [ADR-0004](../docs/decisions/ADR-0004-gui-arkitektur-vendor-neutral.md) D1, [ADR-0006](../docs/decisions/ADR-0006-livets-indbakke.md) L5 (glimt)
**Berører:** ny `eira-contextd` (rod-formidler), `identityd`, gaten, graphd, samtalelaget, den neutrale skal, compositoren, `eira-governance-agent`/Fleet, RIGHTS-SET (revision, §10)

Kontrakten gør ADR-0005 konkret: hvad en kontekst er som data, hvordan den lever på en enhed, hvordan dens data krypteres, gemmes og synkroniseres, og hvad ID-hjemmet indeholder. Den definerer ikke Web App Manager, livets indbakke eller adapterkontrakten; de bygger oven på den.

---

## 1. Begreber og identifikatorer

| Begreb | Identifikator | Form |
|---|---|---|
| Kontekst | `context_id` | `ctx_` + 26 tegn base32 (128 bit tilfældigt). Ændres aldrig |
| Identitet | `identity` | `did:eira:<provider-id>.<subjekt>` (EIRA-IDENTITY) |
| Enhed | `device_id` | Fingeraftryk (SHA-256) af enhedens Ed25519-signeringsnøgle |
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
    "devices": "personal_and_managed"
  },
  "created_at": "…"
}
```

| Felt | Regel |
|---|---|
| `kind` | `organisation` (styret af en organisations Fleet) eller `personal` (styret af personen) |
| `identity.provider_id` | Udbyderen, personen logger ind med for at låse konteksten op. En bestyrelseskontekst uden egen udbyder bruger personens private udbyder (ADR-0005, "Begreber") |
| `governance.source` | `fleet` (rettigheder og politik fra organisationen) eller `person` |
| `home` | Kontekst-hjemmet (K3). `type` er `s3` eller `webdav` (K8 lag 1). `prefix` er et pseudonym, så hjemmet ikke ser kontekstens navn |
| `policy.max_offline_days` | K4/K10. Standard 7 for `personal`. Sat af Fleet for `organisation` |
| `policy.glimt_allowed` | ADR-0006 L5. En organisation kan forbyde glimt fra sin kontekst |
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

### 3.2 Hvad hver kontekst-bruger har

- Eget hjemmekatalog (`/var/lib/eira/contexts/<kort-id>/`, mode `0700`), krypteret i hvile med kontekstens nøgle (§5.3).
- Egen `systemd --user`-instans (startet af `eira-contextd` via `user@<uid>.service`), egen D-Bus-sessionsbus og egen PipeWire-instans.
- **Egen Wayland-socket**, oprettet af compositoren med `wp_security_context_v1` og mærket med `context_id`. Compositoren ved dermed, hvilken kontekst hvert vindue tilhører (ADR-0004 D6). Ingen kontekst-bruger kan forbinde til compositorens hovedsocket.
- Lyd ud og notifikationer går gennem en snæver formidler i skallen. Udklipsholder og fil-deling mellem kontekster findes ikke (K2, ADR-0006 L5).

### 3.3 Grænser, der testes

En kontekst-bruger kan ikke læse en anden konteksts filer, sende signaler til dens processer, ptrace dem, forbinde til dens D-Bus eller Wayland-socket eller læse dens udklipsholder. Skal-brugeren kan ingen af delene over for nogen kontekst.

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

1. Personen logger ind i skallen med en identitet (EIRA-IDENTITY).
2. Skallen finder personens kontekster: fra ID-hjemmet (§9) eller, på en lukket organisationsenhed, fra Fleet (K11).
3. For hver kontekst, personen vælger at åbne: `eira-contextd` opretter kontekst-brugeren, henter den krypterede post og kontekstens nøgle **pakket til denne enhed** (§5.1), forsegler nøglen i TPM'en og starter synkronisering.
4. Kræver konteksten en anden identitet end den, der blev brugt ved log ind (fx arbejde), logger personen ind med den, før konteksten åbnes.

### 4.2 Oplåsning offline (K4)

En kontekst i tilstanden **låst** kan låses op uden net, hvis:
- dens nøgle er forseglet i enhedens TPM, og forseglingen kræver personens lokale oplåsning (PIN eller biometri via TPM-politik); og
- seneste verificerede online-kontakt med kontekstens hjem og udbyder ikke er ældre end `policy.max_offline_days`.

Tiden måles som i RIGHTS-SET §4.1 ("uret må ikke kunne skrues tilbage"): seneste kendte tid fra hjemmets signerede svar er en nedre grænse, og et lokalt ur, der går baglæns, forlænger ikke perioden. Er perioden udløbet, kan konteksten kun åbnes online.

### 4.3 Glemsel (K11 / O-5 i ADR-0005)

En kontekst, der ikke har været åben i 30 dage (forslag, O-2), fjernes fra enheden. Data findes stadig i kontekstens hjem. Enheden husker intet læsbart om konteksten bagefter.

## 5. Nøgler

### 5.1 Nøglehierarki pr. kontekst

| Nøgle | Hvad | Hvor |
|---|---|---|
| **CMK** (context master key) | 256 bit tilfældigt. Åbner kontekstens data | Aldrig i klartekst uden for en åben kontekst på en enhed |
| CMK pakket til enhed | CMK krypteret til enhedens X25519-nøgle (HPKE, RFC 9180, `DHKEM(X25519)`/`HKDF-SHA256`/`ChaCha20Poly1305`) | `keys/devices/<device_id>` i kontekstens hjem |
| CMK pakket til genoprettelse | CMK krypteret til genoprettelsestjenestens frigivelse (K5, §7) | `keys/recovery` i kontekstens hjem (kun `personal`) |
| CMK pakket til organisationen | CMK krypteret til organisationens escrow-nøgle | `keys/org` i kontekstens hjem (kun `organisation`, K5) |
| Afledte nøgler | HKDF-SHA256 fra CMK med faste etiketter (§6) | Afledes ved brug, gemmes ikke |

Enhedens X25519-nøgle og Ed25519-signeringsnøgle ligger i TPM'en eller er forseglet med den.

### 5.2 Forsegling på enheden

Når en kontekst åbnes første gang på en enhed, forsegles CMK i TPM'en til (a) enhedens målte opstart (PCR-politik, samme kæde som RIGHTS-SET-ankeret) og (b) personens lokale oplåsning. Låses konteksten, fjernes CMK fra hukommelsen; kun forseglingen bliver.

### 5.3 Lokal kopi i hvile

Kontekst-brugerens hjemmekatalog er krypteret med en nøgle afledt af CMK (`eira-ctx-local-v1`), fx via fscrypt-politik pr. katalog. Uden CMK kan selv root ikke læse en låst kontekst på en slukket enhed. (En åben kontekst på en kørende enhed er ikke beskyttet mod root, jf. trusselsmodellen i EIRA-CONSENT-AGENT §9.)

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

### 6.2 Blokke

- Filer opdeles med FastCDC (min 256 KiB, gennemsnit 1 MiB, maks 4 MiB). Små filer er én blok.
- `block_id` = hex(HMAC-SHA256(K_id, klartekst)), hvor `K_id` = HKDF(CMK, `eira-ctx-blockid-v1`). Hjemmet kan ikke afgøre, om to kontekster har samme indhold.
- Kryptering: ChaCha20-Poly1305 med nøgle HKDF(CMK, `eira-ctx-block-v1` ‖ `block_id`) og nonce på 12 nulbytes. Nøglen er unik pr. indhold, så nonce-genbrug med forskelligt klartekst kan ikke forekomme. Valgt for at følge `app/fleet/e2ee.py` og fordi det findes i alle gængse biblioteker.

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
- Manifestet er krypteret som en blok og signeret med enhedens Ed25519-nøgle. En læser godtager kun manifester fra enheder på den signerede enhedsliste (§8).
- `parents` peger på de manifester, enheden havde set; det giver en DAG, som sammenfletning bygger på (§7).

### 6.4 Strukturerede data

Universet (graphd), samtaler og andre strukturerede data er Automerge-dokumenter (K8 lag 3). Deres ændringer gemmes som blokke og refereres fra `documents` i manifestet. Formatet er Automerges eget, åbent dokumenterede binære format.

### 6.5 Referenceværktøj

`eira-context-export` (separat, åbent repo) læser et kontekst-hjem med en CMK eller genoprettelsesnøgle og skriver almindelige filer og JSON-eksport af Automerge-dokumenterne. Det er en del af leverancen, ikke et senere ønske.

## 7. Synkronisering

- **Skrive:** en åben kontekst lægger nye blokke op, derefter et nyt manifest med `seq` + 1. Fejler noget undervejs, er der højst efterladt ubrugte blokke.
- **Læse:** enheden henter nye manifester fra alle enheder på enhedslisten og fletter dem:
  - **Filer:** samme sti ændret i to manifester, der ikke er hinandens forfædre, giver begge versioner og et synligt **konfliktobjekt** i universet. Intet overskrives stille (K4).
  - **Strukturerede data:** Automerge fletter deterministisk.
  - **Sletning:** en sletning vinder kun over versioner, den har set (via `parents`).
- **Oprydning:** blokke, som intet manifest i de seneste N versioner pr. enhed peger på, kan slettes af en enhed med skriveret. N er politik (O-3).
- **Offline:** alt foregår mod den lokale kopi; synkronisering sker, når der er net (K10).

## 8. Enheder og tilbagekaldelse

- `keys/devices.signed` er listen over enheder, der må læse og skrive konteksten. Den signeres af:
  - for `organisation`: organisationens nøgle via Fleet (samme rod- og driftsnøgler som RIGHTS-SET §3.1);
  - for `personal`: en af personens eksisterende enheder (første enhed signerer sig selv ved oprettelse; genoprettelse (ADR-0005 K5) kan starte en ny liste).
- **Tilbagekaldelse:** enheden fjernes fra listen, dens `keys/devices/<device_id>` slettes, og CMK roteres (§5.5). Næste gang den tilbagekaldte enhed er online, ser den, at den ikke er på listen, og fjerner konteksten (§4). Er den offline, låses konteksten senest, når `max_offline_days` udløber.

## 9. ID-hjemmet (K11)

Specificeres i detaljer i en separat kontrakt (EIRA-ID-HOME). Denne kontrakt fastlægger kun, hvad det må indeholde:

```json
{
  "eira_id_home": "1",
  "account": "<pseudonym, afledt af eID pr. tjeneste>",
  "devices": ["<offentlig Ed25519-nøgle>", "…"],
  "sealed": "<blok krypteret med personens nøgle: liste over {context_id, home} for personens kontekster>"
}
```

- `sealed` kan kun åbnes på personens enheder. Eira ser en uigennemsigtig blok og dens størrelse.
- Ingen `display_name`, ingen organisationsnavne, ingen CMK i nogen form.
- På en lukket organisationsenhed bruges ID-hjemmet ikke (K11): listen kommer fra Fleet.

## 10. Fleet og rettigheder

Fleet leverer pr. organisationskontekst: kontekst-posten (§2), enhedslisten (§8), politik (`max_offline_days`, `glimt_allowed`, `devices`) og hjemmet (K3), samt for enheder: `device_mode` = `closed` | `open` (K6).

**Revision krævet af RIGHTS-SET:** et rettighedssæt bindes i dag til (`tenant_id`, `device_id`). Med kontekster skal det kunne bindes til (`tenant_id`, `context_id`) og gælde på enhver enhed på kontekstens enhedsliste. Gaten vælger sæt efter den kontekst, kaldet kommer fra (kontekst-brugerens UID → `context_id`). Revisionen af RIGHTS-SET er et separat dokument.

## 11. Glimt (ADR-0006 L5)

- Hver åben kontekst må, hvis `policy.glimt_allowed`, sende til skallen: `{context_id, count, since}`. Skallen slår `display_name` op i sin egen krypterede cache, der kun findes, mens personen er logget ind.
- Intet andet felt er tilladt. Skallen afviser beskeder med andre felter.
- En låst kontekst sender ikke glimt (dens processer kører ikke). Glimt fra låste kontekster findes ikke i 1.0 (O-4): det ville kræve, at hjemmet kan tælle nye manifester og dermed ser personens aktivitetsmønstre.

## 12. Fejlkoder

| Kode | Hvornår |
|---|---|
| `E_CONTEXT_UNKNOWN` | Konteksten findes ikke for denne person/enhed |
| `E_CONTEXT_LOCKED` | Handling kræver en åben kontekst |
| `E_CONTEXT_OFFLINE_EXPIRED` | Offline-perioden er udløbet; online-oplåsning kræves (§4.2) |
| `E_CONTEXT_DEVICE_REVOKED` | Enheden er ikke på kontekstens enhedsliste (§8) |
| `E_CONTEXT_IDENTITY_REQUIRED` | Konteksten kræver login med en anden identitet (§4.1) |
| `E_CONTEXT_HOME_UNREACHABLE` | Hjemmet svarer ikke; arbejder videre lokalt (ikke en fejl for brugeren, men logges) |
| `E_CONTEXT_INTEGRITY` | Manifest med ugyldig signatur, ukendt enhed eller Merkle-afvigelse. Manifestet ignoreres og hændelsen auditeres |
| `E_CONTEXT_POLICY` | Fleet-politik forbyder handlingen (fx åben kontekst på en lukket enhed) |

## 13. Uden for scope

- Root på en kørende enhed, en kompromitteret kerne (som EIRA-CONSENT-AGENT §9).
- Web App Manager, livets indbakke, adapterkontrakten (bygger på denne kontrakt).
- ID-hjemmets protokol og genoprettelsestjenesten i detaljer (EIRA-ID-HOME).
- EiraOS på telefonen (ADR-0006 L4b).

## 14. Åbne spørgsmål

- **O-1 UID-interval** for kontekst-brugere. Forslag: et dedikeret interval uden kollision med systemd (dynamiske brugere 61184–65519, homed 60001–60513, containere fra 524288). Skal verificeres mod Ubuntu 26.04 og værktøjer, der ikke tåler UID'er over 65535.
- **O-2 Glemselsfrist** for ubrugte kontekster (forslag: 30 dage) og om personen kan ændre den.
- **O-3 Oprydning af blokke:** hvor mange manifestversioner pr. enhed der bevares (versionshistorik vs. lagerforbrug).
- ~~**O-4 Glimt fra låste kontekster.**~~ Besluttet af ejer: nej i 1.0. Kun åbne kontekster viser glimt (§11).
- **O-5 fscrypt eller andet** til lokal kryptering i hvile (§5.3), og samspil med TPM-forsegling.
- ~~**O-6 Organisationens escrow.**~~ Besluttet af ejer: én nøgle pr. kontekst, opbevaret i Fleet, brugt af rollen nøgleforvalter med fire øjne og besked til medarbejderen (§5.4).
