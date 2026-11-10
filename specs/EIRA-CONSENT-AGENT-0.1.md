# EIRA Consent Agent 0.1 — betroet vej til samtykke mod programmer, der kører som brugeren

**Status:** Udkast til ejerens accept. **Ikke normativ**, før ejeren har accepteret det. Testplanen er et separat trin efter accept.
**Version:** 0.1 (10. november 2026)
**Lukker:** "Rest" under GATE-KERNEL bilag A pkt. 1, *Betroet vej til samtykke*
**Erstatter:** Agent 3-opgaven "LD_PRELOAD Consent Path" i `docs/AGENT_WORK_ASSIGNMENTS.md` (se §2)
**Berører:** `identityd`, Gate (`intentd`, lag 5), Tauri-appen (`ui/src-tauri`), sessionen (`eira-session`, labwc-konfiguration), pakken (`eira-os-core`), ADR-0003

---

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

### 5.3 Login

Uændret OIDC-flow i appen (`identity.login_start` / `identity.login_complete`). Ændringen er, at `login_complete` **ikke** returnerer `consent_key`. Agenten henter den med `identity.consent_key_claim(session_id)`. `identityd` udleverer den kun til en registreret agent (§5.2) i samme logind-session og med samme uid som Eira-sessionen. Log ud glemmer nøglen i både agent og `identityd`.

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

De to sidste kan kun compositoren lukke. Det er et **krav for udgivelse**, ikke en anbefaling, og det åbne spørgsmål O-2 afgør hvordan:

- R-6.1 Den leverede compositor udbyder ikke virtual pointer, virtual keyboard eller input-method til almindelige klienter.
- R-6.2 Mens agentens vindue vises, ligger intet andet vindue over det, og agenten har tastaturfokus.
- R-6.3 Agenten tager først imod en beslutning, når vinduet har været vist og haft fokus uafbrudt i mindst 750 ms. Det dæmper "flyt vinduet ind under et klik".

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
- **ADR-0003** får en præcis sætning i stedet for "lover ikke beskyttelse mod programmer, der kører som dig": *Et program, der kører som brugeren, kan ikke samtykke eller bekræfte. Det kan forsinke brugerens samtykke (ved at dræbe agenten), men ikke samtykke i hans sted.* Sætningen gælder først, når R-6.1–R-6.3 er opfyldt.
- `docs/AGENT_WORK_ASSIGNMENTS.md`: Agent 3-opgaven erstattes af en henvisning hertil.

## 9. Uden for scope

- **root, en bruger med `sudo` og en kompromitteret kerne.** I managed mode styres sudo af Fleet (ADR-0003 nuance 4).
- **En kompromitteret `identityd` eller `intentd`.** De er gaten.
- **En kompromitteret compositor.** Labwc kører som brugeren. Det beskyttes kun af, at den startes fra en root-ejet konfiguration og ikke kan ptraces af sine efterkommere (Yama ≥ 1). Beskyttelse ud over det kræver O-3.
- **Phishing**, hvor brugeren selv samtykker til noget, han ikke forstår. Det er gengivelsens opgave (bilag A pkt. 3).

## 10. Åbne spørgsmål til ejeren

- **O-1 UI-toolkit til agenten.** Den må ikke bruge GTK. Kandidater er `winit` + `softbuffer` med egen tekstgengivelse (mindst flade, mest arbejde) og `slint` eller `iced` uden GTK-backend (hurtigere, større afhængighedstræ i en setgid-binær). *Min anbefaling:* den mindste flade. Agenten viser én tekst og to knapper.
- **O-2 Compositor-garantier (R-6.1, R-6.2).** Det skal undersøges, om labwc kan slå virtual-input-protokollerne fra og forbeholde `overlay` for én klient via konfiguration. Hvis ikke, er valget mellem en lille, vedligeholdt patch til labwc og en anden compositor (`cage` til single-app-tilstand har samme spørgsmål). Det skal afgøres, før agenten bygges, fordi det afgør, om løftet i ADR-0003 kan gives.
- **O-3 Fysisk tilstedeværelse til handlinger med høj værdi.** Det eneste, der også holder mod en kompromitteret compositor, er en faktor uden for sessionen, fx FIDO2-berøring med `rendering_hash` i udfordringen. Spørgsmålet er, om det skal være krav for betaling og step-up (lag 6), eller om det skal ligge uden for 1.0.
- **O-4 `hidepid`.** Hvis `/proc` monteres med `hidepid=2`, kan `identityd` ikke læse `stat` og `loginuid` for brugerprocesser. Derfor: dokumentér, at EiraOS ikke bruger `hidepid`, eller giv `identityd` gruppen fra `gid=`-mount-option.
- **O-5 Flere sessioner pr. bruger** (fx fjernskrivebord). Kontrakten antager én logind-session med én compositor pr. Eira-session.
- **O-6 Compositorens forælder.** §5.2 pkt. 3 antager, at greetd's sessionsproces er logind-leaderen og selv starter `eira-session`, som `exec`'er labwc. Det skal verificeres i VM'en (`LEADER=` mod labwc's ppid). Hvis der ligger et led imellem, skal reglen være "første labwc-efterkommer af leaderen, der kører `/usr/bin/labwc`", og det kræver en anden måde at se exe på end `/proc/<pid>/exe`.

## 11. Næste skridt

1. Ejeren accepterer, retter eller afviser denne kontrakt og tager stilling til O-1 og O-2.
2. Testplan som separat dokument: én test pr. krav i §3, §5.2 (inkl. R-5.1–R-5.4), §5.3, §6 og §7, med mutationstjek som i bilag A, plus VM-tests for setgid- og ptrace-garantierne.
3. Implementering i tre PR'er: (a) gruppe, forudsætningstjek og `E_CONSENT_PATH` i gaten, (b) `identityd`-registrering og nøgleudlevering, (c) agenten og flytning af beviset ud af appen.
