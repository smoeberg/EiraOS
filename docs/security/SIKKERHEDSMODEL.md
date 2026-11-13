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

## 4. Adgangsklasser pr. IPC-metode

Hver metode har præcis én klasse (`app/ipc/access.py`), og `JsonRpcServer.register` afviser en metode uden klasse. Kataloget over alle metoder genereres fra daemonernes egne registreringer: [`docs/reference/ipc-katalog.md`](../reference/ipc-katalog.md) (`scripts/ipc_catalog.py --check` i CI).

| Klasse | Metoder | Hvem må | Håndhævet af | Eksempler |
|---|---|---|---|---|
| `read` | 24 | Alle på socketen | Ændrer intet | `graph.spatial_snapshot`, `graph.temporal_query`, `health` |
| `caller` | 28 | Alle, men handleren får kernens kalder og handler kun på dennes vegne | Handleren (`wants_peer`) | `dashboard.get`, `presentation.mode_set`, `identity.session`, `gate.propose`; `gate.consent`/`gate.confirm`, hvor gaten desuden kræver agentens gruppe |
| `daemon_write` | 4 | Kun tjenestebrugeren (en anden daemon) | Serveren, før handleren: `E_ACCESS_DAEMON_ONLY` | `state.append`, `state.sync_push`, `audit.append`, `identity.verify_production_certificate` |
| `signed` | 4 | Den, der kan bevise sin ret med en signatur | Handleren | Fleets `fleet.device.enroll` og `sync.*` |
| `refused` | 4 | Ingen | Svarer altid med en afvisning | `intent.execute`, `intent.confirm`, `journey.advance` (`E_GATE_REQUIRED`), `identity.step_up` |
| `open_write` | **0** | Alle, uden kontrol: **et kendt hul** | Kun tilladt med et plantrin | Ingen tilbage siden F0b.4 |

Tallene er for de syv produktionsdaemons pr. denne PR; kataloget er den aktuelle kilde.

Beviser: `tests/test_ipc_access.py` (hver metode har en klasse; `open_write` er præcis de kendte huller, og listen er tom; `daemon_write` afvises fra en anden bruger og uden kalder; root er ikke daemon-skriver; desktop-brugeren kan hverken skrive i `stated` eller få `identityd` til at skrive audit). VM: `user-cannot-write-stated`, `user-cannot-make-identityd-audit`, `user-mode-without-session`.

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
- Samtykkenøglen ligger kun i agentens hukommelse. `intentd` og `identityd` nægter at starte, hvis gruppen får medlemmer.
- Dens vindue ligger øverst og har fokus, mens det vises (`<trustedGroup>` i `eira-labwc`, R-6.2). Ingen klient har privilegerede Wayland-protokoller (R-6.1).

Eira UI viser aldrig gatens gengivelse som noget at godkende; appen sender kun `action_id`.

Beviser: `tests/test_consent_agent_path.py`, `packaging/eira-labwc/verify-trusted.sh` og `verify-globals.sh` (i CI). VM: `consent-*`, `labwc-trusts-consent-group`.

## 7. Indeslutning

- **AppArmor** har en profil pr. daemon (`packaging/apparmor/`), som indlæses ved installation. VM: `modeld-profile-enforced`, `identityd-no-apparmor-denials`.
- **systemd** hærder alle tjenester (`NoNewPrivileges`, `ProtectSystem=strict` m.fl.). Modelprocessen har intet net. VM: `modeld-confined`, `modeld-no-network`.
- **Sessionen** er kun EiraOS: andre login-sessioner skjules, og miljøet renses (`packaging/session/`). VM: `only-eira-session`, `gnome-session-hidden`.

## 8. Kendte begrænsninger

- **Grafisk session:** R-6.1–R-6.3 er afprøvet headless, ikke i en grafisk VM-session (UDVIKLINGSPLAN F0.2).
- **Login:** uden en rigtig login-udbyder (F0.3) er der ingen autentificeret session på en installeret maskine, så gaten afviser alt, der kræver en.
- **Root og fysisk adgang** er uden for modellen (§1).

Fundregistret ([`docs/reviews/GENNEMGANG-2026-11-12.md`](../reviews/GENNEMGANG-2026-11-12.md)) har status på hvert kendt fund.
