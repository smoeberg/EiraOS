# EiraOS — udviklingsplan

**Status:** Forslag til ejerens accept, 12. november 2026
**Afløser:** rækkefølgen i [MASTER-PLAN-1.0](MASTER-PLAN-1.0.md) §4, §5 og §8 (principperne, statusordene og definition of done dér gælder fortsat)
**Bygger på:** [ADR-0001–0006](decisions/), kontrakterne i [`specs/`](../specs/README.md), koden på `main` efter #184 , [fundregistret fra de eksterne gennemgange](reviews/GENNEMGANG-2026-11-12.md) og [vurderingen af rådene om intuitivt design](reviews/RAAD-UX-2026-11-12.md)

> **AI'en foreslår. Gaten afgør. Systemet udfører.**

Planen siger, hvad der bygges, i hvilken rækkefølge, og hvad der skal være sandt, før et trin er færdigt. Den lover ingen datoer. Hvor planen og en kontrakt eller ADR er uenige, gælder kontrakten eller ADR'en, og planen rettes.

## 1. Hvor vi står

Sikkerhedskernen er bygget og afprøvet på den installerede pakke i en VM (`vm-install-acceptance`, 72 checks):

| Område | Status |
|---|---|
| Gate Kernel 1.1 | Otte lag, to handlingsfamilier (EDP og EiraSystemAPI), kalderidentitet fra `SO_PEERCRED`, audit med FSS-segl og Fleet-anker |
| Rettigheder fra Fleet | Signerede rettighedssæt, standardsæt i pakken, enroll og synkronisering over mTLS |
| Samtykke | Kun `eira-consent-agent` kan samtykke og bekræfte; nøglen ligger kun i RAM |
| Model | `eira-modeld` som egen bruger uden net; regelbaseret adapter, ingen sprogmodel |
| Identitet | Leverandørneutral OIDC; aldrig afprøvet mod en rigtig udbyder |
| Desktop | Explorer og Builder Mode, rigtig terminal, strøm via EiraSystemAPI; login gennem GDM |
| Pakning | `.deb`, `eira-labwc`, installer-ISO på Ubuntu 26.04, offline VM-test |

**Besluttet, men ikke bygget:** kontekster (ADR-0005, EIRA-CONTEXT og testplan accepteret), ID-hjemmet, Web App Manager (ADR-0004), livets indbakke (ADR-0006), universets model i graphd (ADR-0004 D4), adgangskoder og passkeys (ADR-0007, foreslået).

**Ikke besluttet:** økonomi. Det eneste af personens kerneområder uden en ADR (§3, spor P).

**Prototyper uden plads i målbilledet:** `walletd`, `presenced` og `contextd` i `app/daemons/`. De er ikke pakket (`packaging/daemon-policy.json`), men startes stadig af `runner.py` under udvikling. `contextd.py` modsiger EIRA-CONTEXT (testplan §5 pkt. 2).

## 2. Arbejdsform

- **Én agent ad gangen**, ét PR pr. trin. Ejeren merger; intet merges uden ejerens accept.
- **Kontrakt før kode.** En ny komponent får sin kontrakt i `specs/`, accepteret af ejeren, før den første kodelinje.
- **Færdig betyder afprøvet på den installerede pakke**, når trinnet rører rettigheder, AppArmor, systemd eller sessionen (som EIRA-CONSENT-AGENT §0.1 og EIRA-CONTEXT-testplanen N3).
- **Invarianter har mutanter.** En sikkerhedstest tæller først, når en realistisk fejl i koden får den til at fejle (EIRA-CONTEXT-testplan §2).
- **Den trygge handling skal være den letteste.** En funktion er først færdig, når en person, der ikke kender EiraOS, kan bruge den (spor U); teknisk korrekthed alene er ikke nok.
- **Hvert PR opdaterer** statustabellen i den berørte kontrakt, README's statustabel og CHANGELOG.

## 3. Rækkefølgen

