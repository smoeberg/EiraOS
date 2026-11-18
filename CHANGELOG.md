# Changelog

Alle væsentlige ændringer i EiraOS dokumenteres her. Datoer angiver leveringsperioden, ikke nødvendigvis en publiceret release.

## [Unreleased]

### Hardware Trust & Open Silicon (forslag)
- Tilføjet et ikke-normativt arkitekturudkast om hardwareprofiler, evidensniveauer, Fleet/Gate-grænser, den eksisterende TPM-enrollment og en mulig rolle for GoIT Hardware Hub. Ingen runtime, daemon, Gate-, Fleet- eller Phase 0-kontrakter ændres; notatet afventer ejerreview.

### Kontekster (EIRA-CONTEXT 1.0)
- F2.1: lagerformatet (§6) i `app/context/`: blokke, manifester, enhedsliste, FastCDC og et lokalt hjem; referenceværktøjet
  `tools/eira-context-export/`, som læser et hjem uden EiraOS; testvektorer; B-1, B-2 og B-3 verificeret på N1 med 16
  mutanter (`scripts/check-mutants.sh`). Kontrakten har fået præciseringer i §6.6, og testplanen har et nyt fund om
  enhedslisten.
- F2.2: kontekst-hjem på S3 og WebDAV (`app/context/remote.py`) med opret-hvis-fraværende (`If-None-Match: *`). Et hjem
  prøves ved tilknytning og afvises med `E_CONTEXT_HOME_UNSUPPORTED`, hvis det overskriver. En manifestkollision afvises
  og auditeres. Nyt CI-job `context-home` kører H-1 mod MinIO, Apache `mod_dav`, moto og WsgiDAV; mutanterne er flyttet
  dertil (20 i alt). Testplanens fund 6: ingen af de testede WebDAV-servere holder H-1 under samtidige uploads.
- ADR-0009 (forslag): datalagets byggesten. NextGraph bruges som forlæg, ikke som afhængighed; CRDT via Automerge eller
  Yrs bag en grænseflade.

### Model og AI-grænseflade
- AI-INTERFACE 1.0 er afstemt mod runtime efter #190: `eira-modeld` ejer adapterkaldet, samtalekontekst kommer fra appen/EIRA-CONVERSATION (ikke `contextd`), forespørgsler uden samtale begrænses til systemhandlinger, og EDP/EiraSystemAPI beskrives som adskilte handlingsfamilier bag samme Gate Kernel. Den aktive adapter er fortsat regelbaseret; ingen sprogmodel eller modelruntime er tilføjet.

### Model evaluation (F8.1 — draft)
- Added the draft EIRA Model Evaluation 1.0 contract: versioned multilingual corpus, repeatable adapter runs, per-language reporting, offline verification, and independent Gate security acceptance. No evaluation harness or model selection is implemented by this documentation-only change.

Leveret 6.–12. november 2026 (PR #128 og frem). Ingen release er tagget siden 0.7.0.

### Dokumentation
- `CONTRIBUTING.md`: hvad der gælder, de hårde regler og vejen for en ny beskyttet handling (skema → policy →
  gengivelse → executor → rettighed → AppArmor → model → UI → test → VM-check → audit). PR-skabelon. `.cursor`-reglen
  pegede på arkiverede filer og sessionsbundet tilstand og er rettet.
- Vurdering af den uafhængige gennemgang 13.–14. november ([`docs/reviews/GENNEMGANG-2026-11-13.md`](docs/reviews/GENNEMGANG-2026-11-13.md)):
  42 fund fra to runder efterprøvet mod `main`, de fleste bekræftet, og forslag til to nye trin, F0c (bevisets
  tillid i CI) og F1c (sikkerhedsgæld), accepteret af ejeren 14. november og skrevet ind i udviklingsplanen.
- Forældede sætninger rettet: `specs/README.md` og README om kontekster (lageret og hjemmene er leveret, daemonen
  ikke) og om R-6.2 (implementeret med `<trustedGroup>`-patchen), `databaseskema.md` om `stated` (Python-lageret på en
  installeret maskine), kommentaren i `system_api/mod.rs` (gaten findes; den typede vej afviser sluk med vilje),
  kommentaren i `fleetd.py` og SIKKERHEDSMODEL §4, som kaldte synkroniseringens bearer-token en signatur
  (udviklingsplan F1c.9, gennemgang G-6, G-7, G-40 til G-42).

### CI
- Packaging Acceptance er kortere: ISO og VM-installation i samme job (CI-billedet uploades og hentes ikke længere), ISO'er uploades uden ny komprimering, VM-disken bruger `cache=unsafe`, Rust-bygget har sccache, og testsuiterne på Ubuntu 26.04's Python og Node kører i et parallelt job i stedet for inde i pakkebygget (`DEB_BUILD_OPTIONS=nocheck`). Basis-ISO'ens cache gemmes kun, når ISO'en skifter.
- Packaging Acceptance rydder disk, når runneren har under 40 GB fri, og fejler tydeligt under 30 GB (ISO-bygget løb tør for plads på en runner med 16 GB fri).
- VM-checkene kan ikke længere bestå af forkerte grunde: negative checks går gennem hjælpere med en positiv kontrol. `postinst` indlæser også samtykkeagentens AppArmor-profil, og VM-checket `consent-agent-profile-enforced` viser den.
- Rust bygges med låste afhængigheder: workspacets `Cargo.lock` er committet, og alle `cargo build`, `test` og `clippy` i CI bruger `--locked`.
- Opgraderingstest i VM (`vm-upgrade-acceptance`): på en pull request bygges også base-grenens pakke. Den installeres, og CI opgraderer det kørende system til pull requestens pakke og kører derefter alle checks.

### Gate Kernel og sikkerhed
- Gate: sessioner uden udløbstidspunkt er ikke længere gyldige (fail-closed).
- Fleet e2ee: hver retning i et par har sin egen nøgle, nonces huskes i et glidende vindue, og en genafspillet envelope afvises.
- F0b.4: `identity.verify_production_certificate` er kun for daemons; desktop-brugeren kan ikke længere få `identityd` til at skrive audit-hændelser.
