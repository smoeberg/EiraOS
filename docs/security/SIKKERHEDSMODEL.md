# EiraOS' sikkerhedsmodel

Status: beskriver koden på `main` pr. 13. november 2026 (UDVIKLINGSPLAN F0b.3, fundregister D-3). Afløser `socket-permissions.md`, som beskrev en svagere adfærd end koden.

Hver påstand nedenfor peger på koden, der gør det, og på testen eller VM-checket, der beviser det. VM-checkene står i `packaging/installer/ci/eira-ci-report` og køres på den installerede ISO i CI.

## 1. Hvem vi beskytter mod

| Modpart | Inden for modellen? | Hvad den kan |
|---|---|---|
| Et program, der kører som desktop-brugeren | **Ja, det vigtigste** | Alt, hvad brugeren kan: læse IPC-tokenet, forbinde til alle sockets, starte processer, vise vinduer |
| Modelprocessen (`eira-model`) | **Ja** | Foreslå handlinger under en delegation; intet net |
| En anden lokal bruger | Ja | Som desktop-brugeren, men uden for den første brugers sessioner og tilstand |
| Netværket | Ja | Intet direkte: daemons lytter kun på Unix-sockets |
| **root** | **Nej** | Alt. Root kan ændre pakken, nøglerne og kernen; ingen kontrol i brugerland kan stoppe det (EIRA-CONSENT-AGENT §9) |
| Fysisk adgang, kernen, firmware | Nej | Uden for modellen |

## 2. Identiteter og grupper

Oprettes af `packaging/debian/postinst`:

| Bruger/gruppe | Hvem | Medlemmer | Kan |
|---|---|---|---|
| `eira` (bruger og gruppe) | Daemons | Kun `eira` | Eje `/data` (gatens database, rettigheder) og skrive i `stated` |
| `eira-clients` | Klienter | Desktop-brugere, `eira`, `eira-model` | Forbinde til sockets; læse IPC-tokenet |
| `eira-model` | Modelprocessen | Ingen | Intet net (`PrivateNetwork=true`, kun `AF_UNIX`); aldrig i `eira` |
| `eira-consent` | Samtykkeagenten | **Ingen**, ingen adgangskode | Kun den setgid-installerede agent har gruppen som effektiv GID |
| `eira-fleet-admin` | Fleet-administratorer | Tom; tilføjes bevidst | Oprette parringskoder og tilbagekalde enheder |

Desktop-brugeren er medlem af `eira-clients`, aldrig af `eira` (ADR-0003: substratet beskytter Eira-laget). Ældre installationer flyttes ved opgradering.

Beviser: VM-checkene `user-in-eira-clients`, `user-not-in-eira`, `user-cannot-write-gate-db`, `model-not-in-eira`, `model-is-system-uid`, `consent-group-no-members`, `consent-group-no-password`, `consent-gid-not-obtainable`.

## 3. Grænsen: socket-rettigheder plus kernens kalder

**Sockets.** `setup_unix_socket` (`app/ipc/socket_security.py`) opretter hver socket med mode `0660` og gruppen `eira-clients`. Under `/run/eira` (installeret system) nægter daemonen at starte, hvis gruppen ikke findes, eller `chown` fejler. Det er en ødelagt installation, ikke et udviklingsmiljø. Kun i udvikling og CI falder den tilbage til processens egen gruppe med en advarsel.

**Kalderen.** For hver forbindelse læser daemonen kernens oplysninger om peeren (`SO_PEERCRED` og `SO_PEERGROUPS`): UID, GID og supplerende grupper, som de var ved `connect()`. Det er den eneste identitet, der tæller. En parameter kan aldrig give en klient en anden identitet (F1.5).

**IPC-tokenet beskytter ikke mod desktop-brugeren.** `/etc/eira/eira.conf` er `root:eira-clients 0640`, så brugeren kan læse det. Tokenet beviser kun, at kalderen er en del af installationen, og det giver ingen rettigheder i sig selv (fundregister S-11). Grænsen er adgangsklasserne nedenfor.

**Root** får altid forbindelse (`socket_access_allowed`, fundregister S-12). Root er dog ikke en daemon: `daemon_write` kræver tjenestebrugerens UID, også for root.

