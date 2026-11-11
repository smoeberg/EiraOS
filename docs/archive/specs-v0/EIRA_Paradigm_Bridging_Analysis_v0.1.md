# EIRA OS � Paradigmeskift og brobygning (2000 ? 2030) v0.1

**Status:** Produktanalyse � ekstern feedback integreret  
**Dato:** 26. juni 2026  
**Relateret:** [EIRA_User_Experience_Logic_v0.1.md](EIRA_User_Experience_Logic_v0.1.md), [EIRA_Ubuntu_Integration_v0.1.md](EIRA_Ubuntu_Integration_v0.1.md), [EIRA_Update_Release_Train_v0.1.md](EIRA_Update_Release_Train_v0.1.md)

---

## 1. Kerneobservation (bekr�ftet)

> Flytte PC-brug fra **filer og mapper** til **data, hensigter og kontekst** er pr�cis den retning enterprise-IT mangler.

EIRA's produktposition er ikke "nyt OS" � det er **opm�rksomhedscentrisk computing** oven p� Ubuntu:

| 2000-tals paradigme | EIRA 2030-paradigme |
|---------------------|---------------------|
| Applikationscentreret | Intent-drevet |
| Statiske filer i hierarki | Objekter med relationer (tynd graf) |
| Brugeren navigerer | Systemet prioriterer og foresl�r |
| Mange indbakker | �n handlingsflade |

**Vigtig nuance:** EIRA ejer ikke indholdet. Kildesystemer (Public360, SharePoint) forbliver sandheden. Object Graph er **lokal metadata-cache + relationer** � ikke erstatning for alle datastores.

---

## 2. Inspiration fra mobil � hvad vi tager, hvad vi tilpasser

### 2.1 Intent-driven interaktion ? Adopteret

Android's Intent-model er den rigtige analogi:

```
Mobil:  Bruger deler billede ? OS sp�rger hvilken app
EIRA:   Bruger markerer objekt / skriver intention ? Capability Layer foresl�r handlinger
```

Implementeret via: Intent Protocol, Capability Layer, adapter-manifest.

**UX-forskel:** EIRA er ikke "v�lg mellem 12 apps". Det er **�n foresl�et handling** med rationale (regel 4�5 i UX Logic).

### 2.2 On-the-fly permissions ?? Delvist � anderledes end mobil

Mobil: "Tillad adgang i 10 minutter?"

EIRA: **Assurance per handling** (Identity Spec) � step-up ved `org_acting`, delegation, policy � ikke tidsbaseret popup-bingo.

| Mobil | EIRA |
|-------|------|
| Runtime permission per app | Runtime assurance per **intention** |
| App-isoleret | Tv�rg�ende via Capability + audit |
| Ofte engangs | Logget i Intent Audit (compliance) |

**Gap:** Tidsbegr�nset "session grant" (fx "adgang til sag X i 30 min") er **ikke** spec'et � relevant for borgmester-delegation. ? Identity Spec v0.2.

### 2.3 App lifecycle / resume ? Ikke spec'et endnu

Mobil: fryser ikke apps � gemmer **tilstand** og genoptager p� tv�rs af enheder.

EIRA i dag: fokus + tilstand i kontekst, men **ingen normativ "arbejdsgang"-entitet** der pauseres og genoptages p� en anden maskine.

**Forslag (v0.2):**

```
Workflow = { focus, active_intents[], draft_confirmations[], ui_scroll_state }
  ? synk via encrypted sync (ikke fuld graf)
  ? "Forts�t hvor du slap" p� ny EIRA-PC efter login
```

**Prioritet:** P1 efter Explorer MVP � st�rkt differentierende for vidensarbejdere.

---

## 3. Inspiration fra moderne web � hvad vi tager, hvad vi tilpasser

### 3.1 Unified Search / Cmd+K ?? Delvist

Object Graph har `search(fts_query)` � men **ingen UX-spec** for universel s�gning i Explorer.

**Forslag:**

