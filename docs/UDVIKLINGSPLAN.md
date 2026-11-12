# EiraOS — udviklingsplan

**Status:** Forslag til ejerens accept, 12. november 2026
**Afløser:** rækkefølgen i [MASTER-PLAN-1.0](MASTER-PLAN-1.0.md) §4, §5 og §8 (principperne, statusordene og definition of done dér gælder fortsat)
**Bygger på:** [ADR-0001–0006](decisions/), kontrakterne i [`specs/`](../specs/README.md) og koden på `main` efter #184

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

**Besluttet, men ikke bygget:** kontekster (ADR-0005, EIRA-CONTEXT og testplan accepteret), ID-hjemmet, Web App Manager (ADR-0004), livets indbakke (ADR-0006), universets model i graphd (ADR-0004 D4).

**Prototyper uden plads i målbilledet:** `walletd`, `presenced` og `contextd` i `app/daemons/`. De er ikke pakket (`packaging/daemon-policy.json`), men startes stadig af `runner.py` under udvikling. `contextd.py` modsiger EIRA-CONTEXT (testplan §5 pkt. 2).

## 2. Arbejdsform

- **Én agent ad gangen**, ét PR pr. trin. Ejeren merger; intet merges uden ejerens accept.
- **Kontrakt før kode.** En ny komponent får sin kontrakt i `specs/`, accepteret af ejeren, før den første kodelinje.
- **Færdig betyder afprøvet på den installerede pakke**, når trinnet rører rettigheder, AppArmor, systemd eller sessionen (som EIRA-CONSENT-AGENT §0.1 og EIRA-CONTEXT-testplanen N3).
- **Invarianter har mutanter.** En sikkerhedstest tæller først, når en realistisk fejl i koden får den til at fejle (EIRA-CONTEXT-testplan §2).
- **Hvert PR opdaterer** statustabellen i den berørte kontrakt, README's statustabel og CHANGELOG.

## 3. Rækkefølgen

```
F0 Luk bilag A ──┐
F1 Teknisk gæld ─┼─► F2 Kontekster ──► F3 Identitet og rettigheder pr. kontekst ──► F5 Web App Manager ──► F6 Livets indbakke
                 │        │                                                              ▲
                 │        └──► F4 ID-hjemmet ─────────────────────────────────────────────┘
                 └─► F7 EiraSystemAPI (kan køre mellem de store trin)      F8 Sprogmodel      F9 Release 1.0
```

Kontekster kommer før Web App Manager og indbakken, fordi begge bygger på konteksten: en webprofil *er* en kontekst (ADR-0005), og der er én indbakke pr. kontekst (ADR-0006).

### F0 — Luk bilag A

Det, der står tilbage af GATE-KERNEL bilag A og EIRA-CONSENT-AGENT.

| # | Leverance | Færdig når | Afhænger af |
|---|---|---|---|
| F0.1 | **R-6.2-patch i `eira-labwc`:** compositoren lægger samtykkeagentens vindue øverst og giver det fokus ud fra klientens effektive GID, og intet andet vindue kan lægge sig over det | Patchen ligger i `packaging/eira-labwc/patches/`; VM-test viser, at et almindeligt vindue ikke kan dække agenten | — |
| F0.2 | **Verifikation i en grafisk VM-session** (EIRA-CONSENT-AGENT V-1; O-6: procestræet under GDM) | `vm-install-acceptance` kører en rigtig labwc-session og afprøver agentens vindue, fokus og registrering | F0.1 |
| F0.3 | **Login mod en rigtig OIDC-udbyder** (udgivelsesbetingelse) | Login i den installerede VM mod ejerens udbyder; identiteten bliver `did:eira:<provider-id>.<subjekt>` | Ejeren: app-registrering |

### F1 — Teknisk gæld, der skal væk før de store trin

Små PR'er, der kan tages i vilkårlig rækkefølge.