```
F0b IPC-adgang ─────┐
F0 Luk bilag A ─────┤
F1 Teknisk gæld ────┼──► F1b Hele vejen ──► F2 Kontekster ──► F3 Identitet og rettigheder pr. kontekst
                    │                            │                         │
                    │                            └──► F4 ID-hjemmet        ▼
                    │                                                F5 Web App Manager ──► F6 Livets indbakke
                    │
                    └──► F7 EiraSystemAPI (mellem de store trin)    F8 Sprogmodel    F9 Release 1.0

U Brugerbevis løber ved siden af alle trin fra F1b
P Personens områder: beslutninger og kontrakter skrives parallelt med F2; bygges i takt med F2–F6
```

Kontekster kommer før Web App Manager og indbakken, fordi begge bygger på konteksten: en webprofil *er* en kontekst (ADR-0005), og der er én indbakke pr. kontekst (ADR-0006).

### F0 — Luk bilag A

Det, der står tilbage af GATE-KERNEL bilag A og EIRA-CONSENT-AGENT.

| # | Leverance | Færdig når | Afhænger af |
|---|---|---|---|
| F0.1 | **R-6.2-patch i `eira-labwc`** (leveret): `<trustedGroup>` i labwc; samtykkeagentens vindue ligger over alle andre (også fuldskærm), har fokus, og ingen anden klient kan tage fokus, starte træk-og-slip, holde input-grabs eller sætte et markørbillede, mens det vises. Sessionen starter ikke uden patchen. **Tilbage:** forslaget upstream til labwc | Patchen ligger i `packaging/eira-labwc/patches/`; `verify-trusted.sh` viser headless i CI, at et fuldskærmsvindue ikke kan dække agenten eller tage fokus, med kontrolkørsler. *Ændret fra planen:* en VM-test i en grafisk session hører til F0.2; VM'en tjekker pakke og konfiguration (`labwc-trusts-consent-group`) | — |
| F0.2 | **Verifikation i en grafisk VM-session** (EIRA-CONSENT-AGENT V-1; O-6: procestræet under GDM) | `vm-install-acceptance` kører en rigtig labwc-session og afprøver agentens vindue, fokus og registrering | F0.1 |
| F0.3 | **Login mod en rigtig OIDC-udbyder** (udgivelsesbetingelse) | Login i den installerede VM mod ejerens udbyder; identiteten bliver `did:eira:<provider-id>.<subjekt>` | Ejeren: app-registrering |

### F0b — Adgangskontrol pr. IPC-metode

Fra gennemgangene 12. november (S-1, S-2, S-3, S-11). Kommer før alt andet, fordi S-1 er et integritetshul på den installerede pakke: desktop-brugeren kan skrive i `stated`.

| # | Leverance | Færdig når |
|---|---|---|
| F0b.1 | `stated`: `state.append`, `state.sync_push` og `audit.append` kræver en daemon som kalder (UID `eira`), aldrig `eira-clients`. `state.sync_push` afviser hele batchen, hvis én blok er ugyldig, som `fleetd` gør | En test kalder metoderne som en almindelig bruger og får afslag; en VM-check (`user-cannot-write-stated`) gør det samme på den installerede pakke; en blandet batch giver nul skrivninger |
| F0b.2 | **Adgangsklasse pr. metode** ved registreringen ([`app/ipc/access.py`](../app/ipc/access.py)): `read`, `daemon_write` (serveren tjekker selv kalderens UID), `caller` (handleren afgør ud fra `SO_PEERCRED` og skal derfor få kalderen), `signed` (kryptografisk bevis i forespørgslen), `refused` og `open_write` (kendt hul med plan-id). En metode uden klasse kan ikke registreres. **JSON-RPC-kataloget** ([`docs/reference/ipc-katalog.md`](reference/ipc-katalog.md)) genereres fra registreringerne; senere også TypeScript- og Rust-typer fra samme kilde | `tests/test_ipc_access.py` gennemløber alle produktionsdaemons; de kendte `open_write`-huller står på en liste, der kun må blive kortere; CI fejler, hvis kataloget afviger fra koden |
| F0b.3 | **Leveret:** [`docs/security/SIKKERHEDSMODEL.md`](security/SIKKERHEDSMODEL.md): trusselsmodel (root og fysisk adgang udenfor), brugere og grupper, socket-rettigheder plus kernens kalder, at IPC-tokenet ikke beskytter mod desktop-brugeren, adgangsklasserne med antal, gaten, samtykkeagenten, indeslutning og kendte begrænsninger. `socket-permissions.md` er foldet ind og fjernet | Hver påstand peger på koden og på testen eller VM-checket, der beviser den |
| F0b.4 | **Leveret:** `identity.verify_production_certificate` er `daemon_write`; desktop-brugeren afvises, før der skrives audit. Listen over kendte huller er tom. VM-check `user-cannot-make-identityd-audit` | Fjernet fra listen over kendte huller i `tests/test_ipc_access.py` |