- `Ctrl+K` / `Eira+K`: s�g objekter, intentioner, fokus-skift  
- Resultater som **objekter + foresl�ede handlinger** � ikke filstier  
- Deep links: `eira://object/{uuid}?focus=Kommunepilot` � delbart internt (ikke fil-URL)

**Prioritet:** P0 for Explorer � supplement til handlingskort, ikke erstatning.

### 3.2 Real-time collaboration ? Bevidst scope-afgr�nsning i v1

Google Docs / Figma: live delt objekt.

EIRA v1: objekter er **referencer til kildesystemer**. Live samarbejde sker **i kildesystemet** (SharePoint co-authoring) � EIRA viser status og intentioner ovenp�.

**Fremtid:** `presence` p� objekter i grafen ("Lars redigerer budget") via adapter-events � ikke CRDT i EIRA.

**Kommunikation til IT:** EIRA collaberer ikke ved at duplikere content � den **orkestrerer** hvem der g�r hvad hvor.

---

## 4. Lifecycle � kommentarens blindt punkt

### Bekymring

> Hvis Governance Agent blokerer *alt*, opst�r sikkerhedshul.

### EIRA's svar (allerede normativt)

Se [EIRA_Update_Release_Train_v0.1.md](EIRA_Update_Release_Train_v0.1.md):

| Type | Hold? | Push? |
|------|-------|-------|
| **Security bundle** (CVE) | Nej � staged rollout | Ja � ugentlig |
| **Feature bundle** | Nej | Ja � m�nedlig efter IT |
| **Major LTS-skift** | **Ja** � `do-release-upgrade` blokeret | Kun via certificeret major bundle |

**Governance Agent blokerer ikke sikkerhedspatches.** Den blokerer **ukontrolleret apt** og **uautoriseret LTS-hop**.

**Salgsbudskab til IT:**

> "I opgraderer EIRA OS 2028.1 � ikke r� Ubuntu. Sikkerhedspatches kommer som bundles, testet mod EIRA-stack."

**Gap:** Kommunikation i kundevendt materiale � teknisk spec er klar, whitepaper b�r have �n tydelig s�tning.

---

## 5. De fire blinde punkter � status og l�sninger

### A. Legacy apps og "Gem som..." ? Kritisk gap � skal designes

**Problemet:** GIMP, LibreOffice, legacy ERP via X11 forventer POSIX + GTK/Qt fil-dialog ? `/home/user/Documents`.

**EIRA's nuv�rende position:** Explorer skjuler filer; Builder eksponerer r� Ubuntu. **Ingen bro for legacy i Explorer.**

**Foresl�et l�sning � tre lag:**

```
???????????????????????????????????????????????????????????
? Explorer (2030) � intentioner, ingen fil-dialog         ?
???????????????????????????????????????????????????????????
? Legacy Bridge (NY)                                      ?
?   � eira-fuse: Object Graph ? virtuel mappe-struktur    ?
?   � GTK3/4 + Qt file portal override (xdg-desktop-portal)?
?   � Gem ? objekt i graf + adapter upload (ikke raw path)?
???????????????????????????????????????????????????????????
? POSIX / ext4 (Ubuntu) � u�ndret under Builder           ?
???????????????????????????????????????????????????????????
```

| Scenario | Adf�rd |
|----------|--------|
| IT har whitelisted LibreOffice i Explorer | �bnes via Legacy Bridge; "Gem" mapper til objekt |
| Udvikler i Builder | Normal `/home` � ingen bro n�dvendig |
| Uautoriseret legacy app | Blokeret af Governance whitelist |

**Princip:** Legacy Bridge er **kompatibilitetslag** � ikke produktvisionen. M�let er at **f�rre legacy apps over tid**, ikke perfekt FUSE for alt.

**Prioritet:** P0 f�r kommune-pilot hvis LibreOffice/ERP kr�ves ved siden af Explorer.

**Dokument at skrive:** `EIRA_Legacy_Filesystem_Bridge_v0.1.md`

---

### B. Offline-first for Object Graph ?? Delvist d�kket � skal sk�rpes

**EIRA's model (ikke central server-graf):**

```
Kildesystemer (sandhed)  ??  Adaptere  ??  Lokal SQLite (tynd cache)
```

