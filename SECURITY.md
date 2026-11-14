# Sikkerhedspolitik · Security policy

*English below.*

## Rapportér en sårbarhed

Brug **GitHubs private sårbarhedsrapportering**: fanen *Security* → *Report a vulnerability* ([direkte link](https://github.com/smoeberg/EiraOS/security/advisories/new)). Rapporten er kun synlig for vedligeholderne.

Opret **ikke** et offentligt issue eller en PR for en sårbarhed, der ikke er rettet.

Skriv gerne:
- hvilken komponent og version (`VERSION`, commit) det gælder
- hvordan det kan genskabes, helst på den installerede pakke
- hvad en angriber skal have i forvejen (en lokal bruger, samme UID, en daemon, netværksadgang)

## Hvad du kan forvente

| | Frist |
|---|---|
| Kvittering for modtagelse | 5 arbejdsdage |
| Første vurdering (bekræftet, afvist eller mere information) | 14 dage |
| Rettelse eller afhjælpning af et bekræftet fund | Efter alvor; vi aftaler en dato med dig |
| Offentliggørelse | Koordineret, senest 90 dage efter rapporten, tidligere når rettelsen er ude |

EiraOS vedligeholdes af én eller få personer. Fristerne er et løfte om svar, ikke om døgnvagt. Vi krediterer dig i rettelsens beskrivelse, hvis du ønsker det. Der er ingen dusør.

## Hvad der er omfattet

Omfattet er alt, der bygges ind i pakken (`eira-os-core`, `eira-labwc`) og installer-ISO'et:
- Gate Kernel (`app/gate/`), IPC-adgangsklasserne (`app/ipc/`) og daemonerne under `systemd/`
- samtykkeagenten (`crates/eira-consent-agent/`) og `eira-labwc`-patchen
- rettighedssæt og Fleet-synkronisering (`app/rights/`, `app/daemons/fleetd.py`)
- kontekstlageret (`app/context/`, `tools/eira-context-export`)
- AppArmor-profiler, polkit-regler, `postinst` og ISO'ets installationsscripts

Ikke omfattet:
- `docs/archive/` og prototyper, der ikke er i pakken (udviklingsbroen `app/http_bridge.py`, `veritas-shield/`)
- fund, der kræver root på maskinen (root er uden for trusselsmodellen, se [sikkerhedsmodellen](docs/security/SIKKERHEDSMODEL.md))

## Kendte, åbne fund

Fund fra de offentlige gennemgange står med dom og plan i [fundregistret](docs/reviews/GENNEMGANG-2026-11-12.md) og [vurderingen 13.–14. november](docs/reviews/GENNEMGANG-2026-11-13.md) og rettes i [udviklingsplanens](docs/UDVIKLINGSPLAN.md) trin F0c og F1c. Et fund, der allerede står dér, er kendt. En rapport, der viser, at det er værre end beskrevet, er velkommen.

## Understøttede versioner

EiraOS har endnu ingen udgivelse med sikkerhedsopdateringer. Rettelser laves på `main` og kommer med i næste version.

---

## Reporting a vulnerability (English)

Use **GitHub private vulnerability reporting**: *Security* tab → *Report a vulnerability* ([direct link](https://github.com/smoeberg/EiraOS/security/advisories/new)). Please do not open a public issue for an unfixed vulnerability.

We acknowledge within 5 working days, give a first assessment within 14 days, and coordinate disclosure no later than 90 days after the report. The scope is everything built into the package and the installer ISO (see above); `docs/archive/`, unpackaged prototypes and findings that require root are out of scope. Known findings are listed in `docs/reviews/`.