### F1 — Teknisk gæld, der skal væk før de store trin

Små PR'er, der kan tages i vilkårlig rækkefølge.

| # | Leverance | Hvorfor |
|---|---|---|
| F1.1 | **Clippy og `cargo fmt` på alle Rust-crates i CI**, også `ui/src-tauri` og `eira-consent-agent` (leveret: `rust-ci` kører clippy på hele workspacet med alle features, `rust-tauri-ci` fmt og clippy på `ui/src-tauri`; testenes bevidste låse er markeret med `#[allow(clippy::await_holding_lock)]` og en begrundelse) | CI kører clippy kun på `eira-core`, og fmt-tjekket dækker ikke `ui/src-tauri`. Clippy finder i dag tre ting i `ui/src-tauri/src/ipc.rs` (én løkke-indeksering i produktionskoden og to bevidste låse i testene, der skal markeres eksplicit), og `system_api/mod.rs` er ikke formateret |
| F1.2 | **Fjern `walletd`, `presenced` og `contextd`** fra `runner.py`, `app/daemons/` og deres tests. **Gate-processen indeholder kun gaten:** `app/mistral.py`, den gamle `intent.parse`/`intent.plan` med `build_agency` og den døde `IntentDaemonService` ud af `intentd` (S-7, S-8, S-9) (leveret sammen med F1.6: også `app/intent_parser.py` og `app/pending_intents.py`; `prototype_daemons` i `packaging/daemon-policy.json` er tom; `tests/test_gate_ipc.py` afviser, at gate-processen indlæser `httpx`, parseren eller CEL-executoren) | De er ikke i målbilledet; `contextd` modsiger EIRA-CONTEXT. Beløbsgrænsen i `contextd` hører under gaten og rettighedssættet. AI-INTERFACE §3 og §6 henter samtalekonteksten fra `contextd` og skal rettes til samtalelaget (EIRA-CONVERSATION) i samme PR |
| F1.3 | **Versioner og pakke-changelog:** `packaging/debian/changelog` siger `noble` og "Ubuntu 24.04"; Tauri-appen er 0.7.0, `ui/package.json` og `Cargo.toml` 0.3.0, pakken 1.0~rc1 (leveret som forslag: `VERSION` er den ene kilde, sat til `1.0.0-rc2`; pakken `1.0.0~rc2-1 resolute`; `tests/test_version.py`. *Ejerbeslutning 13.11.2026:* `1.0.0-rc2` frem for 0.8.0, fordi apt ser 0.8.0 som ældre end 1.0~rc1) | Én version for hele EiraOS, og pakken skal sige 26.04 (`resolute`) |
| F1.4 | **CI-robusthed:** upload af artefakter prøves igen ved fejl i GitHubs artefakttjeneste (leveret: lokale composite-actions for upload og download med tre forsøg, brugt i `packaging-acceptance` og `winapp-release`) | Den fejlede 11. november, efter at bygget var grønt |
| F1.5 | **Sessioner uden påstået identitet** (leveret): præsentationstilstanden hører til OS-brugeren på socketen (`SO_PEERCRED`), ikke til en session, så Tauri-backendens eget tjek ser samme tilstand som UI'et uden login. `presentation.mode_get`/`mode_set`, `dashboard.get` og `identity.session` er `caller`-metoder og opretter aldrig en session; `dashboard.get` og `identity.session` viser kun kalderens egen autentificerede session. `intent.parse`/`intent.plan` gemmer ikke længere en påstået aktør; at de får kalderens session, sker i F1.2. VM-check `user-mode-without-session`. *Ændret fra planen:* planen ville lade Tauri huske sessionen efter login, men så virkede terminalen kun efter OIDC-login, og en klient kunne stadig navngive en session | Ekstern audit 12. november (P1 og P2): `presentation.mode_get` kaldes uden `session_id`, så hvert kald opretter en ny anonym session i tilstanden `normal`, og terminalen afvises derfor altid, også når Builder er tilladt. Samme mekanisme lader `dashboard.get` hilse med et påstået navn (udviklingsbroen sender `mette@kommune.dk`). Gaten er upåvirket, fordi den kun godtager autentificerede sessioner bundet til UID'en |
| F1.6 | **Udviklingsbroen uden skriveruter:** `app/routers/wallet.py`, `presence.py` og `context.py` fjernes sammen med prototyperne i F1.2; `req.dict()` erstattes (S-22); den ubrugte `ui/veritas-hud/index.html` fjernes (D-10) (leveret i samme PR som F1.2; også `/v1/intent/parse` og `/plan`) | Ekstern audit (P2): ruterne skriver uden session eller gate, og `presence` godtager en klientleveret forfatter. Broen er ikke i pakken (`scripts/app_modules.py`, `tests/test_no_http_bridge_prod.py`), så det gælder kun udviklingsmiljøet |
| F1.7 | **Små rettelser fra gennemgangene:** gatens audit-lyttere logger, når Fleet-ankeret fejler, i stedet for at sluge fejlen (S-13); docstringen i `app/gate/consent_proof.py` beskriver agent-modellen (D-8); test af samtidig aktivering af politik (S-23) (leveret. *Fund:* testen afslørede et reelt kapløb: tjek og installation af et rettighedssæt var adskilte skridt, så to samtidige aktiveringer kunne rulle versionen tilbage eller begge godtage samme version med forskelligt indhold. Rettet med compare-and-swap i `RightsCache.install`; `tests/test_rights_concurrent_activation.py` med mutant) | Fundregistret |
| F1.8 | **Android:** ejeren afgør, om `android/` er med i 1.0. Hvis ja: et CI-job, der bygger den og tester hash-paritet Kotlin↔Rust med de samme vektorer som Python (S-16), og en README (D-9). Hvis nej: arkivér (leveret: *nej*, besluttet af ejeren 13. november 2026; arkiveret i `docs/archive/android/`) | Telefonen er uden for EIRA-CONTEXT 1.0 (§13) |
| F1.9 | **Fleet-interoperabilitet:** rettighedssættets testvektorer køres også i `eira-fleet-control`, og et fælles vektorsæt versioneres (S-20) (delvist leveret: vektorsættet er versioneret, og signer-vektorer og `scripts/rights_vectors_conformance.py` er klar til Fleets CI. *Tilbage:* Fleet-repoet (`smoeberg/Eirafleet`) indeholder i dag kun dokumentation og ingen signer, så der er intet at køre vektorerne mod endnu) | Endpointets kode alene beviser ikke, at Fleet signerer det samme |
| F1.10 | **Én vej til databaseskemaet:** Alembic eller `init_db()`, ikke begge; skrevet ned (S-21, D-12) (leveret: `init_db()`; Alembic fjernet fra repo, CI og `debian/rules`; [databaseskema.md](reference/databaseskema.md)) | Skema-drift |