**Hvilken daemon kalder.** Alle syv daemons og rettighedssynkroniseringen kører som `eira`, så UID'et siger ikke, hvilken daemon der kalder. Til `daemon_write` spørger serveren derfor også kernen (`app/ipc/access.py`, F1c.3): kalderens AppArmor-etiket fra `SO_PEERSEC` (`/usr/bin/eira-fleetd (enforce)`), eller, hvis kalderen ikke er under en profil, den systemd-unit, kalderens cgroup ligger i (`eira-fleetd.service`). En proces under en anden profil (fx `eira-rights-apply`) falder ikke tilbage til sin cgroup, en profil i complain-tilstand tæller ikke, og en stak tæller kun, hvis den ud over `unconfined` består af præcis én daemons profil (`/usr/bin/eira-fleetd//&unconfined`, som et profilskift fra en ubegrænset proces giver). Begge dele sætter kernen; en daemon kan ikke skifte profil (profilerne tillader det ikke) eller flytte sig til en anden unit (cgroup-træet er roots). Desktop-brugeren kan godt sætte sig under en daemons profil, men får ikke UID'et, og derfor kræves begge. I udvikling (sockets uden for `/run/eira`) er der hverken profiler eller units; der gælder UID'et alene, medmindre kalderen er en navngiven daemon.

## 4. Adgangsklasser pr. IPC-metode

Hver metode har præcis én klasse (`app/ipc/access.py`), og `JsonRpcServer.register` afviser en metode uden klasse. Kataloget over alle metoder genereres fra daemonernes egne registreringer: [`docs/reference/ipc-katalog.md`](../reference/ipc-katalog.md) (`scripts/ipc_catalog.py --check` i CI).

| Klasse | Metoder | Hvem må | Håndhævet af | Eksempler |
|---|---|---|---|---|
| `read` | 24 | Alle på socketen | Ændrer intet | `graph.spatial_snapshot`, `graph.temporal_query`, `health` |
| `caller` | 28 | Alle, men handleren får kernens kalder og handler kun på dennes vegne | Handleren (`wants_peer`) | `dashboard.get`, `presentation.mode_set`, `identity.session`, `gate.propose`; `gate.consent`/`gate.confirm`, hvor gaten desuden kræver agentens gruppe |
| `daemon_write` | 4 | Kun de navngivne daemons, som tjenestebrugeren (§3) | Serveren, før handleren: `E_ACCESS_DAEMON_ONLY` | `state.append` (kun `fleetd`), `audit.append` (kun `identityd`, `delegationd`), `state.sync_push` og `identity.verify_production_certificate` (ingen kalder i dag, så ingen må) |
| `signed` | 4 | Den, der kan bevise sin ret med en signatur | Handleren | Fleets `fleet.device.enroll` og `sync.*` |
| `refused` | 4 | Ingen | Svarer altid med en afvisning | `intent.execute`, `intent.confirm`, `journey.advance` (`E_GATE_REQUIRED`), `identity.step_up` |
| `open_write` | **0** | Alle, uden kontrol: **et kendt hul** | Kun tilladt med et plantrin | Ingen tilbage siden F0b.4 |

Tallene er for de syv produktionsdaemons pr. denne PR; kataloget er den aktuelle kilde.

Beviser: `tests/test_ipc_access.py` (hver metode har en klasse; `open_write` er præcis de kendte huller, og listen er tom; `daemon_write` afvises fra en anden bruger og uden kalder; root er ikke daemon-skriver; desktop-brugeren kan hverken skrive i `stated` eller få `identityd` til at skrive audit) og `tests/test_daemon_isolation.py` (kun de navngivne daemons; samme UID er ikke nok; etiket før cgroup; complain-tilstand tæller ikke; hvert kald i koden står i politikken, og profilerne svarer til den). Mutanter `IPC-DW-1` til `IPC-DW-6`. VM: `user-cannot-write-stated`, `user-cannot-make-identityd-audit`, `user-mode-without-session`, `eira-uid-is-not-a-daemon`, `eira-uid-cannot-audit`, `fleetd-may-append-state`, `graphd-cannot-append-state`, `fleetd-cannot-audit`, `intentd-cannot-reach-stated`.

**Tilbage:** `fleetd` taler med netværket og må stadig skrive tilstande i `stated`, fordi det er dens opgave at modtage synkroniserede blokke fra parrede enheder (`sync.push_blocks`, som tjekker signaturen og hashkæden). En kompromitteret `fleetd` kan altså stadig tilføje tilstande, men ikke skrive audit og ikke bruge batch-vejen.

## 5. Gaten

Alt, der ændrer noget uden for brugerens egen tilstand, går gennem gaten i `eira-intentd` (GATE-KERNEL 1.0). Gaten:

