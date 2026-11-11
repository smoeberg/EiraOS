# EIRA Consent Agent 0.2 — betroet vej til samtykke mod programmer, der kører som brugeren

**Status:** Udkast til ejerens accept. **Ikke normativ**, før ejeren har accepteret det. Testplanen er et separat trin efter accept.
**Version:** 0.2 (10. november 2026: 0.2 beslutninger om compositor, toolkit, FIDO2 og `hidepid`, §6, §10)
**Lukker:** "Rest" under GATE-KERNEL bilag A pkt. 1, *Betroet vej til samtykke*
**Erstatter:** Agent 3-opgaven "LD_PRELOAD Consent Path" i `docs/AGENT_WORK_ASSIGNMENTS.md` (se §2)
**Berører:** `identityd`, Gate (`intentd`, lag 5), Tauri-appen (`ui/src-tauri`), sessionen (`eira-session`, labwc-konfiguration), pakken (`eira-os-core`), ADR-0003

---

## 0. Status for sikkerhedsegenskaberne

Intet i denne kontrakt er en opnået sikkerhedsegenskab. Alle punkter nedenfor er **krav, der afventer verifikation**. Et punkt markeres først som verificeret, når der findes en test, der fejler, hvis egenskaben brydes (mutationstjek), og for kerne- og compositoregenskaber en VM-test.