### F1b — Første hele vej: fra intention til udført handling

IntentBar kalder i dag kun `intent.execute`, som svarer `E_GATE_REQUIRED` (ekstern audit, P1). Brugeren kan derfor ikke få udført noget fra den centrale indtastning. Alle dele findes, men er ikke koblet sammen: modelprocessen, `gate.propose`, samtykkeagenten og executorerne.

| # | Leverance | Færdig når |
|---|---|---|
| F1b.1 | **Leveret:** IntentBar sender teksten (uden samtale) og brugerens session til `eira-modeld`, som forstår strøm (“sluk computeren”, “genstart”, “sæt computeren i dvale”) og foreslår en EiraSystemAPI-handling til gaten som sig selv. Mangler en delegation, siger modellen præcis hvilken, og UI'et beder om den gennem samtykkeagenten. Afstår modellen, siger UI'et det og nævner, hvad den forstår. Manuel vej: Strøm-menuen, men kun i Builder Mode (ADR-0001 holder Explorer fri for systemknapper) | En kendt kommando giver et forslag; en ukendt giver et ærligt "forstod ikke" (`tests/test_intent_to_gate.py`, `ui/tests/intent_bar.test.ts`) |
| F1b.2 | **Leveret undtagen VM-delen:** samtykke og bekræftelse går gennem samtykkeagenten (appen sender kun `action_id`); UI'et viser gatens egen status bagefter (`gate.status`) og aldrig gengivelsen. Hele kæden tekst → model → gate → delegation → samtykke → logind er afprøvet i processen. **Tilbage:** VM-testen af hele vejen kræver installeret login (F0.3) og en grafisk session (F0.2); VM'en tjekker indtil da, at brugerens forespørgsel når gaten og afvises uden session (`intent-power-reaches-gate-and-is-refused`). `utterance` fra IntentBar kræver en samtale og kommer med samtalelaget | En VM-test kører hele vejen for strøm og for en `utterance`, og UI'et viser den reelle tilstand (`requested`, `pending`, afvist) |