1. kender kalderen fra kernen (menneske eller model, `app/gate/caller.py`);
2. tjekker skema, policy, sikkerhedsniveau og rettigheder fra Fleet (lag 1–6);
3. lader kun modellen foreslå under en delegation fra mennesket;
4. kræver samtykke og bekræftelse fra samtykkeagenten for det, der er irreversibelt;
5. skriver hver beslutning i sin egen audit-kæde, som forankres i journalen og forsegles (FSS).

Beviser: `tests/test_gate_kernel.py`, `tests/test_gate_system.py`, `tests/test_intent_to_gate.py` (hele kæden; modellen kan ikke samtykke). VM: `gate-ipc-reject`, `modeld-reaches-gate-and-is-refused`, `intent-power-reaches-gate-and-is-refused`, `model-cannot-consent`, `audit-*`.

## 6. Samtykkeagenten

Kun `eira-consent-agent` kan samtykke og bekræfte (EIRA-CONSENT-AGENT):

- Den er installeret setgid `eira-consent`, en gruppe uden medlemmer. Gaten genkender den på den effektive GID ved `connect()`.
- Samtykkenøglen ligger aldrig på disk. Den dannes af `identityd` ved login og ligger i RAM: i agentens hukommelse og i `/run/eira/consent-keys.db` (tmpfs, ejet af `eira`, `0600`). Kun `identityd` kan skrive den; gaten (`intentd`) og `delegationd` kan kun læse den (AppArmor `rk`, skrivebeskyttet forbindelse), fordi de efterprøver beviserne med den. Da alle daemons kører som `eira`, er det AppArmor og ikke filrettighederne, der holder skrivningen til `identityd` (F1c.3 binder `daemon_write` til navngivne daemons, §3). En nøgle fra en tidligere opstart bruges aldrig.
- **Logout** (`identity.logout`, knappen "Log ud") afslutter sessionen med det samme og sletter dens nøgle. Gaten, `delegationd` og agenten afviser derefter sessionen, og et samtykke givet i den kan ikke længere bekræftes. Ved næste login slettes også nøglerne for alle udløbne sessioner. Kun den OS-bruger, sessionen er bundet til, kan logge den ud.
- `intentd` og `identityd` nægter at starte, hvis gruppen `eira-consent` får medlemmer.
- Dens vindue ligger øverst og har fokus, mens det vises (`<trustedGroup>` i `eira-labwc`, R-6.2). Ingen klient har privilegerede Wayland-protokoller (R-6.1).

Eira UI viser aldrig gatens gengivelse som noget at godkende; appen sender kun `action_id`.

Beviser: `tests/test_consent_agent_path.py`, `tests/test_logout.py`, `tests/test_consent_keys_ram_only.py`, mutant `GATE-S-1`, `packaging/eira-labwc/verify-trusted.sh` og `verify-globals.sh` (i CI). VM: `consent-*`, `labwc-trusts-consent-group`.

## 7. Indeslutning

- **AppArmor** har en profil pr. daemon (`packaging/apparmor/`), som indlæses ved installation. Hver daemon kan kun oprette sin egen socket i `/run/eira` og kun forbinde til de daemons, den kalder (`ipc_connects` i `packaging/daemon-policy.json`: `identityd`, `delegationd`, `graphd` og `fleetd` kalder `stated`; `veritasd` kalder `graphd`; `stated` og `intentd` kalder ingen). Ingen daemon deler en logmappe; de logger til journalen under deres egen unit (F1c.3). Tilbage: AppArmor skelner ikke mellem at forbinde til og at slette en sti-socket, så en daemon kan slette socketen for en daemon, den kalder. VM: `modeld-profile-enforced`, `identityd-no-apparmor-denials`, `intentd-cannot-reach-stated`.
- **systemd** hærder alle tjenester (`NoNewPrivileges`, `ProtectSystem=strict` m.fl.). Modelprocessen har intet net. VM: `modeld-confined`, `modeld-no-network`.
- **Sessionen** er kun EiraOS: andre login-sessioner skjules, og miljøet renses (`packaging/session/`). VM: `only-eira-session`, `gnome-session-hidden`.

## 8. Kendte begrænsninger

- **Grafisk session:** R-6.1–R-6.3 er afprøvet headless, ikke i en grafisk VM-session (UDVIKLINGSPLAN F0.2).
- **Login:** uden en rigtig login-udbyder (F0.3) er der ingen autentificeret session på en installeret maskine, så gaten afviser alt, der kræver en.
- **Root og fysisk adgang** er uden for modellen (§1).

Fundregistret ([`docs/reviews/GENNEMGANG-2026-11-12.md`](../reviews/GENNEMGANG-2026-11-12.md)) har status på hvert kendt fund.