| Komponent | Offline |
|-----------|---------|
| Explorer UI | ? Lokal (Tauri) |
| Login | ? SSSD cache + passkey |
| Object graph read | ? Cached metadata |
| Intent (rule-based) | ? P� cachede entiteter |
| Intent (skriv/godkend) | ? Fail closed (Identity Spec) |
| Adapter-kald | ? K�et eller blokeret |

**Ikke:** CouchDB-sync af fuld central graf (enterprise data bor i Public360).

**Ja:** Relevant **subgraf** prefetches ved fokus-skift; sync n�r netv�rk returnerer.

**Gap:** Prefetch-strategi og k�-UX ("3 handlinger venter p� netv�rk") er ikke spec'et.

**Prioritet:** P0 � "Dead Desktop" er diskvalificerende for IT.

---

### C. Power users / alienation ? L�st via Builder Mode

Kommentaren: *"2030-gr�nsefladen skal kunne klippes fra."*

EIRA's svar (Platform Principles + UX Logic):

| Bruger | Mode | POSIX synlig? |
|--------|------|---------------|
| Mette (sagsbehandler) | Explorer | Nej |
| IT / udvikler | Builder | Ja � terminal, Docker, filer |

**Ikke et f�ngsel** � et **lag** med bevidst break-glass.

**Gap:** Rolle-baseret auto-switch (IT logger ind ? Builder tilg�ngelig) er policy, ikke UX-spec.

---

### D. Sandbox vs Intent Engine ? Arkitekturbeslutning taget

Se Ubuntu Integration �4:

```
1. AppArmor (Ubuntu MAC)     ? hard ceiling � vinder altid
2. EIRA Capability Layer       ? hvad m� fors�ges
3. EIRA Intent / Agent         ? hvad brugeren �nsker
```

Intent Engine **overskriver ikke** kernel-sandbox. Tv�rg�ende handlinger kr�ver:

- EIRA-platform daemons (`eira-*`) med **kuraterede AppArmor-profiler**  
- Adaptere i **Flatpak** med eksplicitte permissions  
- Capability = "m� denne adapter kalde Public360?" � ikke "bryd isolation"

**AI-agent p� tv�rs:** Agenten handler via **adapter-API'er** � ikke ved at l�se andre apps' filer direkte.

---

## 6. Syntese � hvad kommentaren f�r rigtigt

| Punkt | Vurdering |
|-------|-----------|
| 2000 ? 2030 framing | ? Kerne i EIRA � brug i salg og design |
| Mobil intent-model | ? Validerer Intent Engine-design |
| Web Cmd+K / deep links | ?? Mangler UX-spec |
| Live collaboration | ?? Bevidst deferred � kildesystem ejer content |
| Lifecycle security vs major | ? Allerede l�st i Release Train |
| Legacy fil-dialog | ? **St�rste tekniske gap** f�r bred pilot |
| Offline | ?? Princip klar � prefetch/k� mangler |
| Power users | ? Builder Mode |
| Sandbox | ? Lag-r�kkef�lge dokumenteret |

---

## 7. Anbefalet r�kkef�lge (produkt, ikke IT)

| # | Leverance | Hvorfor |
|---|----------|---------|
| 1 | Explorer handlingsflow (wireframe) | Brugeroplevelsen *er* produktet |
| 2 | Cmd+K / unified search UX | Bro mellem 2030 og "find noget nu" |
| 3 | Offline degradation + k�-UX | IT-krav + rejse |
| 4 | Legacy Filesystem Bridge (design) | Kun hvis pilot kr�ver LibreOffice/ERP ved siden af Explorer |
| 5 | Workflow resume (cross-device) | Differentiator efter MVP |

---

## 8. �n s�tning til skeptikere

> **EIRA viser 2030 ovenp� � og hacker 2000-tals POSIX i baggrunden, s� overgangen ikke kn�kker enterprise.**

Det er ikke hykleri � det er **brobygning**. Explorer er visionen; Legacy Bridge og Builder er broerne.

---

*EIRA OS � Paradigmeskift og brobygning v0.1*