Trinnet forudsætter F1.5 (sessionen) og bør komme før F2, fordi det er første gang, hele kæden afprøves sammen (MASTER-PLAN WS-7).

### F2 — Kontekster (EIRA-CONTEXT 1.0)

Det største trin. Kontrakten og testplanen er accepteret, så der skal ikke skrives ny kontrakt. Rækkefølgen følger testplanens niveauer: først rene funktioner (N1), så lagerservere (N2), så den installerede pakke (N3).

| # | Leverance | Invarianter (testplan) | Niveau |
|---|---|---|---|
| F2.1 | **Lagerformatet** (§6): blokke med AEAD, manifester, Merkle-træ, og referenceværktøjet `eira-context-export`, der læser et hjem uden EiraOS. Scriptet `scripts/check-mutants.sh`. Senere en knap i skallen, "Tag dine data med", der bruger værktøjet (exit-garantien som synlig funktion) | B-1, B-2, B-3, M-1, U-1, X-1 | N1 |
| F2.2 | **Kontekst-hjem over S3 og WebDAV** med opret-hvis-fraværende; nyt CI-job `context-home` | H-1 | N2 |
| F2.3 | **Enhedens nøgler i TPM** (§5.0): signerings- og ECDH-nøgle dannes i TPM'en og kan ikke eksporteres; Fleet-tilmelding bruger dem (FLEET-RIGHTS-API 1.3) | A-1 | N1, N3 |
| F2.4 | **`eira-contextd`:** opretter, låser op, låser og glemmer kontekst-brugere; LUKS2 pr. kontekst; `systemd --user` pr. kontekst; `/proc` med `hidepid=invisible` | I-1, O-1, F-1 | N3 |
| F2.5 | **Neutral skal-bruger og greetd** (ADR-0005 K7, K9) i stedet for GDM med en fast bruger; én Wayland-socket pr. kontekst (`wp_security_context_v1`) i `eira-labwc` | I-1 (Wayland-delen) | N3 |
| F2.6 | **Synkronisering:** filer med konfliktobjekter, strukturerede data med et åbent CRDT (fx Automerge); tilbagekaldelse og rotation | S-1, R-1 | N1, N2 |
| F2.7 | **Organisation og familie:** escrow med fire øjne, værgestyret kontekst, glimt og "overfør glimt" | E-1, V-1, G-1 | N1, N3 |

Et delpunkt er færdigt, når invarianternes tests og mutanter består på det angivne niveau (testplan §0).

### F3 — Identitet og rettigheder pr. kontekst

Kontraktrevisioner, som EIRA-CONTEXT og ADR-0005 kræver. De skrives, mens F2 bygges, og implementeres, når F2.4 findes.

