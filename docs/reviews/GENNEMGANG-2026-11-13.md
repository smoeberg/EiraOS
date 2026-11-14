# Uafhængig gennemgang, 13. november 2026 — vurdering

**Grundlag:** En statisk gennemgang af `main` (zip, `VERSION` = `1.0.0-rc2`), læst og ikke kørt. Hvert fund er her efterprøvet mod koden på `main` (efter #212). Gennemgangen er input, ikke krav.

**Vurderinger:** som i [fundregistret 12. november](GENNEMGANG-2026-11-12.md): *Bekræftet* (fundet holder), *Delvist* (en del holder), *Afvist* (koden siger noget andet), *Dækket* (står allerede i planen). **Plan** er et forslag til trin, som ejeren skal acceptere, før det kommer i [udviklingsplanen](../UDVIKLINGSPLAN.md).

## Det vigtigste

Gennemgangen har ret i sin hovedpointe: **beviset er svagest der, hvor det betyder mest.** Paknings-CI'en starter ikke på ændringer i `app/**` eller `crates/**`, VM-testen venter ikke på testsuiten, og mutationstestene dækker kun kontekstlageret. Oven i det kan repoet (privat, uden GitHub Pro) ikke kræve grønne checks før merge. I dag er det altså ejerens disciplin, der holder kæden sammen, ikke CI. Det koster lidt at rette og bør komme før flere store trin (forslag F0c).

Den har også ret i, at dokumentationen på nogle få punkter siger mere, end koden gør. Det gælder især adgangsklassen `signed`, samtykkenøglen og `daemon_write`. Rettelserne er små, men de skal laves, for resten af dokumentationen er præcis.

Tre påstande holder ikke: strøm via EiraSystemAPI (gatens vej til logind findes; den direkte UI-vej er bevidst lukket), at rettighedssættene ikke er signerede (de er Ed25519-signerede), og at `walletd`, `presenced` og `contextd` stadig startes (fjernet i F1.2).

## Dokumentation mod kode (gennemgangens §2)

| # | Fund | Vurdering | Plan |
|---|---|---|---|
| G-1 | Adgangsklassen `signed` er en bearer-token, ikke en signatur | **Bekræftet** for synkroniseringen: `fleetd._authorize` → `DeviceRegistry.assert_authorized` sammenligner `sha256(auth_token)` og en offentlig nøgle, som klienten selv sender; ingen nonce, ingen signatur. Kommentaren i `fleetd.py:529` ("authorized by the device's signature") er forkert, og det samme er SIKKERHEDSMODEL §4. **Afvist** for rettighedssættene: de er Ed25519-signerede med anti-rollback (`app/rights/`) | F1c.1 |
| G-2 | "Samtykkenøglen ligger kun i agentens hukommelse" | **Bekræftet** som en dokumentationsfejl. Nøglen ligger i RAM (tmpfs, `/run/eira`, `app/consent_keys.py`), men i en fil ejet af `eira`, så identityd, gaten og delegationd kan læse den. Det er designet, men det er ikke "kun agenten". `forget()` har intet kald i produktionskoden, for der er ingen logout: nøglen lever til næste boot | F1c.2 |
| G-3 | `daemon_write` betyder "samme UID", ikke "en daemon" | **Bekræftet.** `service_uid()` er `os.getuid()`, og alle syv daemons samt `eira-rights-sync` kører som `User=eira`. `fleetd`, der taler med netværket, kan derfor skrive i `stated` og `audit.append`. SIKKERHEDSMODEL §4 siger "en anden daemon" | F1c.3 |
| G-4 | Audit-kæden kan genberegnes af en anden daemon | **Bekræftet.** Kæden er `sha256(prev + body)` uden nøgle, og AppArmor giver både `identityd` og `delegationd` `rwk` på `/data/eira-app.db`, hvor `gate_audit` ligger. FSS-seglet og Fleet-ankeret opdager det, men kun ved næste segl (grænsen står i `audit_anchor.py`). At to andre daemons har skriveadgang, står ikke nogen steder | F1c.4 |
| G-5 | "Tag dine data med" er kun et script | **Dækket.** F2.1 leverer formatet og `eira-context-export`; nøglehierarki, TPM og genoprettelse er F2.3 (#214) og F4. Planen siger det. Ingen tekst må kalde exit-garantien opfyldt, før F4.3 findes | — |
| G-6 | EiraSystemAPI's strøm returnerer altid `Unsupported` | **Afvist.** README beskriver gatens vej: `app/gate/executors.py` kalder logind over D-Bus. Den typede vej i `ui/src-tauri/src/system_api/mod.rs` afviser `power.request_action` med vilje, fordi sluk skal gå gennem gaten. Kommentaren "Until the Gate exists" er dog forældet | F1c.9 |
| G-7 | `specs/README.md` siger om kontekster: "Nothing is implemented yet" | **Bekræftet**, forældet siden F2.1 og F2.2 | F1c.9 |
| G-8 | `veritas-shield/` er en mock | **Bekræftet.** `parameters.json` har 4 parametre (README lover 200), og HUD'en har 88/100 skrevet direkte i HTML'en. Den bruges kun af `app/services/` i udviklingsbroen og er ikke i pakken. `app/veritas` (i pakken) er det rigtige | F1c.5 |

## Sikkerhedsfund (gennemgangens §3)

| # | Fund | Vurdering | Plan |
|---|---|---|---|
| G-9 | `capabilityd` hardkoder `policy_gate_passed: True` | **Bekræftet, men ikke kritisk.** Den har ingen socket og ingen unit og er ikke i pakken (`app-modules.txt`); den nås kun gennem udviklingsbroens `/v1/capability/resolve`. Den hører hjemme sammen med prototyperne fra F1.2 og skal fjernes, før nogen tror, den er godkendt | F1c.5 |
| G-10 | `fleetd` lytter på TCP `127.0.0.1:8765` i pakken | **Bekræftet.** `EIRA_FLEET_WS_ENABLED=1` i `systemd/eira-fleetd.service`; ingen klient bruger det, og `IPAddressAllow=localhost` gør det ubrugeligt udefra. Enhver lokal proces kan forbinde | F1c.6 |
| G-11 | `stated`s læsemetoder er ikke afgrænset pr. bruger | **Bekræftet.** `state.get`, `get_history`, `list` og `sync_pull` er `read`: alle i `eira-clients` kan læse hele tilstandskæden. På en maskine med én bruger er det ikke en lækage, men det bliver det med kontekster (F2.4), hvor det skal lukkes | F2.4 |
| G-12 | `veritasd` vægter lag 2 og C2PA, som ikke kan køre i pakken | **Bekræftet.** `EIRA_EUTL_SNAPSHOT` sættes intet sted, og `c2patool` er ikke en afhængighed, så 50 % af `trust_score` er strukturelt 0. Scoren skal sige, hvilke lag der faktisk er vurderet, i stedet for at tælle et manglende lag som et dårligt | F1c.7 |
| G-13 | `confirm` tjekker ikke, at bekræfteren er den, der foreslog handlingen | **Bekræftet.** `grant_consent` sammenligner `actor_identity`; `confirm` gør ikke. For en handling, der kræver samtykke, binder samtykket til sessionen. For en handling, der kun kræver bekræftelse, kan en anden bruger med en gyldig agent-session bekræfte, hvis hun kender `action_id`. Kræver flere brugere på maskinen, men er et rigtigt hul i en invariant | F1c.8 |
| G-14 | `delegation.check` kan bruges til at slå op, hvem der har delegeret hvad | **Bekræftet.** Et menneske kan spørge på vilkårlige `delegee_id` og `target` uden session. Kommentaren "Nobody anonymous learns which delegations exist" holder kun for modellen | F1c.8 |
| G-15 | Sessioner kan ikke tilbagekaldes | **Bekræftet.** 12 timers levetid, ingen logout, ingen sletning. Hænger sammen med G-2 | F1c.2 |
| G-16 | Ingen rate limiting, kvoter eller opbevaringsgrænse | **Bekræftet.** Modellen kan sende `gate.propose` uden grænse, og hver post skriver i databasen, audit-kæden og ankeret. Opbevaringen kræver en beslutning (audit må ikke bare slettes) | F1c.10 (beslutning) |
| G-17 | Samtykkeagentens socket tjekker ikke klienten | **Delvist.** Rigtigt, at der intet `SO_PEERCRED`-tjek er, men appen (samme UID) *skal* kunne bede agenten vise en handling. Agenten tager kun et `action_id`, henter selv gengivelsen fra gaten og viser kun brugerens egne ventende handlinger. Tilbage er, at et program kan åbne dialoger igen og igen; det løses med en grænse for, hvor tit agenten viser noget | F1c.10 |
| G-18 | `"untrusted"` matcher `"trusted"` i C2PA-vurderingen | **Bekræftet.** Med `valid: true` i manifestet og koden `signingCredential.untrusted` bliver resultatet `trusted`. En ægte fejl | F1c.7 |

## Test og CI (gennemgangens §4)

| # | Fund | Vurdering | Plan |
|---|---|---|---|
| G-19 | VM-acceptancen venter ikke på testene | **Bekræftet.** `build-deb` bygger med `nocheck`, `tests-on-ubuntu-26-04` kører parallelt og står ikke i `vm-install-acceptance`s `needs:`. Valget var bevidst (kortere kritisk vej i #191), men så skal testjobbet være en forudsætning for den samlede dom | F0c.1 |
| G-20 | `app/**` udløser ikke paknings-CI'en | **Bekræftet**, og det samme gælder `crates/**` (samtykkeagenten). Netop gaten, IPC-adgangen og agenten afprøves derfor aldrig på den installerede pakke, når kun de ændres | F0c.1 |
| G-21 | Mutationstestene dækker ikke sikkerhedskernen, og en fejl i opsamlingen tæller som dræbt | **Bekræftet.** `check-mutants.sh` kører kun `CTX-*`, og enhver exit ≠ 0 tæller som "caught". Pytest giver exit 2 eller 4 ved fejl i opsamlingen, så en mutant, der ødelægger importen, giver falsk grønt | F0c.2 |
| G-22 | Testene kører i udviklingstilstand (`EIRA_ENV=development`, mock-OIDC) | **Delvist.** Det er standard i `conftest.py`, og produktionsstien testes enkeltvis med `monkeypatch` (fx `installed()`). Men det er ikke synligt, hvilke invarianter der er afprøvet i produktionstilstand. VM-testen er den egentlige produktionsprøve | F0c.3 |
| G-23 | `ProvingGate` laver selv det bevis, gaten tjekker | **Delvist.** Rigtigt for Python-testene. Rust-agenten og Python-gaten deler testvektoren `consent-proof.json`, og VM-checket `consent-path-enforced` bruger den rigtige vej. Det er dækket, men spredt | — |
| G-24 | Checks i `eira-ci-report` kan bestå af forkerte grunde | **Bekræftet.** `! runuser … sg …` består også, hvis `sg` mangler, og `! journalctl … \| grep` består, hvis `journalctl` fejler. En negativ test skal have en positiv kontrol, som `consent-agent-secure-exec` allerede har | F0c.4 |
| G-25 | Samtykkeagentens AppArmor-profil indlæses ikke af `postinst` | **Bekræftet.** Globben `usr.bin.eira-*` rammer ikke `usr.lib.eira-os.eira-consent-agent`. Profilen indlæses ved næste boot af `apparmor.service`, så i VM'en, der genstarter, er den aktiv; ved en opgradering uden genstart er den ikke | F0c.4 |
| — | "~773 tests" | **Afvist** som tal: zip'en var ældre end F1; på `main` er der 934 Python-tests | — |

## Produktet og strategien (gennemgangens §5 og §7)

**§5 (det, der mangler)** er **Dækket:** launcher, indstillinger, indbakke, sprogmodel, kontekster og rigtigt login står i planen som F0.3, F2, F5–F8. Ét punkt er forkert: §5.4 siger, at `walletd`, `presenced` og `contextd` stadig startes af `runner.py`; de er fjernet i F1.2.

**§7 (væddemålene)** stemmer med planens retning: kontekster som produktet (F2), én færdig rejse med rigtigt login (F0.3 + F1b), en lokal sprogmodel bag kontrakten (F8), labwc og Chromium i stedet for egne komponenter (F5) og en ærlig tærskel for, hvad der loves. To ting er nye og værd at tage med:

- **Beviselig tillid som produkt:** reproducerbare builds, SBOM og signeret attestation, plus `SECURITY.md` (står allerede i plan §4 og venter på ejerens kontakt og svartid). Det passer til målgruppen (offentlig sektor), og der findes ikke et plantrin for det endnu. Forslag: et trin efter F0c (F9 forudsætter det alligevel).
- **De otte måltal i §7.5** kan blive README's statustabel for 1.0. Flere af dem findes allerede som planmål (U.2 tid og skridt, U.3 samtykker pr. dag, U.4 WCAG AA, `open_write` = 0).

Gennemgangens 90-dagesplan (§7.4) lægger CI-tillid og sikkerhedsgæld før kontekster. Det er en anden rækkefølge end den, der er i gang (F2.1 og F2.2 er merget, F2.3 er åben i #214). Mit forslag er at tage F0c nu, fordi det er lille og beskytter alt det andet, og at lægge F1c ind som små PR'er mellem F2-trinnene, som F1 blev det. Beslutningen er ejerens.

## Forslag til planen

**F0c — Bevisets tillid** (før næste store trin)

| # | Leverance | Færdig når |
|---|---|---|
| F0c.1 | Paknings-CI'en starter også på `app/**`, `crates/**` og `requirements*.txt`; et samlet slutjob kræver både testene på 26.04 og VM-acceptancen (G-19, G-20) | En PR, der kun ændrer `app/gate/`, kører VM-acceptancen, og en fejlende test gør hele workflowet rødt |
| F0c.2 | Mutationstest af gaten og IPC-adgangen (fx lag 5–7, `_rendering_intact`, `daemon_write_allowed`, adgangsklasser); kun exit 1 tæller som dræbt, andre exitkoder fejler kørslen (G-21) | `check-mutants.sh` kører `GATE-*` og `IPC-*` i CI; en mutant, der ødelægger importen, afvises |
| F0c.3 | En liste over sikkerhedsinvarianter med den test, der afprøver dem i produktionstilstand, og VM-checket (G-22); kan blive en del af implementeringsmatricen (plan §4 nr. 3) | Matricen viser for hver invariant: test, mutant, VM-check |
| F0c.4 | Negative checks i `eira-ci-report` får en positiv kontrol og `pipefail`; `postinst` indlæser alle profiler, også agentens (G-24, G-25) | Et check fejler, når dets værktøj mangler |
| F0c.5 | Merge kræver grønne checks: enten GitHub Pro eller et offentligt repo, så branch protection virker. Ellers en skrevet regel om, at ejeren kun merger med grønt slutjob | Ejeren har valgt |

**F1c — Sikkerhedsgæld fra gennemgangen 13. november** (små PR'er)

| # | Leverance | Fund |
|---|---|---|
| F1c.1 | Synkronisering med challenge og signatur med enhedens nøgle (fra F2.3) i stedet for bearer-token, eller klassen omdøbes til `token`, og dokumentationen siger det | G-1 |
| F1c.2 | Logout: sessionen slettes, `consent_keys.forget()` kaldes, og en session kan tilbagekaldes; SIKKERHEDSMODEL §6 beskriver, hvem der kan læse nøglen | G-2, G-15 |
| F1c.3 | `daemon_write` bundet til navngivne tjenester (egne brugere pr. daemon, eller kalderens systemd-unit via cgroup), så `fleetd` og `rights-sync` ikke kan skrive i `stated` | G-3 |
| F1c.4 | `gate_audit` i sin egen database, som kun `intentd` kan skrive i (AppArmor); på sigt en kæde med nøgle (TPM eller Fleet) | G-4 |
| F1c.5 | `capabilityd`, `app/routers/capability.py`, `app/services/*veritas*`, `veritas-shield/` fjernet eller arkiveret; projektbeskrivelsen opdateret | G-8, G-9 |
| F1c.6 | `fleetd`s WebSocket-lytter slået fra i pakken, indtil en klient findes og er beskrevet | G-10 |
| F1c.7 | C2PA: `untrusted` matcher ikke `trusted`; `trust_score` siger, hvilke lag der er vurderet, og tæller ikke et manglende lag som 0 | G-12, G-18 |
| F1c.8 | `confirm` kræver den foreslående identitet; `delegation.check` kræver en session og svarer kun om kalderens egne delegationer (modellen som nu) | G-13, G-14 |
| F1c.9 | Forældede sætninger: `specs/README.md` om kontekster, kommentaren i `system_api/mod.rs`, `fleetd.py:529` | G-6, G-7 |
| F1c.10 | Ejerens beslutning om grænser: hvor mange forslag modellen må sende, hvor tit agenten må vise en dialog, og hvor længe beskedtekst og audit gemmes | G-16, G-17 |
