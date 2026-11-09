# Situation-layout, november 2026 — designreference

**Status:** Reference, ikke spec. Normativ er [Situation UI Vision v0.1](../../specs/EIRA_Situation_UI_Vision_v0.1.md); hvor dette layout afviger, gælder visionen.
**Kilde:** Skærmbilleder fra ejeren, 9. november 2026. Mærket "Made with Emergent". **Ingen kode fra værktøjet må ind i repoet**, før licens og ejerskab til den genererede kode er afklaret; billederne bruges kun som retning.
**Formål:** (1) bevare retningen, (2) markere hvor den strider mod visionen, (3) udlede hvilke hændelser og datakilder skærmene kræver, så hændelsesstrømmen til Explorer bygges til dem.

| Fil | Skærm |
|---|---|
| [01-arbejde.jpg](01-arbejde.jpg) | Tilstand *Arbejde*: Deadlines, Afventer, Genveje, Seneste, Mine workspaces, I dag, intent-bar med forslag |
| [02-moede.jpg](02-moede.jpg) | Tilstand *Møde*: Dagsorden, Deltagere, Genveje |
| [03-aabne-applikationer.jpg](03-aabne-applikationer.jpg) | Åbne applikationer (objekt først, app som detalje) |
| [04-app-bibliotek.jpg](04-app-bibliotek.jpg) | App-bibliotek |

## 1. Det, der rammer rigtigt

- **Tilstandsfaner** (Arbejde, Møde, Fritid, Krise, Rejse, Læring) er §3.1 i pilotform: manuel `Tilstand`. Møde-skærmen viser, at indholdet skifter med situationen og ikke med appen.
- **Intent-baren** ("Fortæl mig hvad du vil lave…") er forløberen for Intent Canvas (§3.11).
- **"Budget 2027 · Word · Redigerer lige nu"** (03): objektet først, appen som detalje. Det er den rigtige retning for hele skallen.
- **Ro i udtrykket:** mørk flade, én accentfarve, få elementer pr. kort.

## 2. Hvor layoutet strider mod visionen

| # | Element | Strider mod | Retning |
|---|---|---|---|
| 1 | **App-bibliotek** (04) med Word, Outlook, Teams, Chrome, Slack, Notion, Figma … | Nordstjernen: *"Windows organiserer apps. EIRA organiserer opmærksomhed."* Og et katalog af netop de tjenester, EiraOS skal gøre organisationen uafhængig af. | Apps er måden et objekt åbnes på, ikke et sted man går hen. Et "bibliotek" findes højst i Builder Mode. |
| 2 | **"24 opgaver", "89 % automatiseret"**, tællere ved Mine workspaces | §3.8: statistik og inbox-sprog er forbudt | Tom tilstand: *"Alt er klaret."* |
| 3 | **"89 % automatiseret"** | Grundreglen: *AI'en foreslår. Gaten afgør. Systemet udfører.* | Vis ikke en automatiseringsgrad. Vis hvad der venter på brugerens beslutning. |
| 4 | **Seks kort på én gang** (01) | §3.1: højst 4 forslag; §3.8 | Én hero og højst fire klynger, valgt af prioritizeren. |
| 5 | **Forslag i intent-baren** ("Send budget til Lars") uden samtykkeskærm | GATE-KERNEL: hver handling bliver et forslag med gengivet sætning, som brugeren godkender (den betroede vej, `gate_consent`/`gate_confirm`) | Samtykkeskærmen er den vigtigste skærm og mangler i layoutet. |
| 6 | Ingen **"Hvorfor?"** og ingen **usikkerhed** | §3.3, §3.9 | Hvert hero-kort har en Hvorfor-fold; ved tvivl vises valg, ikke én knap. |
| 7 | **"Tilføj widget", "Tilføj genvej"** | §3.6: GUI-hukommelse er muskelhukommelse, ikke konfiguration | Genveje opstår af brug og bekræftes, ikke af en tilføj-knap. |

## 3. Hændelser og kilder skærmene kræver

Intet af nedenstående findes i dag som hændelse. Bygges skærmene nu, viser de opdigtede data. Listen er input til hændelsesstrømmen (bilag A) og til presenced/contextd.

| Skærmelement | Hændelse / kilde | Daemon | Findes |
|---|---|---|---|
| Deadlines, Dagsorden | `commitment.due`, kalenderbegivenheder på et objekt | contextd + connector (kalender) | nej |
| Afventer ("venter på dig") | `commitment_proposed` med brugeren som modtager, endnu ikke besvaret | presenced (EDP-samtaler) | delvist: EDP-typen findes i gaten |
| Deltagere (bekræftet/afventer) | deltagerstatus pr. samtale | presenced | nej |
| Online-status | tilstedeværelse | presenced | nej |
| Seneste | hændelser på brugerens objekter, nyeste først | graphd + hændelsesstrøm | nej |
| Mine workspaces | objekter brugeren er medlem af | graphd (`gate_members` er i dag kun gatens) | nej |
| Åbne applikationer | hvilke objekter er åbne i hvilke værktøjer | shell + app-adaptere | nej |
| Tilstand (fanerne) | manuel tilstand nu; senere kalender + mønster | contextd | manuel: ja (UI) |
| Forslag i intent-baren | intentd's forslag, højst fire, med Hvorfor | intentd + prioritizer | delvist |
| Godkend/udfør | `gate.propose` → samtykkeskærm → `gate_consent` → `gate_confirm` | intentd (gaten) + appen | ja, uden skærm |

## 4. Åbne spørgsmål til ejer

1. Skal app-biblioteket væk helt, eller leve i Builder Mode?
2. Licens og ejerskab til Emergent-genereret kode, hvis noget af den skal bruges.
3. Hvilken tilstand er pilotens første: *Arbejde* eller *Møde*? Den bestemmer, hvilke hændelser der bygges først.
