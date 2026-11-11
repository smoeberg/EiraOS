# EIRA Context 1.0 — testplan

**Status:** Accepteret af ejer 11. november 2026. Normativ for implementeringen af EIRA-CONTEXT.
**Grundlag:** [EIRA-CONTEXT-1.0](EIRA-CONTEXT-1.0.md) v0.3 (accepteret 11. november 2026), §12a.
**Formål:** Planen fastlægger, hvordan hver invariant i §12a bevises, og hvad der skal til, før en invariant må kaldes *verificeret*. Den skriver ingen kode. Implementeringen er næste trin.

---

## 0. Status

| Invariant | Tests | Implementeret | Verificeret |
|---|---|---|---|
| B-1 | T-B1-a … T-B1-f | Nej | Nej |
| B-2 | T-B2-a, T-B2-b | Nej | Nej |
| B-3 | T-B3-a … T-B3-c | Nej | Nej |
| H-1 | T-H1-a … T-H1-e | Nej | Nej |
| M-1 | T-M1-a … T-M1-e | Nej | Nej |
| S-1 | T-S1-a … T-S1-d | Nej | Nej |
| U-1 | T-U1-a, T-U1-b | Nej | Nej |
| I-1 | T-I1-0 … T-I1-j | Nej | Nej |
| O-1 | T-O1-a … T-O1-d | Nej | Nej |
| G-1 | T-G1-a … T-G1-d | Nej | Nej |
| E-1 | T-E1-a … T-E1-e | Nej | Nej |
| V-1 | T-V1-a … T-V1-d | Nej | Nej |
| X-1 | T-X1-a, T-X1-b | Nej | Nej |
| R-1 | T-R1-a … T-R1-d | Nej | Nej |
| F-1 | T-F1-a … T-F1-c | Nej | Nej |
| A-1 | T-A1-a … T-A1-g | Nej | Nej |

En invariant er **verificeret**, når alle dens tests består på det niveau, tabellerne angiver, *og* alle dens mutanter (§2) får mindst én af testene til at fejle.

## 1. Testniveauer

| Niveau | Hvad | Hvor | Kører |
|---|---|---|---|
| **N1 enhed** | Rene funktioner: kryptering, manifester, fletning, glimt-validering, offline-ur, escrow-regler. Ingen netværk, ingen root | `tests/context/` | CI-job `python-ci`, hver PR |
| **N2 lager** | Mod rigtige lagerservere i containere (S3 og WebDAV) og mod bevidst fejlbehæftede testservere | `tests/context/home/`, pytest-markør `home` | Nyt CI-job `context-home`, PR'er der rører kontekstkoden |
| **N3 VM** | Den installerede pakke i en VM på Ubuntu 26.04 med `eira-contextd`, `eira-labwc`, greetd og to åbne kontekster | Udvidelse af `vm-install-acceptance`; hver test skriver `EIRA-CI CTX <test-id> PASS\|FAIL` på seriekonsollen | `packaging-acceptance`, som i dag |

N3 tester **den installerede pakke**, ikke kildetræet, af samme grund som EIRA-CONSENT-AGENT §0.1: rettigheder, AppArmor, nftables og systemd-hærdning findes kun der.

## 2. Mutanter

Hver invariant har en eller flere håndskrevne **mutanter**: små patches, der bryder invarianten på en realistisk måde. De ligger i `tests/mutants/CTX-<id>.patch`. Scriptet `scripts/check-mutants.sh` anvender én mutant ad gangen, kører de tilhørende tests og fejler, hvis en mutant overlever. Det kører i `context-home`-jobbet på N1/N2 og manuelt (eller natligt) på N3.

Det er bevidst ikke et generelt mutationsværktøj. Mutanterne nedenfor er netop de fejl, kontrakten er skrevet for at forhindre.

## 3. Testvektorer

`tests/vectors/context/` indeholder faste vektorer, så formatet kan genimplementeres uden EiraOS (exit-garantien):

- `block-v2.json`: CMK, `context_id`, klartekst, forventet `block_id`, salt, nonce og den færdige blok. **Produceres af en uafhængig referenceimplementering i testen**, skrevet direkte mod `cryptography` (HKDF, HMAC, ChaCha20-Poly1305), ikke af EiraOS' egen kode. Produktets API tager aldrig salt eller nonce udefra (B-1 d).
- `block-v2-negative.json`: samme blok med én ændret byte i hhv. version, salt, nonce, chiffertekst og tag; samme blok med forkert `context_id`; samme blok under forkert `block_id`.
- `manifest-v2.json`: manifest med kendt Merkle-rod, krypteret og signeret, plus negative varianter (forkert signatur, ukendt enhed, udeladt blok).