| Egenskab | Krav | Implementeret | Verificeret |
|---|---|---|---|
| Ingen privilegerede Wayland-protokoller til klienter | R-6.1 | `eira-labwc` + tom `<privilegedInterfaces>` (#163) | Kun lokalt (headless, mutationstjek). Ikke i VM-session |
| Intet vindue over agenten; agenten har fokus | R-6.2 | Nej (labwc-patch mangler) | Nej |
| Beslutning tidligst efter 750 ms fokus | R-6.3 | Nej | Nej |
| setgid-installation `root:eira-consent 2755` og gruppe uden medlemmer/adgangskode, fail-closed ved start | §3 | Nej | Nej |
| Effektiv GID via `SO_PEERCRED` identificerer agenten | §3 pkt. 3 | Nej | Nej. Holder kun, hvis installationskæden ovenfor er fail-closed |
| `LD_PRELOAD`/ptrace/`/proc/<pid>/mem` mod agenten afvist af kernen | §3 pkt. 1–2 | Nej | Nej |
| Agentregistrering mod sessionens compositor | §5.2 | Nej | Nej (forudsætning O-6 ikke verificeret) |
| Nøgleudlevering kun til registreret agent; appen får ingen nøgle | §5.3 | Nej (appen har i dag nøglen) | Nej |
| Gaten afviser samtykke uden agentens GID (`E_CONSENT_PATH`) | §7 | Nej | Nej |
| Samtykkenøglen skrives aldrig til disk og er ugyldig efter genstart | §5.3 | Nej (`consent_key` ligger i dag i sessionsdatabasen på disk og overlever genstart) | Nej |
| Agentens miljø-, fd- og argumentkrav | R-5.1–R-5.5 | Nej | Nej |

Indtil alle rækker er verificeret, gælder den nuværende formulering i ADR-0003 og GATE-KERNEL bilag A pkt. 1 ("Rest") uændret: et program, der kører som brugeren, kan i dag stadig få fat i samtykkenøglen.

### 0.1 Verifikationskrav (testplanen)

En egenskab i tabellen ovenfor må først markeres som verificeret, når disse tests findes og består på **det installerede system** (pakken installeret i en VM, ikke kildetræet), og hver fejler, hvis egenskaben brydes (mutationstjek):

**V-1 Compositorens tillid (§5.2, O-6) — det svageste led.**
- Fastlæg i VM'en den faktiske procestræ på den understøttede opsætning (Ubuntu 26.04, greetd, `eira-session`, `eira-labwc`): forventet *logind-sessionens leader → `eira-session` → labwc*.
- Registreringen skal afvise: (a) en compositor startet fra brugerens shell; (b) en indlejret compositor; (c) en compositor med genbrugt PID men anden starttid.
- Afviger det faktiske procestræ, ændres §5.2 til at beskrive den invariant, der faktisk håndhæves, og ikke det forventede træ.

**V-2 Hele setgid-kæden (§3), på den installerede pakke.**
1. `eira-consent-agent` er `root:eira-consent` med mode `2755`.
2. Gruppen `eira-consent` har ingen medlemmer og kan ikke opnås via `newgrp`/`sg`.
3. Den kørende agent har de forventede reelle, effektive og gemte UID'er og GID'er.
4. `SO_PEERCRED`, som gaten ser, indeholder den forventede effektive GID.
5. En almindelig brugerproces kan ikke opnå den GID.
6. `LD_PRELOAD`, ptrace og `/proc/<pid>/mem` mod agenten fejler.
7. Fjernes eller ændres setgid-bitten eller ejerskabet, fejler systemet lukket: gaten og `identityd` nægter at starte (§3), og intet samtykke accepteres.

**V-3 Øvrige rækker** i tabellen får hver mindst én test efter samme princip (R-6.1–R-6.3 i en rigtig session, nøgleudlevering, `E_CONSENT_PATH`, R-5.1–R-5.5).

## 1. Problemet

I dag får appens Rust-del samtykkenøglen ved login og laver `proof = HMAC(nøgle, …)` for `gate.consent` og `gate.confirm` (`app/gate/consent_proof.py`, `ui/src-tauri/src/login.rs`). Gaten afviser alt uden gyldigt bevis med `E_CONSENT_PROOF`.

GATE-KERNEL siger selv, hvor det holder op: *et program under brugerens UID kan dræbe appen og starte en ny kopi med indsprøjtede biblioteker (`LD_PRELOAD`), og brugeren logger så ind gennem den.* Det indsprøjtede bibliotek læser nøglen i appens hukommelse og kan derefter samtykke til hvad som helst. Yama-ptrace hjælper ikke, fordi angriberen er forælder til den nye kopi.

**Mål for denne kontrakt:** Et program, der kører som brugeren, kan ikke selv frembringe et samtykke eller en bekræftelse, som gaten accepterer.

## 2. Hvad der ikke virker, og hvorfor

| Forslag | Hvorfor det afvises |
|---|---|
| **"Kun processer med LD_PRELOAD kan samtykke"** (Agent 3-opgaven) | Vender truslen om til mekanismen. Enhver proces under samme UID kan selv sætte `LD_PRELOAD`. Et bibliotek, der "verificerer sin egen integritet", kører inde i den proces, angriberen styrer, så det kan ikke bevise noget over for en anden part. Det ville åbne en ny vej uden om gaten. |
| **`identityd` tjekker `/proc/<pid>/exe` ved login** | Kræver ptrace-adgang til appen, og `identityd` kører som `eira` med `CapabilityBoundingSet=` (ingen capabilities). Den skal ikke have `CAP_SYS_PTRACE`. Selv med adgang ville tjekket ikke fange den ægte binære fil med et indsprøjtet bibliotek. |
| **Rent miljø ved sessionsstart alene** | Gør det sværere, men angrebet sker efter sessionsstart. Leveret separat som hærdning (`eira-session`, PR "fix/session-clean-environment"). |
| **Gør Tauri-appen setgid** | GTK nægter at starte setgid ("not a supported use of GTK"), og WebKitGTK med et helt webview er for stor en flade til at køre med forhøjede rettigheder. |

## 3. Det, kernen garanterer, og som vi bygger på

En binær fil, der er **setgid til en gruppe, som ingen bruger er medlem af**, giver tre ting, som en proces under samme UID ikke kan forfalske:

1. **Dynamic loader i sikker tilstand.** Ved setgid-exec sætter kernen `AT_SECURE`. `ld.so` ignorerer da `LD_PRELOAD` og `LD_LIBRARY_PATH` (bortset fra biblioteker i standardstier, der selv er markeret setuid), og glibc fjerner de farlige variabler fra miljøet.
2. **Ingen ptrace og ingen læsning af hukommelsen.** Processen bliver ikke-dumpbar, og `ptrace_may_access` kræver i forvejen, at kalderens GID svarer til målets reelle, effektive og gemte GID. Det kan en almindelig brugerproces ikke opfylde. Det samme gælder `/proc/<pid>/mem` og `environ`.
3. **Identitet på socket'en.** `SO_PEERCRED` leverer den *effektive* GID ved `connect()`. En peer med `gid = eira-consent` er altså en proces, der kører den binære fil. Det kan kun kernen afgøre, og forbindelsen kan ikke forfalskes af kalderen.

**Forudsætninger (fail closed, som `require_model_identity`):** `intentd` og `identityd` nægter at starte på et installeret system, hvis

- gruppen `eira-consent` mangler, er en bruger-GID (≥ 1000) eller deler GID med `eira`, `eira-clients` eller `eira-model`;
- gruppen har medlemmer (`getent group`), eller en bruger har den som primær gruppe;
- `/etc/gshadow` giver gruppen en adgangskode (ellers kan `newgrp`/`sg` give en brugerproces den som effektiv GID);
- `/usr/lib/eira-os/eira-consent-agent` ikke er `root:eira-consent` med mode `2755`.

## 4. Komponenter og ansvar

| Komponent | Kører som | Ansvar |
|---|---|---|
| **`eira-consent-agent`** (ny, Rust, ikke GTK) | brugerens UID, effektiv GID `eira-consent` (setgid) | Holder samtykkenøglen. Henter selv den kanoniske gengivelse fra gaten, viser den, tager imod brugerens beslutning, laver beviset og kalder selv `gate.consent`/`gate.confirm`. |
| **`identityd`** | `eira` | Opretter nøglen ved login som i dag, men udleverer den **kun** til den registrerede agent for sessionen (§5.2), aldrig til appen. |
| **Gate (`intentd`)** | `eira` | Accepterer `gate.consent`/`gate.confirm` kun fra en peer med `gid = eira-consent` **og** gyldigt bevis. Ny læsemetode til agenten: `gate.rendering`. |
| **Tauri-appen** | brugerens UID | Gør login (OIDC, RFC 8252) som i dag, men får ingen nøgle. Beder agenten om at vise et samtykke. Har ingen anden vej til at samtykke. |
| **labwc (sessionens compositor)** | brugerens UID | Starter agenten fra den root-ejede autostart før appen. Er tillidsroden for skærm og input (§6). |

Agenten må aldrig tage indhold fra appen. Appen sender kun `action_id`. Alt, hvad brugeren ser og samtykker til, kommer fra gaten.

## 5. Flow

### 5.1 Grundtanken: den ægte agent på den ægte skærm er ufarlig, uanset hvem der startede den

Agenten er setgid, så dens kode og hukommelse kan ikke manipuleres (§3). Den henter selv det, den viser, fra gaten (§5.4). Det eneste, en angriber kan ændre, er **hvor** den viser det: med et falsk `WAYLAND_DISPLAY` kan agenten startes i en indlejret compositor, som angriberen styrer og selv kan klikke i. Derfor bindes tilliden til agentens compositor og ikke til, hvem der startede agenten. Starter angriberen selv den ægte agent på den ægte skærm, vinder han intet: brugeren ser gatens gengivelse og skal selv beslutte.

Labwc's autostart starter agenten før appen, så den normalt kører fra sessionsstart. Det er bekvemmelighed og ikke en sikkerhedsforudsætning.

### 5.2 Registrering af agenten

Agenten forbinder til sin compositor (`WAYLAND_DISPLAY` under `XDG_RUNTIME_DIR`) og læser compositorens pid med SO_PEERCRED på Wayland-socket'en. Derefter kalder den `identity.consent_agent_register(compositor_pid)` over `identityd.sock`. `identityd` accepterer kun, når **alle** disse er opfyldt; ellers `E_CONSENT_AGENT`:

1. peer `gid` = `eira-consent` (SO_PEERCRED). Det er ægte agentkode, så dens oplysning om `compositor_pid` kan stoles på;
2. peer `uid` = `loginuid` for peer-processen, og ≥ 1000;
3. compositoren er **sessionens** compositor: dens forælder (`/proc/<pid>/stat`, ppid) er logind-sessionens leader (`/run/systemd/sessions/<sessionid>`, `LEADER=`, hvor `sessionid` læses fra `/proc/<agent-pid>/sessionid`), og dens uid er brugerens. En indlejret compositor, som brugeren selv har startet, er barn af noget andet;
4. compositoren og agenten lever stadig. Starttiden fra `/proc/<pid>/stat` gemmes, så en genbrugt PID ikke tæller.

`identityd` gemmer `(logind-session, agent-pid, agent-starttid, compositor-pid, compositor-starttid)`. Flere agenter må registreres i samme session. Det gør ingen skade (§5.1), og det betyder, at det at dræbe agenten kun forsinker brugeren og ikke låser ham ude.

**Krav til agenten selv** (den er setgid, så argv, miljø, stdin og arvede fd'er er fjendtlige):

- R-5.1 Den læser kun `WAYLAND_DISPLAY` og `XDG_RUNTIME_DIR` fra miljøet og afviser `WAYLAND_DISPLAY`, der indeholder `/` eller peger uden for `XDG_RUNTIME_DIR`. `XDG_RUNTIME_DIR` skal være `/run/user/<ruid>`.
- R-5.2 Den bruger en font, der følger med pakken, og ignorerer `FONTCONFIG_*`, locale-variabler og temaer. Ellers kan en angriber få teksten til at se ud som noget andet.
- R-5.3 Den lukker alle arvede fd'er ud over 0–2 ved start, åbner alt med `O_CLOEXEC` og sender aldrig fd'er videre (SCM_RIGHTS), så en forbindelse med agentens GID ikke kan lånes ud.
- R-5.4 Den tager ingen argumenter ud over `--version`.
- R-5.5 Den er bygget på `smithay-client-toolkit` (kun Wayland, ingen X11), `softbuffer` og `fontdue` med en font, der følger med pakken. Den linker hverken mod GTK, fontconfig, D-Bus eller et webview. Pakketesten tjekker det med `ldd`/`readelf` på den byggede binære fil.

### 5.3 Login

Uændret OIDC-flow i appen (`identity.login_start` / `identity.login_complete`). Ændringen er, at `login_complete` **ikke** returnerer `consent_key`. Agenten henter den med `identity.consent_key_claim(session_id)`. `identityd` udleverer den kun til en registreret agent (§5.2) i samme logind-session og med samme uid som Eira-sessionen. Log ud glemmer nøglen i både agent og `identityd`.

**Nøglen skrives aldrig til disk** (11. november 2026, fra invariant A-1 i EIRA-CONTEXT). Den findes kun i hukommelsen hos `identityd` og agenten og er bundet til sessionens logind-session og boot-id. Efter genstart findes der ingen gyldig samtykkenøgle, og en kopi af disken indeholder ingen. I dag ligger `consent_key` i sessionsdatabasen (`app/session_store.py`) og overlever genstart; det skal rettes, uanset hvornår agenten bygges.

### 5.4 Samtykke og bekræftelse

```
App ──agent.show(action_id)──► Agent ──gate.rendering(action_id)──► Gate
                                 │◄── tekst, rendering_hash, content_hash
                                 │    (agenten genberegner rendering_hash over teksten)
                                 │  viser teksten i eget vindue, venter på brugerens beslutning
                                 └──gate.consent(action_id, …, proof)──► Gate
                                        Gate: peer.gid == eira-consent  ∧  proof gyldigt
App ◄── resultat (kun status, aldrig nøgle eller bevis)
```

- Agentens socket (`$XDG_RUNTIME_DIR/eira-consent.sock`) tager kun imod `agent.show(action_id)` og `agent.status`. Den tager aldrig imod tekst, hashes eller beviser fra appen.
- Agenten viser kun vinduer på den compositor, den blev registreret med i §5.2. Mister den forbindelsen, skal den registreres igen.
- `gate.confirm` følger samme vej.

### 5.5 Udviklingsmaskiner

Uden for et installeret system (`caller.installed()` er falsk) kan appens nuværende vej bevares bag samme betingelse som mock-login. På et installeret system findes den ikke.

## 6. Skærm og input: det, setgid ikke løser

Setgid beskytter nøglen. Det beskytter **ikke** det, brugeren ser og klikker på. Et program, der kører som brugeren, kan:

- **starte agenten selv** i en falsk, indlejret compositor, som det selv styrer. Det lukkes af §5.2: kun en agent på sessionens compositor kan registreres;
- **klikke for brugeren** gennem Wayland-protokollerne `zwlr_virtual_pointer_manager_v1` og `zwp_virtual_keyboard_manager_v1`, hvis compositoren udbyder dem;
- **lægge et vindue oven på agenten** (layer-shell `overlay`), der viser én tekst, mens klik går igennem til agentens knap (clickjacking).

De to sidste kan kun compositoren lukke. Det er **krav for udgivelse**:

- R-6.1 Ingen klient får `zwlr_virtual_pointer_manager_v1`, `zwp_virtual_keyboard_manager_v1`, `zwp_input_method_manager_v2`, `zwlr_layer_shell_v1`, `zwlr_screencopy_manager_v1`, `ext_image_copy_capture_manager_v1`, `zwlr_export_dmabuf_manager_v1`, data-control eller foreign-toplevel. Dermed kan en angriber hverken klikke for brugeren, lægge et overlay over agenten eller se agentens vindue.
- R-6.2 Mens agentens vindue vises, ligger intet andet vindue over det, og agenten har tastaturfokus.
- R-6.3 Agenten tager først imod en beslutning, når vinduet har været vist og haft fokus uafbrudt i mindst 750 ms. Det dæmper "flyt vinduet ind under et klik".

### 6.1 Sådan opfyldes R-6.1 og R-6.2 (besluttet i 0.2)

**EiraOS leverer sin egen compositor-pakke, `eira-labwc`**, i stedet for Ubuntus. Ubuntu 26.04 har labwc 0.9.3, som ikke kan begrænse protokollerne.

- **Version:** labwc ≥ 0.20.3 med den wlroots 0.20, den kræver. `<privilegedInterfaces>` findes fra 0.20.0, men logikken ("første `<privilegedInterfaces>` slår alle fra, `<allow>` tilføjer") blev først rigtig i 0.20.3. `eira-labwc` erstatter (`Conflicts`/`Replaces`) Ubuntus `labwc`, og `eira-session` kalder den med fuld sti.
- **R-6.1 med konfiguration alene:** Den leverede `rc.xml` indeholder en tom `<privilegedInterfaces/>`. Den skjuler alle privilegerede protokoller for alle klienter. Ingen EiraOS-klient har brug for dem: appen er et fullscreen-vindue (`tauri.conf.json`), og agenten er et almindeligt `xdg_toplevel`. `<shell>layer-shell</shell>` i dagens `rc.xml` er ikke en labwc-indstilling og fjernes.
- **R-6.2 med en lille patch:** labwc kender hver klients effektive GID gennem `wl_client_get_credentials` (SO_PEERCRED på klientens forbindelse). Patchen gør tre ting for klienter med `gid = eira-consent` og kun for dem: deres vinduer lægges i et eget scenetræ over alle andre lag, inklusive fullscreen og `overlay`; de får tastaturfokus, når de vises; og andre klienter kan ikke aktivere sig selv eller tage fokus, så længe et sådant vindue findes. GID'en angives i `rc.xml` (fx `<core><trustedGroup>eira-consent</trustedGroup></core>`), så patchen er generel og kan foreslås upstream. Indtil den er accepteret, vedligeholder EiraOS den selv. Patchen ligger i `packaging/eira-labwc/patches/` med en test pr. punkt.
- **Konsekvens for Builder Mode (P4):** Et panel kræver layer-shell. Det må kun gives tilbage gennem en mekanisme, der begrænser protokollen til en bestemt klient (også efter GID), aldrig ved at tilføje `<allow>zwlr_layer_shell_v1</allow>` globalt.

## 7. Fejlkoder

| Kode | Lag | Hvornår |
|---|---|---|
| `E_CONSENT_PATH` (ny) | 5 | `gate.consent`/`gate.confirm` fra en peer, hvis `gid` ikke er `eira-consent` (installeret system) |
| `E_CONSENT_PROOF` (uændret) | 5 | Peer er agenten, men beviset mangler eller er ugyldigt |
| `E_CONSENT_AGENT` (ny, `identityd`) | – | Registrering eller nøgleudlevering afvist (§5.2, §5.3) |
| `E_CONSENT_AGENT_UNAVAILABLE` (ny, til appen) | – | Ingen registreret agent i sessionen; appen viser, at samtykke ikke kan gives lige nu |

Hver kode har sin egen audit-post, så SIEM og Fleet kan alarmere på dem. `E_CONSENT_PATH` fra en brugerproces er et stærkt signal om forsøg på at gå uden om agenten.

## 8. Konsekvenser for eksisterende kode og dokumenter

- `ui/src-tauri/src/login.rs`: `consent_key` og `consent_proof` fjernes fra appen på installerede systemer. Testvektorerne (`tests/vectors/consent-proof.json`) flyttes til agenten.
- `app/auth/login.py`: `login_complete` returnerer ikke længere `consent_key`.
- `app/gate/kernel.py`: lag 5 tjekker peer-GID før beviset.
- `packaging/`: ny gruppe `eira-consent` (postinst, uden medlemmer), agenten installeres `root:eira-consent 2755`, labwc-autostart starter agenten før appen, og AppArmor-profil til agenten.
- `packaging/eira-labwc/`: ny kildepakke (labwc ≥ 0.20.3 + wlroots 0.20 + patchen fra §6.1). `eira-os-core` afhænger af den.
- `packaging/session/config/labwc/rc.xml`: tom `<privilegedInterfaces/>`, `<trustedGroup>eira-consent</trustedGroup>`, og `<shell>layer-shell</shell>` fjernes. En pakketest kræver, at blokken findes og er tom.
- **ADR-0003** får en præcis sætning i stedet for "lover ikke beskyttelse mod programmer, der kører som dig": *Et program, der kører som brugeren, kan ikke samtykke eller bekræfte. Det kan forsinke brugerens samtykke (ved at dræbe agenten), men ikke samtykke i hans sted.* Sætningen gælder først, når R-6.1–R-6.3 er opfyldt.
- `docs/AGENT_WORK_ASSIGNMENTS.md`: Agent 3-opgaven erstattes af en henvisning hertil.

## 9. Uden for scope

- **root, en bruger med `sudo` og en kompromitteret kerne.** I managed mode styres sudo af Fleet (ADR-0003 nuance 4).
- **En kompromitteret `identityd` eller `intentd`.** De er gaten.
- **En kompromitteret compositor.** Labwc kører som brugeren. Det beskyttes kun af, at den startes fra en root-ejet konfiguration og ikke kan ptraces af sine efterkommere (Yama ≥ 1). Beskyttelse ud over det kræver O-3.
- **Phishing**, hvor brugeren selv samtykker til noget, han ikke forstår. Det er gengivelsens opgave (bilag A pkt. 3).

## 10. Beslutninger og åbne spørgsmål

### Besluttet i 0.2

- **O-1 Toolkit:** den mindste flade, se R-5.5. Agenten viser én tekst og to knapper og har ikke brug for mere.
- **O-2 Compositor:** egen `eira-labwc` ≥ 0.20.3 med tom `<privilegedInterfaces/>` (R-6.1) og en lille, generel patch til en betroet gruppe (R-6.2), se §6.1.
- **O-3 Fysisk tilstedeværelse:** ikke i 1.0. Senere kan en FIDO2-udfordring tilføjes uden brud, fordi den kan laves over samme besked som beviset (`message(...)` i `consent_proof.py`, som allerede indeholder `rendering_hash`). Agenten er det naturlige sted at kalde nøglen.
- **O-4 `hidepid`:** EiraOS monterer ikke `/proc` med `hidepid`. Kan `identityd` ikke læse `stat`, `loginuid` eller `sessionid` for en peer, afvises registreringen (`E_CONSENT_AGENT`). Det fejler lukket, aldrig åbent.

### Stadig åbne

- **O-5 Flere sessioner pr. bruger** (fx fjernskrivebord). Kontrakten antager én logind-session med én compositor pr. Eira-session.
- **O-6 Compositorens forælder.** §5.2 pkt. 3 antager, at greetd's sessionsproces er logind-leaderen og selv starter `eira-session`, som `exec`'er labwc. Det skal verificeres i VM'en (`LEADER=` mod labwc's ppid), før testplanen skrives. Hvis der ligger et led imellem, skal reglen være "første labwc-efterkommer af leaderen", og det kræver en anden måde at se exe på end `/proc/<pid>/exe`.
- **O-7 Upstream.** Skal patchen fra §6.1 foreslås til labwc nu eller først efter en VM-verificeret version? Det ændrer ikke kontrakten, kun vedligeholdelsen.

## 11. Næste skridt

1. Ejeren accepterer, retter eller afviser denne kontrakt (v0.2). O-6 verificeres i VM.
2. Testplan som separat dokument: én test pr. krav i §3, §5.2 (inkl. R-5.1–R-5.4), §5.3, §6 og §7, med mutationstjek som i bilag A, plus VM-tests for setgid- og ptrace-garantierne.
3. Implementering i tre PR'er: (a) gruppe, forudsætningstjek og `E_CONSENT_PATH` i gaten, (b) `identityd`-registrering og nøgleudlevering, (c) `eira-labwc` med konfiguration og patch, (d) agenten og flytning af beviset ud af appen. (c) kan begynde straks, fordi R-6.1 er ren konfiguration og gør systemet bedre også uden agenten.