| # | Leverance |
|---|---|
| F3.1 | **EIRA-IDENTITY 1.1:** udbyder pr. kontekst og flere samtidige identiteter; tenant-migrering som nyt provider-id |
| F3.2 | **RIGHTS-SET-revision:** et rettighedssæt bindes til (`tenant_id`, `context_id`) og ikke kun til en enhed; værgesignerede regler (`governance.source = guardian`); private kontekster på en åben organisations-enhed får standardsættet uden `system:`-handlinger (ADR-0005 O-9) |
| F3.3 | **Sessioner pr. kontekst** i `identityd` og gaten; samtykkeagenten viser altid, i hvilken kontekst et samtykke gives |
| F3.4 | **Enroll ved installation:** installeren spørger "Tilknyt en organisation" eller "Opret eller brug et Eira ID" (ADR-0005 K6); organisationsvejen enroller med en kort kode (ADR-0005 O-8). `device_mode` (lukket/åben, ét flueben i Fleet) føjes til desired state i FLEET-RIGHTS-API og OpenAPI-filen; skallen viser "Log ind i en anden kontekst" kun på en åben enhed. Enroll registrerer `owner` (`organisation`/`employee`); kommandoen *frigiv enhed* for medarbejder-ejede maskiner (ADR-0005 K6) |
| F3.5 | **Push fra Fleet:** udgående MQTT over mTLS fra agenten til EMQX; samme kanal bærer EiraOS-opdateringer (apt); Fleet sender "hent nu", agenten henter og verificerer som ved polling; polling er fallback (FLEET-RIGHTS-API §6 pkt. 5) |
| F3.6 | **Husstands-Fleet og opdatering uden Fleet:** tenant-type `household` i Fleet (kun fysiske maskiner; børns maskiner uden sudo); maskiner uden Fleet henter en signeret opdateringsfil hver time uden enheds-ID (ADR-0005 K6) |

### F4 — ID-hjemmet

| # | Leverance |
|---|---|
| F4.1 | Kontrakt **EIRA-ID-HOME**: indhold, kryptering, pseudonym afledt af eID, minimal logning, exit (ADR-0005 K11) |
| F4.2 | Klienten i EiraOS: kontekstlisten hentes ved login; lukkede enheder kører uden ID-hjem |
| F4.3 | Genoprettelse forankret i eID på niveau høj (ADR-0005 K5); første adapter MitID, mål EU Digital Identity Wallet |

Selve tjenesten drives af Eira og hører formentlig hjemme i et andet repo; det afgør ejeren.

### F5 — Web App Manager (ADR-0004)

| # | Leverance | Afhænger af |
|---|---|---|
| F5.1 | Kontrakt: app-manifest, motor-grænsesnit, profil = kontekst, links mellem apps (O-5), filer fra webapps ind i objektmodellen (O-6). **Tilladelse ved handlingen:** når personen vælger eller trækker en fil ind, får appen netop den fil og intet andet (powerbox-mønstret, som xdg-desktop-portal bruger) | ADR-0004 accepteret |
| F5.2 | Valg af Chromium-distribution (O-1) ud fra kontraktens sikkerhedskrav | F5.1 |
| F5.3 | Compositorens snævre vinduesgrænseflade efter GID (D6) | F0.1 |
| F5.4 | Første motor (Chromium) og de første webapps | F2.4, F5.2, F5.3 |

### F6 — Livets indbakke (ADR-0006)

| # | Leverance |
|---|---|
| F6.1 | Ejerens beslutning om ADR-0006 O-1–O-3 |
| F6.2 | Kontrakt for adapterlaget og indbakken pr. kontekst |
| F6.3 | Første adaptere på åbne standarder (IMAP/SMTP, CalDAV), gennem gaten |

### F7 — EiraSystemAPI ud over strøm

Kan tages mellem de store trin. Hver operation får et skema, en policy-post i gatens registry, en executor bag gaten og en række i [dækningsmatricen](architecture/ubuntu-pc-api-coverage-matrix.md).

Rækkefølge: netværksstatus (læs, NetworkManager), skift netværk, lyd, skærm, opdateringer. Indstillinger i UI'et bygges på operationerne, aldrig på shell-kommandoer.

### F8 — Sprogmodel bag AI-INTERFACE

| # | Leverance |
|---|---|
| F8.1 | Gentagelig flersproget evaluering (se [soofi-s-model-evaluation](architecture/soofi-s-model-evaluation.md)) |
| F8.2 | En lokal sprogmodel som adapter i `eira-modeld`, bag den samme kontrakt og de samme grænser (egen bruger, intet net, ingen samtykke) |

### F9 — Release 1.0

Opgradering og rollback, backup og genopretning, licenser, tilgængelighed og lokalisering, supportmatrix og en ærlig liste over kendte begrænsninger (MASTER-PLAN §6 og WS-11). Forudsætter F0, F2 og F3.

### U — Brugerbevis