Vektorerne bruges begge veje: EiraOS skal kunne dekryptere dem, og referenceimplementeringen skal kunne dekryptere det, EiraOS skriver.

## 4. Tests pr. invariant

### B-1 `block_id` beregnes af præcis den krypterede klartekst (§6.2)

| Test | Niveau | Trin | Forventet |
|---|---|---|---|
| T-B1-a | N1 | Klartekst → `encrypt_block` → (`block_id`, blok) → `decrypt_block(block_id, blok)` | Samme klartekst; `block_id` = HMAC-SHA256(K_id, klartekst) beregnet af referenceimplementeringen |
| T-B1-b | N1 | Ændr én byte i hver af salt, nonce, chiffertekst og tag (vektorer) | Hver giver `E_CONTEXT_INTEGRITY` (AEAD-fejl); ingen klartekst returneres, heller ikke delvist |
| T-B1-c | N1 | Referenceimplementeringen krypterer klartekst P med et `block_id`, der *ikke* er HMAC af P (simulerer en skriverfejl), med korrekt AAD | AEAD lykkes, men læsning giver `E_CONTEXT_INTEGRITY`, fordi HMAC af P ≠ `block_id` |
| T-B1-d | N1, statisk | `inspect.signature(encrypt_block)` og AST-gennemgang af alle kaldesteder i `app/` | Funktionen har kun parametrene klartekst og kontekst; ingen parameter hedder eller indeholder `id`, `salt`, `nonce` eller `key`; intet kaldested sender et id ind |
| T-B1-e | N1 | Kryptér samme klartekst to gange | Samme `block_id`; forskellig salt, nonce og chiffertekst |
| T-B1-f | N1 | Dekryptér `block-v2.json` med EiraOS; dekryptér EiraOS' output med referenceimplementeringen | Begge veje giver samme klartekst |

**Mutanter:** CTX-B1-1 `block_id` tages fra filstien; CTX-B1-2 `block_id` tages fra et sekvensnummer; CTX-B1-3 HMAC-tjekket ved læsning fjernes; CTX-B1-4 `encrypt_block` får en valgfri `block_id`-parameter.

### B-2 Frisk salt og nonce pr. kryptering (§6.2)

| Test | Niveau | Trin | Forventet |
|---|---|---|---|
| T-B2-a | N1 | 100 000 krypteringer af samme klartekst | Ingen gentaget salt, ingen gentaget nonce, ingen gentaget chiffertekst |
| T-B2-b | N1 | Erstat CSPRNG med en spion | Salt (32 bytes) og nonce (12 bytes) hentes fra `os.urandom`/`secrets` ved hvert kald; intet caches mellem kald |

**Mutanter:** CTX-B2-1 fast nonce; CTX-B2-2 salt genbruges pr. kontekst; CTX-B2-3 nonce afledes af `block_id`.

### B-3 AAD binder til `context_id` og `block_id` (§6.2)

| Test | Niveau | Trin | Forventet |
|---|---|---|---|
| T-B3-a | N1 | Dekryptér en blok fra kontekst A med kontekst B's `context_id` (samme CMK, for at isolere AAD) | `E_CONTEXT_INTEGRITY` |
| T-B3-b | N1 | Dekryptér en blok under et andet, gyldigt `block_id` | `E_CONTEXT_INTEGRITY` |
| T-B3-c | N2 | Kopiér `blocks/aa/X` til `blocks/bb/Y` i hjemmet og referér Y fra et manifest | Læsning af Y fejler med `E_CONTEXT_INTEGRITY`; X kan stadig læses |

**Mutanter:** CTX-B3-1 AAD uden `context_id`; CTX-B3-2 AAD uden `block_id`; CTX-B3-3 tom AAD.

### H-1 Opret-hvis-fraværende (§6.1)

N2 kører mod tre slags hjem:

- **Overholdende servere:** mindst én S3-server og én WebDAV-server. Hvilke rigtige servere, der overholder kravet, er netop det T-H1-c afgør. Kandidater er Garage (europæisk), Ceph RGW og MinIO for S3, og Apache `mod_dav` og **Nextcloud** for WebDAV. Nextcloud er vigtig, fordi den åbne stak er førsteklasses (ADR-0006).
- **Fejlbehæftet testserver 1:** ignorerer `If-None-Match` og overskriver.
- **Fejlbehæftet testserver 2:** svarer `412`, men har alligevel overskrevet (lyver).

| Test | Niveau | Trin | Forventet |
|---|---|---|---|
| T-H1-a | N2 | Skriv blok X; skriv en anden gyldig chiffertekst under samme X | Andet kald får `412`; objektet er byte for byte uændret; EiraOS behandler det som "findes allerede", ikke som fejl |
| T-H1-b | N2 | 20 tråde uploader samtidig hver sin uafhængigt krypterede udgave af samme blok, 100 gentagelser | Præcis én skrivning lykkes pr. gentagelse; det lagrede objekt er vinderens bytes; alle 20 udgaver dekrypterer til samme klartekst |
| T-H1-c | N2 | Tilknyt hvert hjem. Prøven: skriv A til en prøvesti, skriv B med `If-None-Match: *`, læs | Overholdende: `412` og læsning giver A → hjemmet accepteres. Testserver 1 og 2 → afvises med `E_CONTEXT_HOME_UNSUPPORTED` |
| T-H1-d | N2 | Skriv manifest `<device_id>/<seq>`; skriv et andet manifest med samme sti | Andet kald afvises med `E_CONTEXT_INTEGRITY` og en audithændelse; det første manifest er uændret |
| T-H1-e | N2 | Gentag T-H1-a og T-H1-d over WebDAV | Samme resultat som over S3 |

**Mutanter:** CTX-H1-1 `If-None-Match` udelades ved upload; CTX-H1-2 `412` på et manifest behandles som succes; CTX-H1-3 tilknytningsprøven springes over; CTX-H1-4 prøven læser ikke objektet tilbage (fanger ikke testserver 2).

**Følge af T-H1-c:** Overholder Nextcloud ikke kravet, kan Nextcloud ikke være et kontekst-hjem i 1.0, før det er rettet. Det er et reelt projektvalg og skal afklares tidligt.

### M-1 Ukendte eller manipulerede manifester ignoreres og auditeres (§6.3, §8)

| Test | Niveau | Trin | Forventet |
|---|---|---|---|
| T-M1-a | N1 | Manifest signeret af en enhed, der ikke er på `keys/devices.signed` | Ignoreres; audithændelse; tilstanden er uændret |
| T-M1-b | N1 | Manifest, hvor én blok er fjernet fra `files`, men `merkle_root` er uændret | `E_CONTEXT_INTEGRITY`; ignoreres; audit |
| T-M1-c | N1 | Gyldigt manifest med én byte ændret i chifferteksten efter signering | Signaturfejl; ignoreres; audit |
| T-M1-d | N2 | Enhed D tilbagekaldes (§8); D skriver derefter et manifest | Ignoreres af alle øvrige enheder; audit |
| T-M1-e | N1 | Enhedslisten selv er signeret af en nøgle uden ret (ikke organisationen/ikke en af personens enheder) | Listen afvises; den forrige liste gælder fortsat |

**Mutanter:** CTX-M1-1 signaturtjek fjernes; CTX-M1-2 Merkle-tjek fjernes; CTX-M1-3 enhedslisten hentes, men bruges ikke; CTX-M1-4 audithændelsen udelades (testen kræver begge: ignoreret *og* auditeret).

### S-1 Samtidige ændringer giver konflikt, ikke overskrivning (§7)

| Test | Niveau | Trin | Forventet |
|---|---|---|---|
| T-S1-a | N1 | Enhed A og B ændrer samme sti offline, synkroniserer | Begge versioner findes; der er et konfliktobjekt i universet; ingen af dem er tabt |
| T-S1-b | N1 | A sletter en fil; B ændrer den uden at have set sletningen | B's version overlever (sletning vinder kun over versioner, den har set) |
| T-S1-c | N1 | A og B ændrer samme Automerge-dokument; flet i rækkefølgen A,B og B,A | Identisk resultat |
| T-S1-d | N2 | T-S1-a mod et rigtigt hjem med afbrudt net midt i upload | Højst ubrugte blokke efterlades; intet manifest peger på manglende blokke |