| # | Leverance | Hvorfor |
|---|---|---|
| F1.1 | **Clippy og `cargo fmt` på alle Rust-crates i CI**, også `ui/src-tauri` og `eira-consent-agent` | CI kører clippy kun på `eira-core`, og fmt-tjekket dækker ikke `ui/src-tauri`. Clippy finder i dag tre ting i `ui/src-tauri/src/ipc.rs` (én løkke-indeksering i produktionskoden og to bevidste låse i testene, der skal markeres eksplicit), og `system_api/mod.rs` er ikke formateret |
| F1.2 | **Fjern `walletd`, `presenced` og `contextd`** fra `runner.py`, `app/daemons/` og deres tests | De er ikke i målbilledet; `contextd` modsiger EIRA-CONTEXT. Beløbsgrænsen i `contextd` hører under gaten og rettighedssættet. AI-INTERFACE §3 og §6 henter samtalekonteksten fra `contextd` og skal rettes til samtalelaget (EIRA-CONVERSATION) i samme PR |
| F1.3 | **Versioner og pakke-changelog:** `packaging/debian/changelog` siger `noble` og "Ubuntu 24.04"; Tauri-appen er 0.7.0, `ui/package.json` og `Cargo.toml` 0.3.0, pakken 1.0~rc1 | Én version for hele EiraOS, og pakken skal sige 26.04 (`resolute`) |
| F1.4 | **CI-robusthed:** upload af artefakter prøves igen ved fejl i GitHubs artefakttjeneste | Den fejlede 11. november, efter at bygget var grønt |

### F2 — Kontekster (EIRA-CONTEXT 1.0)

Det største trin. Kontrakten og testplanen er accepteret, så der skal ikke skrives ny kontrakt. Rækkefølgen følger testplanens niveauer: først rene funktioner (N1), så lagerservere (N2), så den installerede pakke (N3).

| # | Leverance | Invarianter (testplan) | Niveau |
|---|---|---|---|
| F2.1 | **Lagerformatet** (§6): blokke med AEAD, manifester, Merkle-træ, og referenceværktøjet `eira-context-export`, der læser et hjem uden EiraOS. Scriptet `scripts/check-mutants.sh` | B-1, B-2, B-3, M-1, U-1, X-1 | N1 |
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
| F3.2 | **RIGHTS-SET-revision:** et rettighedssæt bindes til (`tenant_id`, `context_id`) og ikke kun til en enhed; værgesignerede regler (`governance.source = guardian`) |
| F3.3 | **Sessioner pr. kontekst** i `identityd` og gaten; samtykkeagenten viser altid, i hvilken kontekst et samtykke gives |

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
| F5.1 | Kontrakt: app-manifest, motor-grænsesnit, profil = kontekst, links mellem apps (O-5), filer fra webapps ind i objektmodellen (O-6) | ADR-0004 accepteret |
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

## 4. De næste tre PR'er

1. **F0.1** R-6.2-patch i `eira-labwc`, da den lukker bilag A og er forudsætningen for F5.3.
2. **F1.1** clippy og fmt på alle crates, så fejl i Tauri-koden og agenten fanges i CI.
3. **F2.1** lagerformatet og `eira-context-export`, da det er rene funktioner uden root og første skridt i kontekster.

F1.2–F1.4 kan lægges ind mellem dem.

## 5. Ejerens beslutninger

| Beslutning | Blokerer |
|---|---|
| Accept af ADR-0004, ADR-0005 og ADR-0006 (står som "Foreslået", selvom EIRA-CONTEXT bygger på ADR-0005 og er accepteret) | F5, F6; formelt også F2 |
| Accept af EIRA-IDENTITY 1.0 (står som "Udkast", men er implementeret) | F3.1 |
| App-registrering hos en rigtig OIDC-udbyder | F0.3 og udgivelse |
| ADR-0006 O-1–O-3 | F6 |
| Forslaget om et menneske- og fællesskabscentreret fundament (#165) | Formuleringer i F4–F6 |
| Hvor ID-hjemmets tjeneste og genoprettelsen bor (repo og drift) | F4 |
| Én versionsplan for EiraOS (F1.3) | F9 |
| Pilot (Arbejde eller Møde) | Prioritering af F6 og F7 |
