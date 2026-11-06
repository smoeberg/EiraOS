# EiraOS – Phase 0: IPC & Event Bus Foundation

**Status:** Kontrakt + referenceimplementation. Kontrakten er frosset gennem testene i `crates/eira-core/src/ipc/`.
**Ejer:** Søren Møberg. Gennemgået i fire review-runder (se §10).
**Kode:** `crates/eira-core`, feature `ipc` (og `ipc-tokio` til Tokio-listeners). Kun Linux.

> **Regel:** En test i `eira-core::ipc` er den eksekverbare form af dette dokument. En ændring, der får en test til at fejle, er en kontraktændring og kræver en amendment her.

Phase 0 etablerer den fælles, sikre kommunikationskontrakt, som alle senere EiraOS-dæmoner og services bygger på. Målet er ikke hele event-systemet, men et stabilt fundament, der kan testes isoleret og bruges af Phase 1.

## 1. Formål og afgrænsning

Phase 0 leverer:

1. En fælles event-envelope og serialiseringskontrakt.
2. Sekvensstyring og eksplicit commit.
3. Sikker håndtering af filstier og IPC-ressourcer.
4. Systemd socket activation og FD ownership.
5. En kryptografisk signaturkontrakt.
6. Kø- og drop-semantik for subscribers.
7. Dokumenterede fejltilstande og testbare garantier.

Phase 0 omfatter ikke: persistent Event Store, replay og durable delivery, key management (TPM/YubiKey), brugeridentitet og login, Graph/Veritas/UI-integration og bootbar ISO.

## 2. Arkitektur

```text
EiraOS Services     eira-sessiond · eira-compositord · eira-keyd · øvrige dæmoner
IPC Contract        eira-core::ipc — envelope · CBOR · framing · sequence · signatures · path · activation · queues
Event Fabric (P1)   eira-eventd — routing · subscribers · backpressure
Event Store (P2)    durable · replay · checkpoints · audit
```

## 3. Kerneområder

### 3.1 Event Envelope — `envelope.rs`, `cbor.rs`

Envelopen sendes på wire som et kanonisk CBOR-map med tekstnøgler:

| Felt | CBOR-type | Regel |
|---|---|---|
| `envelope_version` | uint | Skal være `1`. Andre værdier afvises ved både afsendelse og modtagelse |
| `event_id` | bstr (16) | UUIDv7 eller tilfældig |
| `event_type` | tstr | `[a-z0-9_.]`, 1–128 tegn, ingen tomme segmenter |
| `schema_version` | uint (≥1, u16) | Versionen af payload-schemaet |
| `producer_id` | bstr (16) | Producentens instans |
| `sequence` | uint (≥1) | Pr. producent; der er ingen global rækkefølge |
| `timestamp_ns` | int (i64) | Nanosekunder siden Unix epoch. Aldrig en tekst eller dato-type |
| `correlation_id` | bstr (16) \| null | |
| `payload` | vilkårlig profil-værdi | |
| `signature` | map \| *fravær* | `{algorithm: "ed25519", key_id: bstr16, signature: bstr64}` |

Ukendte felter, manglende felter og forkerte typer afvises (fail closed).

**CBOR-profil** (RFC 8949 core deterministic, strammet op):
- Kun heltal, bstr, tstr, array, map, `true`, `false` og `null`.
- Korteste kodning af heads og kun definite length.
- Map-nøgler sorteres bytevis efter deres kodede form, og dubletter er forbudt.
- Ingen floats, tags eller andre simple values. Maksimal dybde 32.

**Dekoderen håndhæver profilen.** Gyldig CBOR, der ikke er kanonisk, afvises. Derfor er "decode og encode igen" identiteten. Golden vectors fra RFC 8949 appendiks A ligger i testene. Den signerede golden envelope er desuden verificeret med en uafhængig implementation (Python `cbor2`, `canonical=True`): byte-identisk.

### 3.1a Framing — `frame.rs`
`u32 big-endian længde || CBOR-besked`, med længde 1–16 MiB. Dekoderen er inkrementel og håndterer halve frames, flere frames i ét læs og én byte ad gangen. Længden 0 eller over grænsen *forgifter* streamen, og forbindelsen skal lukkes. Grænsen håndhæves ud fra headeren alene, før noget bufferes.