**Mutanter:** CTX-S1-1 "seneste vinder" efter `mtime`; CTX-S1-2 sletning ignorerer `parents`; CTX-S1-3 manifest skrives før blokkene.

### U-1 Linux-UID forlader aldrig enheden (§1)

| Test | Niveau | Trin | Forventet |
|---|---|---|---|
| T-U1-a | N1, statisk | JSON-skemaerne for kontekst-post, manifest, glimt, audit-eksport og rettighedssæt | Intet felt hedder `uid`, `gid` eller indeholder en UID-type |
| T-U1-b | N2/N3 | Kør et fuldt forløb (oprettelse, synkronisering, glimt, audit-eksport, Fleet-kald) med kontekst-UID'er fra et genkendeligt værdisæt (fx 87 654 og 87 655). Opsaml alle bytes, der forlader enheden, og alle *dekrypterede* manifester og poster | Ingen af UID'erne optræder som decimaltal, hex eller 32-bit big/little-endian |

**Mutanter:** CTX-U1-1 `uid` tilføjes i manifestet; CTX-U1-2 audit-eksporten bruger UID i stedet for `context_id`.

### I-1 Isolation mellem kontekster og over for skallen (§3.3)

**T-I1-0 fastlægger UID-intervallet** (§3.1 lægger det i testplanen). Forslag: **65 536–99 999**. Det ligger over systemd's dynamiske brugere (61 184–65 519) og `nobody` (65 534), under standardintervallet for subordinate UID'er (`SUB_UID_MIN` = 100 000) og langt under containerintervallet (fra 524 288). Det giver plads til 34 464 kontekster pr. enhed. T-I1-0 kører på N3 og bekræfter, at intervallet ikke overlapper `/etc/login.defs` (`UID_MIN`–`UID_MAX`, `SUB_UID_MIN`–`SUB_UID_MAX`), `/etc/subuid`, `/etc/subgid` eller de intervaller, `userdbctl` rapporterer på det installerede system.

Øvrige tests kører på N3 med to åbne kontekster, A og B, og skal-brugeren `eira-shell`. Hver test køres fra A mod B og fra `eira-shell` mod både A og B:

| Test | Forsøg | Forventet |
|---|---|---|
| T-I1-a | Læs en fil i B's monterede volumen | `EACCES` |
| T-I1-b | `kill -0` mod en af B's processer | `EPERM` |
| T-I1-c | `ptrace(PTRACE_ATTACH)` og læsning af `/proc/<pid>/mem` | `EPERM` |
| T-I1-d | Forbind til B's D-Bus-sessionsbus (`/run/user/<uid-B>/bus`) | Afvist |
| T-I1-e | Forbind til B's Wayland-socket og til compositorens hovedsocket | Afvist |
| T-I1-f | Læs udklipsholderen, mens B har kopieret en kendt tekst | Teksten kan ikke læses |
| T-I1-g | Læs B's låste LUKS-fil som root uden CMK | Kun chiffertekst |
| T-I1-h | Opret en Linux-bruger fra en kontekst-bruger eller fra `eira-shell` | Afvist; kun `eira-contextd` kan |
| T-I1-i | List `/proc`, kør `ps -e`, og læs `/proc/<pid>/cmdline` og `environ` for en af B's processer (pid kendt fra testen) | B's processer findes ikke i listen; direkte læsning giver `ENOENT` |
| T-I1-j | Tjek `/proc`-monteringen og gruppen `eira-procview` på det installerede system; start en session og brug systemets almindelige funktioner (log ind, lås skærm, polkit-godkendelse, netværk) | Monteret med `hidepid=invisible,gid=eira-procview`; gruppen har kun systemtjenester som medlemmer; `user@<uid>.service` har `ProtectProc=invisible`; intet fejler. Fejler noget, er det et fund, der afgør, hvilke tjenester der skal undtages |

**Mutanter:** CTX-I1-0 `/proc` uden `hidepid`; CTX-I1-5 `eira-shell` er medlem af `eira-procview`; CTX-I1-1 B's hjem monteres `0755`; CTX-I1-2 kontekst-brugere i samme gruppe; CTX-I1-3 compositorens hovedsocket `0666`; CTX-I1-4 fælles udklipsholder.

### O-1 Offline-perioden kan ikke forlænges ved at stille uret tilbage (§4.2)

Testes på N1 med et injiceret ur (samme mønster som `app/clock.py`) og verificeres på N3 med `timedatectl`.

