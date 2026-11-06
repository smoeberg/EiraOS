# ADR-0001 — Explorer er hændelsesdrevet; vinduer, filer og terminal hører til Builder

**Status:** Besluttet af ejer (Søren Møberg), 6. november 2026
**Gælder for:** eira-shell (Explorer og Builder), EiraSystemAPI, Gate Kernel, EDP, alle UI-PR'er

## Baggrund

Dokumenterne er uenige om, hvordan Explorer skal se ud:

- **Juli 2026:** [Desktop Architecture v1.0](../specs/EIRA_Desktop_Architecture_v1.0.md), [UX Logic](../specs/EIRA_User_Experience_Logic_v0.1.md), [Situation UI Vision](../specs/EIRA_Situation_UI_Vision_v0.1.md) og [Visual Language](../specs/EIRA_UX_Visual_Language_v0.1.md). Her har Explorer ingen filer, stier, programnavne, vinduer, panel eller terminal.
- **Oktober 2026:** [Architecture Baseline 1.0](../architecture/eiraos-architecture-baseline-1.0.md), [GUI-planen](../architecture/eiraos-gui-product-and-implementation-plan-1.0.md), [Design Principles](../architecture/eiraos-design-principles.md) og [Cross-device](../architecture/eira-cross-device-principles.md). Her beskrives vinduer, multitasking, filer og en launcher, "inspireret af iPadOS".

[Master Plan 1.0](../MASTER-PLAN-1.0.md) kræver, at sådanne konflikter afgøres eksplicit.

## Beslutning

> "Jeg vil gerne en moderne brugerflade, hvor vi kun drives af begivenheder." — ejer

1. **Explorer drives af hændelser.** Brugeren åbner ikke apps, mapper eller vinduer. Skærmen viser det, der er sket eller kræver handling: en henvendelse på en sag, et forslag til en aftale, en blokering, en ændret tilstand. Hver hændelse er knyttet til en person, en samtale eller et objekt. Kæden er Tilstand → Fokus → Aktører → Intention → Handling.
2. **Hændelser er semantiske, ikke kanaler.** En besked er en `utterance` på `obj:sag:…`, uanset om den kom som SMS, mail eller chat. Ruten er metadata i [EDP 1.0](../../specs/EDP-1.0.md) (`transport.actual`, `degraded`). Prioritering og sortering sker aldrig efter kanal.
3. **Handlinger er intentioner gennem Gaten.** Også Ubuntu-funktioner som at slukke, printe eller gå på netværk følger vejen: forslag → hvorfor → bekræftelse → [Gate Kernel 1.0](../../specs/GATE-KERNEL-1.0.md) → resultat. Ingen knap i Explorer kalder systemet direkte.
4. **Builder er den bevidste undtagelse.** Vinduer, filer, terminal, legacy-apps og Docker hører til Builder. Builder er policy-styret, og klienten kan ikke selv slå den til.
5. **Oktober-dokumenterne gælder for Builder og for kontrakterne.** Gate, EDP, AI Interface, EiraSystemAPI, adskillelsen af præsentation og logik samt ærlige tilstande gælder uændret overalt. Beskrivelserne af vinduer, filer og launcher gælder kun Builder.
6. **Det første gennemgående flow er "samtale om en sag".** En henvendelse fra en person lander på sagen som en hændelse. Eira foreslår et møde (`commitment_proposed`, vist som *foreslået*, indtil modtageren accepterer). Gaten afgør. Resultatet bliver auditeret og vist ærligt i Explorer.

## Konsekvenser, der er gennemført i denne PR

- `power.request_action` fejler lukket (`UNSUPPORTED`), og strømknappen er fjernet fra Explorer. Executoren bevares til Gate-vejen.
- Terminalen vises kun i Builder. `terminal_create` spørger intentd om sessionens tilstand og afviser uden for Builder.
- `presentation.mode_set` stoler ikke længere på klientens `policy_allowed`. Builder kræver policy (`EIRA_BUILDER_MODE_ALLOWED` indtil governance-agenten kompilerer policy). Hvis policy trækkes tilbage, falder sessionen tilbage til Explorer.

## Opfølgning i rækkefølge

1. **Gate Kernel 1.0** (master plan fase 1): otte lag, et reversibilitets-registry, bekræftelse bundet til `action.id` og et hash af indholdet samt regressionstests mod omgåelse.
2. **Samtale-laget:** EDP-validering og en hændelseslog med samtaler forankret på objekter (`presenced`/`contextd` erstatter de nuværende stubs). En adapter med ærlig leveringsstatus.
3. **Explorer-hændelsesstrømmen:** én hero og højst fire klynger, Hvorfor-fold, *foreslået* indtil accept og en tom tilstand.
4. **Installationen (PR #130):** Explorer-session uden GNOME som brugerflade og uden flugtvej, medmindre Builder er tilladt ([Contributor Prompt](../EIRA_Contributor_Prompt.md): ingen GNOME-afhængighed).
5. Ret [Prioritization Heuristics](../specs/EIRA_Prioritization_Heuristics_v0.1.md), så kanal-typen "mail" bliver til semantiske typer.