Fra rådene om intuitivt design (se [vurderingen](reviews/RAAD-UX-2026-11-12.md)). GUI-planen §5.1 siger allerede, *hvad* der er intuitivt; dette spor sørger for, at det bliver *bevist*. Det begynder med F1b, fordi der først da findes en hel vej at teste.

| # | Leverance | Færdig når |
|---|---|---|
| U.1 | **10–15 hverdagsrejser** skrevet som opgaver, ikke som funktioner (fx "find det, jeg arbejdede på i går", "sluk computeren", "hvorfor kan jeg ikke det her?"), med GUI-planens §5.1 H som de første | Ejeren har accepteret listen; hver rejse har et mål for tid og antal skridt |
| U.2 | **Rejserne som automatiske tests i VM'en**, målt i tid og antal skridt ved hver PR, sammen med ventetiden pr. trin (GUI-plan §5.1 E) | En rejse, der bliver langsommere eller længere end sit mål, fejler CI |
| U.3 | **Samtykke-træthed måles:** hvor mange samtykker og afvisninger en dag giver. For mange løses med politik (handlinger, der kan fortrydes og bliver i konteksten, kræver kun bekræftelse), ikke ved at samle flere samtykker til ét | Tallet står i audit-oversigten og i rejsernes rapport |
| U.4 | **Tilgængelighed automatisk fra nu:** tastaturbetjening, tilgængelige navne, kontrast og reduceret bevægelse tjekkes i UI-testene (WCAG AA som mål), i stedet for til sidst (GUI-8) | `ui-ci` fejler ved brud |
| U.5 | **Gatens gengivelser læses af rigtige mennesker:** hver handlingstype har en sætning, en ikke-teknisk person forstår, inklusive om den kan fortrydes | Gengivelserne i `app/gate/render.py` og `app/gate/system.py` er gennemgået i en brugertest |
| U.6 | **Brugertest med mennesker, der ikke kender systemet**, ved hvert større trin (F1b, F2, F5): rigtige opgaver uden instruktion; tøven, fejl og spørgsmål noteres | Fund bliver issues og rettes, før næste trin får nye funktioner |

### P — Personens områder: id, økonomi, relationer, pligter, adgange, kommunikation

Ejeren (12. november 2026): det, der er vigtigt for en person, er id, økonomi, relationer, pligter, adgange (også adgangskoder) og kommunikation. Status pr. område:

| Område | Besluttet | Bygget | Trin |
|---|---|---|---|
| Id | ADR-0004/0005, EIRA-IDENTITY, EIRA-CONTEXT | Login uden fast udbyder, sessioner | F0.3, F3, F4 |
| Økonomi | Kun EDP's `value_transfer_requested` (eID høj, maks. 10.000 DKK/EUR) og værgers godkendelse af køb | Intet | **P.3** |
| Relationer | ADR-0006 (kontakter via CardDAV), ADR-0005 K12 (familie), delegation | Medlemskab i samtaler, delegation | **P.2**, F6 |
| Pligter | EDP (aftaler), ADR-0006 (kalender, opgaver) | Gaten tager imod aftaler; intet leveres | **P.2**, F6 |
| Adgange | ADR-0003, samtykkeagenten, ADR-0007 (koder) | Rettighedssæt, samtykke, delegation | F0b, **P.1**, **P.4** |
| Kommunikation | ADR-0006 | Læsbar hændelsesstrøm, ingen kanal | **P.2**, F6 |