| Test | Trin | Forventet |
|---|---|---|
| T-O1-a | Seneste signerede tid fra hjemmet = T. Lokalt ur sættes til T + `max_offline_days` + 1 | `E_CONTEXT_OFFLINE_EXPIRED` |
| T-O1-b | Derefter sættes uret tilbage til T + 1 | Stadig `E_CONTEXT_OFFLINE_EXPIRED` |
| T-O1-c | Som T-O1-b, men med genstart af enheden imellem | Stadig udløbet; den højeste kendte tid er forseglet og overlever genstart |
| T-O1-d | Uret sættes tilbage *før* perioden er udløbet, og tiden går så frem | Perioden udløber på samme tidspunkt, som hvis uret ikke var stillet tilbage |

**Mutanter:** CTX-O1-1 bruger det lokale ur direkte; CTX-O1-2 højeste kendte tid gemmes kun i hukommelsen.

### G-1 Glimt indeholder kun tilladte felter (§11)

| Test | Niveau | Trin | Forventet |
|---|---|---|---|
| T-G1-a | N1 | Aktivitetsglimt med et ekstra felt (`title`, `sender`, `preview` m.fl.) | Afvist |
| T-G1-b | N1 | Kalenderglimt fra en kontekst med `glimt_level` = `activity` | Afvist |
| T-G1-c | N1 | Kalenderglimt med `place`, der indeholder en e-mailadresse eller et telefonnummer | Afvist |
| T-G1-d | N3 | Lås kontekst A; tjek skallen | Ingen glimt fra A |

**Mutanter:** CTX-G1-1 validering med blokliste i stedet for tilladt-liste; CTX-G1-2 `glimt_level` tjekkes ikke.

### E-1 Escrow kræver fire øjne, audit og besked (§5.4)

| Test | Niveau | Trin | Forventet |
|---|---|---|---|
| T-E1-a | N1 | Én nøgleforvalter forsøger at bruge en escrow-nøgle | Afvist |
| T-E1-b | N1 | Samme nøgleforvalter godkender to gange | Afvist |
| T-E1-c | N1 | Medarbejderen selv er den ene godkender | Afvist |
| T-E1-d | N1 | En bruger med anden Fleet-adgang (support, enhedsadministration), men ikke rollen *nøgleforvalter* | Afvist |
| T-E1-e | N1 | Gyldig brug med to forskellige nøgleforvaltere | Lykkes; én audithændelse med begge godkendere, kontekst og begrundelse; besked til medarbejderen. Med registreret udsættelse: ingen besked før udløb, besked ved udløb, udsættelsen er selv auditeret |

**Mutanter:** CTX-E1-1 godkendere sammenlignes ikke; CTX-E1-2 rollen tjekkes som "har Fleet-adgang"; CTX-E1-3 udsættelse uden udløb.

### V-1 Værgestyret kontekst: tidsrum og DNS (§11a)

| Test | Niveau | Trin | Forventet |
|---|---|---|---|
| T-V1-a | N3 | Barnets kontekst er åben; uret passerer sengetid | `eira-contextd` låser konteksten; processerne stoppes |
| T-V1-b | N3 | Fra barnets kontekst-UID: DNS til `8.8.8.8:53` over UDP og TCP, DoT til `1.1.1.1:853`, DoQ på UDP 853, DoH til et kendt endpoint | Alle fejler; kun enhedens filtrerende resolver svarer |
| T-V1-c | N3 | Opslag af et domæne fra filterets testliste gennem resolveren | Spærret |
| T-V1-d | N3 | Ændr reglerne med en signatur fra en nøgle, der ikke er en værges | Afvist; de gamle regler gælder fortsat |

**Mutanter:** CTX-V1-1 nftables-reglen for port 853 fjernes; CTX-V1-2 reglerne gælder pr. program i stedet for pr. UID; CTX-V1-3 tidsrummet håndhæves kun i skallen.

### X-1 Exit-garantien (§6.5)

| Test | Niveau | Trin | Forventet |
|---|---|---|---|
| T-X1-a | N2 | Opbyg et kontekst-hjem med EiraOS (filer, konflikter, slettede filer, Automerge-dokumenter). Kør `eira-context-export` i en ren container uden EiraOS, kun med CMK | Filerne er byte for byte identiske med kilden; Automerge-dokumenterne eksporteres som JSON svarende til graphd's tilstand |
| T-X1-b | N2 | Samme med genoprettelsesnøglen i stedet for CMK (kun `personal`) | Samme resultat |