### 3.2–3.3 SequenceTracker og ConsumerProgress — `sequence.rs`

Et events livsforløb:

```text
receive → begin → complete → commit
            ↑         │
            └─ fail ──┘     (retry; checkpointet går aldrig tilbage)
```

- **Ingen implicit commit.** `commit(n)` committer præcis event *n*. Bufferede events bliver aldrig committet med.
- **Sekventiel commit.** *n* committer kun, når *n−1* er committet.
- **Flere events kan være in-flight samtidig.** Kun commits er ordnede.
- **`PredecessorPending` er ikke en behandlingsfejl.** Consumeren beholder sit resultat og prøver commit igen senere. Eventet må ikke køres igen.
- **Bounded buffer** (standard 1024 pr. producent). Er den fuld, giver det `BufferFull` (fail closed).
- **`fail` påvirker kun det fejlede event.** Eksempel: checkpoint 10, 11 committet, 12 fejler → checkpointet forbliver 11.
- **Kun committede positioner må persisteres** (`checkpoints()`). Efter et crash gen-leveres ucommittede events, og events til og med checkpointet er `Duplicate`.

**Amendment 1 — huller og dødvande.** Bus'en er at-most-once, så en forgænger kan forsvinde for altid. Streng sekventiel commit alene ville da blokere producenten permanent. Det er en fejl, review-runde 3 og 4 ikke opdagede. Løsningen:
- `gaps()` rapporterer manglende intervaller.
- `declare_lost(through)` lader consumeren *eksplicit* erklære dem tabt. Det flytter checkpointet, tæller `lost()` op og afviser at springe et event over, der faktisk er modtaget.
- Det sker aldrig automatisk.
- Et tabt event, der dukker op senere, er `Duplicate`.

### 3.4 PathScope og sikker filadgang — `path.rs`

1. **`RelPath`** validerer stien komponent for komponent. Absolutte stier, `.`, `..`, tomme komponenter og NUL afvises, og stien må højst være 4096 bytes.
2. **`PathScope::permits`** er et komponentbaseret policy-forhåndstjek. `Under("Documents")` matcher ikke `Documents-secret`. `Exact` matcher kun præcis stien.
3. **`SecureRoot::open_file` er sikkerhedsgrænsen.** Autorisation og opløsning sker i én kerne-operation, `openat2(2)`:
   - Først åbnes scope-mappen med `RESOLVE_BENEATH | RESOLVE_NO_MAGICLINKS | RESOLVE_NO_XDEV | RESOLVE_NO_SYMLINKS`. Den leksikale scope-check og kernens opfattelse stemmer derfor overens.
   - Derefter åbnes målet under scope-fd'en, med `RESOLVE_NO_SYMLINKS`, medmindre `SymlinkPolicy::WithinScope` er valgt.
   - Et symlink, der skiftes ind efter forhåndstjekket, afvises af kernen. Der er ingen tjek-så-åbn-race.
4. **Ingen fallback.** Mangler `openat2` (`ENOSYS`), giver det `Unsupported`. En opløsning, der fejler, giver afvisning og aldrig den uopløste sti.
5. **`CreateNew`** bruger `O_CREAT | O_EXCL`, tilstand 0600, og følger aldrig et symlink.

Tests dækker `..`, absolutte og relative symlink-escapes, magic links (`/proc/self/root`), et symlinket scope-dir, en plantet symlink ved oprettelse og en TOCTOU-test, hvor en angribertråd skifter mellem fil og symlink til hemmeligheden 5000 gange. Hemmeligheden læses aldrig.

### 3.5 Systemd FD ownership — `activation.rs`

- `LISTEN_PID` skal være lig vores PID. `LISTEN_FDS` må højst være 64. `LISTEN_FDNAMES`, hvis den er sat, skal navngive hver fd.
- **Én ejer.** Fra parsing ejes hver fd af præcis én `OwnedFd`, og der sættes `FD_CLOEXEC`.
- **`take_listener(name)` flytter fd'en ud** og validerer den: `S_IFSOCK`, `SO_DOMAIN = AF_UNIX`, `SO_TYPE = SOCK_STREAM` og `SO_ACCEPTCONN = 1`. Den returnerer en `std::os::unix::net::UnixListener`. Der findes ingen "rå fd", som to ejere deler.
- Et navn kan kun tages én gang (`AlreadyTaken`). En fd, der fejler valideringen, lukkes.
- `take_tokio_listener` (feature `ipc-tokio`) følger samme kontrakt: `set_nonblocking(true)` og derefter `from_std`.
- Fd'er, der ikke tages, lukkes, når `Activation` droppes.
- `from_process_env()` rydder `LISTEN_*` efter parsing og skal kaldes, før der startes tråde.