| # | Leverance | Hvornår | Færdig når |
|---|---|---|---|
| P.1 | **"Mine adgange":** én oversigt pr. kontekst over hvad personen må (rettighedssættet), hvem der må handle på hendes vegne (delegationer), hvad hun har givet samtykke til, og senere hvilke apps der har kamera, filer osv. og hvilke koder der er svage (ADR-0007 A8). Kun læsning; at ændre noget går gennem gaten | Efter F1b | En ikke-teknisk person kan svare på "hvem må gøre hvad på mine vegne?" i en brugertest (U.6) |
| P.2 | **Kontrakter for personer og kontakter, pligter (aftaler, opgaver, kalender, deadlines) og indbakken** (F6.2), så den første mail- og kalenderadapter er klar, når konteksterne er | Parallelt med F2 | Ejeren har accepteret kontrakterne |
| P.3 | **ADR-0008 Økonomi.** Spørgsmålene, der skal besluttes: Rører EiraOS penge, eller samler det kun overblik (konti, regninger, abonnementer) og sender betalingen videre til bankens egen godkendelse? Hvilke bankforbindelser (open banking, PSD2/PSD3) og i hvilke kontekster? Hvordan med familie og værger (ADR-0005 K12)? Hvad med e-faktura og bogføring for selvstændige? `walletd`-prototypen fjernes i F1.2 uanset hvad; den bygger på en anden model | Nu; før kode | ADR'en er accepteret |
| P.4 | **Adgangskoder og passkeys efter ADR-0007:** kontrakt `EIRA-CREDENTIALS`; nøglebundt i kontekstens lager; passkeys og udfyldning i Web App Manager; import ved første opstart; fornyelse ved læk; eksport i CXF | Kontrakten efter F2.4 og F5.1; bygges med F5 | Ingen kode skal opfindes af personen i en brugertest; AI'en og Eira UI kan bevisligt ikke læse en kode (test) |

## 4. Dokumentation, der mangler

Fra gennemgangene (D-3 til D-11). Det, der kan genereres fra koden, skal genereres, så det ikke forældes.

| # | Dokument | Hvordan |
|---|---|---|
| 1 | `docs/security/` som samlet sikkerhedsmodel | F0b.3 |
| 2 | `SECURITY.md`: hvordan en sårbarhed rapporteres, og hvad der svares | Ejeren afgør kontakt og svartid |
| 3 | `docs/reference/implementeringsmatrix.md`: krav → kode → test → VM-check → status | Genereres af kontrakternes statustabeller og VM-checkenes navne; README's statustabel peger herhen |
| 4 | `docs/reference/miljoevariabler.md` | Genereres ved at søge efter `os.environ`/`getenv` i den pakkede kode |
| 5 | ~~`CONTRIBUTING.md`~~ **Leveret** med "ny beskyttet handling fra ende til anden" (strøm som eksempel), PR-skabelon og en rettet `.cursor`-regel. Issue-skabeloner mangler | Skrevet efter F1b, så den beskriver en vej, der virker |

## 5. De næste tre PR'er

1. ~~**F0b.1 og F0b.2** adgangskontrol pr. IPC-metode~~ (leveret i #186).
2. ~~**F1.5** sessioner uden påstået identitet~~ (leveret).
3. ~~**F0.1** R-6.2-patch i `eira-labwc`~~ (leveret; forslag upstream udestår).

Derefter F1b (hele vejen fra IntentBar). F1.1–F1.4 og F1.6–F1.10 kan lægges ind mellem de store trin.

## 6. Ejerens beslutninger

| Beslutning | Blokerer |
|---|---|
| Accept af ADR-0004, ADR-0005 og ADR-0006 (står som "Foreslået", selvom EIRA-CONTEXT bygger på ADR-0005 og er accepteret) | F5, F6; formelt også F2 |
| Accept af EIRA-IDENTITY 1.0 (står som "Udkast", men er implementeret) | F3.1 |
| App-registrering hos en rigtig OIDC-udbyder | F0.3 og udgivelse |
| ADR-0006 O-1–O-3 | F6 |
| Forslaget om et menneske- og fællesskabscentreret fundament (#165) | Formuleringer i F4–F6 |
| Hvor ID-hjemmets tjeneste og genoprettelsen bor (repo og drift) | F4 |
| ADR-0005 O-8 (tillidsanker for enroll ved installation) | F3.4 |
| Én versionsplan for EiraOS (F1.3) | F9 |
| Pilot (Arbejde eller Møde) | Prioritering af F6 og F7 |
| ~~Er `android/` med i 1.0?~~ Nej (13. november 2026) | F1.8 |
| Kontakt og svartid for sårbarhedsrapporter | `SECURITY.md` (§4) |
| Listen over hverdagsrejser og deres mål | U.1–U.2 |
| Accept af ADR-0007 (adgangskoder) og dens åbne spørgsmål O-1–O-5 (EU-wallet som passkey-udbyder, læk-tjek, digital arv, familiens koder, koder uden for webapps) | P.4 |
| Grundspørgsmålene til ADR-0008 (økonomi) | P.3 |
| Hvem der deltager i brugertests | U.5–U.6 |