**Mutant:** CTX-X1-1 EiraOS skriver et felt, som kun EiraOS' egen kode forstår (testen fanger det, fordi eksporten afviger).

### R-1 Tilbagekaldelse (§5.5, §8)

| Test | Niveau | Trin | Forventet |
|---|---|---|---|
| T-R1-a | N2 | Enhed D tilbagekaldes; CMK roteres; enhed A skriver en ny fil. Forsøg at dekryptere de nye blokke og det nye manifest med D's gamle CMK | Fejler; `keys/devices/<D>` findes ikke længere |
| T-R1-b | N2/N3 | D kommer online og synkroniserer | D ser, at den ikke er på enhedslisten; konteksten går til tilstanden *fjernet* (§4) på D; `E_CONTEXT_DEVICE_REVOKED`; audithændelse |
| T-R1-c | N1 | D er offline under tilbagekaldelsen | D låser konteksten senest ved `max_offline_days` (samme ur som O-1) |
| T-R1-d | N2 | Organisationskontekst: rotationen | `keys/org` er pakket med den nye CMK; den gamle pakning er væk |

**Mutanter:** CTX-R1-1 rotationen springes over; CTX-R1-2 nye blokke krypteres med den gamle CMK; CTX-R1-3 `keys/devices/<D>` slettes ikke; CTX-R1-4 D ignorerer, at den mangler på listen.

### F-1 Glemsel (§4.3)

Kører på N3. Konteksten åbnes og får et kendt `display_name` og en markørtekst, der skrives i en fil, i en webapp (titel og URL) og i en notifikation. Konteksten låses, uret stilles frem forbi `forget_after_days`, og glemslen udløses.

| Test | Trin | Forventet |
|---|---|---|
| T-F1-a | Tjek TPM, `/var/lib/eira/contexts/`, `/etc/passwd`, `eira-contextd`s tabel og skallens cache | Ingen forsegling, ingen LUKS-fil, ingen bruger, ingen kobling, intet cache-indhold for konteksten |
| T-F1-b | Som root: søg efter markørteksten og `display_name` i hele filsystemet (uden `/proc` og `/sys`), i journalen og på den dekrypterede rodenhed (`/dev/mapper/…`) og swap, byte for byte | Ingen forekomster |
| T-F1-c | Åbn konteksten igen online | Den synkroniseres fra hjemmet som ved første login (§4.1); intet genbruges fra før glemslen |

**Mutanter:** CTX-F1-1 TPM-forseglingen fjernes ikke; CTX-F1-2 skallens cache med `display_name` ligger på disk; CTX-F1-3 `display_name` skrives i journalen; CTX-F1-4 webappens cache ligger uden for kontekstens volumen.

### A-1 Gendannelse giver aldrig autoritet (§5.2, §8)

Kører på N3 med emuleret TPM (`swtpm`). En installeret VM tilmeldes Fleet, får en organisationskontekst og en personlig kontekst, et rettighedssæt og en samtykkenøgle. Disken klones (`qemu-img convert`) og startes i en ny VM med en **ny** `swtpm`. For at teste lagene under diskkrypteringen får angriberen diskens gendannelsesnøgle, så rodfilsystemet kan åbnes.

| Test | Trin | Forventet |
|---|---|---|
| T-A1-a | Åbn hver kontekst på klonen | Forseglingen af CMK kan ikke låses op; konteksterne forbliver låste; LUKS-filerne kan kun læses som chiffertekst |
| T-A1-b | Synkronisér eller skriv et manifest fra klonen | Enhedens signeringsnøgle findes ikke på den nye TPM; intet manifest kan signeres; hjemmet modtager intet, der godtages (M-1) |
| T-A1-c | Forbind til Fleet (mTLS) og hent et nyt rettighedssæt; brug en samtykkenøgle fra en session, der var åben, da disken blev kopieret | mTLS-håndtrykket fejler, fordi nøgleblobben ikke kan bruges på den nye TPM; intet nyt sæt hentes. Ingen samtykkenøgle findes på disken, og sessionen er ugyldig efter genstart (EIRA-CONSENT-AGENT). Et allerede cachet sæt gælder som offline, til det udløber; testen bekræfter, at det udløber på det forventede tidspunkt og ikke kan fornyes |
| T-A1-d | Tilmeld den nye VM normalt (§4.1) og log ind | Data synkroniseres tilbage fra hjemmet; enheden får sin egen `device_id`, sin egen plads på enhedslisten og sine egne nøgler; intet fra klonens disk genbruges som autoritet |