### 3.6 Kryptografisk signering — `signature.rs`

Det signerede input er entydigt, fordi alle felter har fast længde eller længdepræfiks:

```text
u8   15                      længden af domain separator
[u8] "EIRAOS-EVENT-V1"       15 bytes (ikke 16 — rettet fra review-runde 4)
u16  envelope_version (BE)   læst fra envelopen, aldrig hardcodet
u16  schema_version   (BE)   læst fra envelopen, aldrig hardcodet
u8   algoritme-id            1 = Ed25519
[16] key_id                  bindes ind i signaturen
[..] kanonisk CBOR af envelopen uden `signature`-feltet
```

Ed25519 bruger 32 bytes offentlig nøgle og 64 bytes signatur, og verifikationen er `verify_strict`. Følgende afvises: manglende signatur, hvor den er påkrævet, ukendt nøgle, ændret payload, schema eller sekvens, ombyttet `key_id` (også selvom samme nøgle findes under to id'er) og forkert domain separator. En signatur, der findes, verificeres altid, også når signering ikke er påkrævet. Der er en golden vector med fast nøgle.

## 4. Event Bus og subscriber-semantik — `queue.rs`

| Politik | Adfærd |
|---|---|
| `DropOldest` | Fjern ældste event ved fuld kø |
| `DropNewest` | Afvis nyeste event ved fuld kø |
| `DropByAge` | Fjern events ældre end `max_age_ns`, og afvis et nyt event, der allerede er for gammelt. Er køen stadig fuld, afvises det nye event |

Grundregler:
- **En publisher blokeres aldrig.** `Fanout::publish` bruger `try_lock` på hver kø. Er en subscribers kø optaget, eller er dens tråd crashet (forgiftet mutex), droppes eventet kun for den subscriber og tælles (`DroppedBusy`).
- Levering er at-most-once, og hvert drop tælles.
- **Huller i sekvensen er normale.** Et `GapDetected` betyder "der mangler måske et event", ikke "bussen er i stykker" (se 3.2–3.3, Amendment 1).
- Durable delivery og replay hører til Event Store (Phase 2).

## 5. Acceptance criteria

| Område | Krav | Status |
|---|---|---|
| Event envelope | Versioneret og valideret | ✅ `envelope::tests` |
| CBOR | Deterministisk og testet | ✅ RFC 8949-vektorer + afvisningstests + uafhængig cbor2-verifikation |
| SequenceTracker | Ingen implicit commit | ✅ |
| ConsumerProgress | Korrekt concurrent tracking | ✅ 4 tråde, 400 events, commit i orden præcis én gang |
| PathScope | Ingen traversal eller symlink-escape | ✅ |
| openat2 | Faktisk implementeret og testet | ✅ syscall, ingen pladsholder |
| systemd FD | Validering og ownership | ✅ |
| Ed25519 | Signering og verifikation med testvektorer | ✅ golden vector |
| Subscriber-køer | Alle tre drop-politikker testet | ✅ |
| Fejlhåndtering | Fail closed | ✅ |
| CI | Relevante tests grønne | `rust-ci`: clippy `-D warnings` + `cargo test -p eira-core --features ipc-tokio` |

## 6. Obligatoriske tests → testnavne

| Krav | Test |
|---|---|
| Out-of-order og eksplicit commit | `sequence::out_of_order_events_are_buffered_never_auto_committed` |
| Dobbelt og ugyldig commit | `sequence::double_and_invalid_commits_are_rejected` |
| Flere samtidige consumers | `sequence::concurrent_consumers_commit_every_event_exactly_once_in_order` |
| Sekvenshuller og genoptagelse | `sequence::a_lost_predecessor_does_not_deadlock_the_producer`, `resume_after_crash_redelivers_uncommitted_events`, `failure_rolls_back_only_the_failed_event` |
| Path traversal med `..` | `path::relative_paths_are_validated_per_component` |
| Symlink-escape og TOCTOU | `path::symlink_escape_is_blocked_by_the_kernel`, `toctou_swap_never_yields_the_secret` |
| Ugyldige systemd-fd'er | `activation::environment_is_validated`, `wrong_descriptor_types_are_rejected_and_closed` |
| Dobbelt fd-overdragelse | `activation::a_named_listener_is_handed_over_exactly_once_and_works` |
| Forkert domain separator | `signature::wrong_domain_separator_is_rejected` |
| Ændret payload efter signering | `signature::tampering_is_detected` |
| Drop-politikker ved overløb | `queue::drop_oldest`, `drop_newest`, `drop_by_age` |
| Langsom subscriber blokerer ikke | `queue::a_slow_subscriber_never_blocks_the_publisher` |

## 7. Implementeringsrækkefølge
Trin A–F er leveret i denne PR. Trin G (integration med `eira-eventd`) er Phase 1.

## 8. Definition of Done
Dokumenteret kontrakt ✅ · genanvendeligt Rust-bibliotek i `eira-core` ✅ · tests for alle sikkerhedsgarantier ✅ · ingen kendte usikre fallbacks ✅ · grøn CI (afventer kørsel på PR'en) · API-kontrakt for Phase 1: de offentlige typer i `eira_core::ipc`.

## 9. Åbne beslutninger før Phase 1 (ejer)

1. **Forhold til det eksisterende IPC.** Prototypens daemons taler i dag JSON-RPC med én besked pr. linje over `/run/eira/*.sock` (CP-IPC-001). Phase 0 er CBOR med længdefelt. Skal `eira-eventd` erstatte det via en migrationsplan, eller køre ved siden af?
2. **EDP og envelope.** Forslag: EDP-handlinger (`utterance`, `commitment_proposed` …) er payload i `EventEnvelope`, med `event_type` som `conversation.<action>`.
3. **Capabilities og Gate Kernel.** Forslag: capabilities (authd) dækker service-til-service-adgang. Gate Kernel dækker beskyttede handlinger på brugerens vegne. Der skal være én policy-motor, ikke to.
4. **Bus og durability.** Det første Explorer-flow ("samtale om en sag", ADR-0001) må ikke tabe en henvendelse. Det kræver Event Store, eller at den semantiske hændelse persisteres hos producenten, før den publiceres.
5. **ServiceRef og ServiceIdentity, samt user- og system-event fabric** (review-runde 1–2) er besluttet i retning, men ikke en del af denne kode. `producer_id` er wire-identiteten i Phase 0.

## 10. Review-fund lukket i koden

| Fund (runde) | Lukket af |
|---|---|
| Timestamp som `DateTime` (1) | `timestamp_ns: i64` som CBOR-heltal; testet bytevis |
| `starts_with`-path og `Object => true` (1–2) | Komponentbaseret scope + `openat2`; ingen object-wildcard |
| `canonicalize()`-fallback (2–4) | Bruges ikke; fejl giver afvisning |
| FD 3 hardcodet, Tokio-API (2) | `LISTEN_PID/FDS/FDNAMES`, navngivet `take_listener`, `from_std` |
| Auto-commit af bufferede events (3) | `commit(n)` committer kun *n* |
| In-flight-inkonsistens (3) | Eksplicitte stadier pr. sekvens; concurrent processing, sekventiel commit |
| openat2 som pladsholder (4) | Rigtig syscall med `RESOLVE_*`-flag |
| FD-ownership låser sig selv (4) | Ownership flyttes ved `take_listener`; ingen parallel "consumed"-liste |
| Domain separator på 15/16 bytes (4) | `&[u8]` med længdepræfiks; testet |
| Hardcodet version 1/1 (4) | Versioner læses fra envelopen; testet med `schema_version` 2 |
| `key_id` ikke signeret (4) | `key_id` og algoritme indgår i det signerede input |
| Commit-retry-semantik (4) | Dokumenteret og testet (`PredecessorPending`) |
| `DropByAge` ikke generisk (4) | `Timestamped`-trait |
| *Dødvande ved strict commit + at-most-once (ny)* | `gaps()` + eksplicit `declare_lost()` |