| T-A1-e | Klonen udgiver sig for den oprindelige enhed over for Fleet og hjemmet i alle kombinationer nedenfor | Se matrixen |

**Identitetsmatrix for T-A1-e.** Klonen har den oprindelige disk, men en ny TPM. Den oprindelige enhed er enten stadig aktiv eller tilbagekaldt.

| `device_id` | Offentlig nøgle | Auth-token | Forventet |
|---|---|---|---|
| Gammel | Gammel | Gammelt | Afvist: klonen kan ikke bevise besiddelse af den private nøgle (mTLS-håndtrykket kræver en signatur med nøglen), som kun findes i den gamle TPM. **Lykkes i dag**, fordi nøglen og tokenet ligger i filer; lukkes af §5.0 |
| Gammel | Ny | Gammelt | Afvist: nøglen matcher ikke registret |
| Gammel | Ny | Intet | Afvist |
| Ny, selvvalgt | Ny | Intet | Afvist: `device_id` er ikke fingeraftrykket af nøglen |
| Fingeraftryk af ny nøgle | Ny | Intet, uden tilmeldingskode | Afvist |
| Fingeraftryk af ny nøgle | Ny | Normal tilmelding med kode fra en administrator | Accepteret som **ny** enhed uden noget fra den oprindelige (T-A1-d) |

Hver afvisning auditeres. Ingen kombination må give adgang til den oprindelige enheds rettighedssæt, kontekster eller tilmeldingsstatus.

| T-A1-f | Inspicér nøglerne på en installeret enhed med TPM | Signerings- og ECDH-nøglen har attributterne `fixedTPM` og `fixedParent`; `device.key` er en TSS2-nøgleblob og ikke en almindelig PEM-nøgle; `TPM2_Duplicate` afvises |
| T-A1-g | Installér på en VM uden TPM | Fleet-tilmelding afvises (`E_CONTEXT_POLICY`); en organisationskontekst kan ikke åbnes; en personlig kontekst kan oprettes, skallen viser advarslen, og enhedslisten har `key_protection: "file"`; en organisationskontekst afviser en enhed med `"file"` på listen |

**Mutanter:** CTX-A1-6 nøglen dannes i software og importeres til TPM'en (kan eksporteres); CTX-A1-7 en enhed uden TPM tilmeldes Fleet med filnøgle; CTX-A1-4 `device_id` tages fra forespørgslen; CTX-A1-5 gyldigt token accepteres uden bevis for den private nøgle; CTX-A1-1 CMK gemmes ved siden af forseglingen (fx som fallback i en fil); CTX-A1-2 enhedens signeringsnøgle ligger i en fil i stedet for i TPM'en; CTX-A1-3 `device_id` læses fra disken i stedet for at afledes af TPM-nøglen.

## 5. Fund under arbejdet med planen

1. **Manglende fejlkoder.** Kontrakten nævnte ikke, hvilken fejl en manifest-kollision, en AEAD-fejl på en blok og et hjem uden opret-hvis-fraværende giver. Rettet i kontrakten v0.3 (§12): `E_CONTEXT_INTEGRITY` dækker nu også blokke og manifest-kollision, og `E_CONTEXT_HOME_UNSUPPORTED` er ny.
2. **Den eksisterende `app/daemons/contextd.py` modsiger kontrakten.** Den har en fast liste af seks kontekster, én "aktiv" kontekst og en beløbsgrænse for automatisk godkendelse i wallet pr. kontekst. Den skal erstattes af `eira-contextd`, ikke udbygges. Beløbsgrænsen hører under gaten og rettighedssættet, ikke under kontekstlaget.
3. **`/proc` manglede i §3.3.** Som standard kan alle brugere læse alle processers kommandolinje. Tilføjet i kontrakten: `hidepid=invisible` for hele systemet med undtagelsesgruppen `eira-procview` (besluttet af ejer). Testes i T-I1-i og T-I1-j.
4. **Tilbagekaldelse og glemsel** manglede i §12a. Tilføjet som R-1 og F-1 (besluttet af ejer).
