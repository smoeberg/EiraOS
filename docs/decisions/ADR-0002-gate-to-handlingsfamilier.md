# ADR-0002 — Gate 1.1: to handlingsfamilier, én sikkerhedsgrænse

**Status:** Besluttet af ejer (Søren Møberg), 7. november 2026
**Gælder for:** Gate Kernel, EiraSystemAPI, EDP, intentd, eira-shell (Tauri)
**Relateret:** [GATE-KERNEL-1.0](../../specs/GATE-KERNEL-1.0.md), [EDP-1.0](../../specs/EDP-1.0.md), [EiraSystemAPI](../architecture/eira-system-api.md), [ADR-0001](ADR-0001-haendelsesdrevet-explorer.md)

## Baggrund

Gate Kernel 1.0 tager kun EDP-handlinger. EDP er en *dialog*-protokol: dens handlingstyper beskriver kommunikation. Operationer på operativsystemet, som at slukke maskinen, skifte netværk eller printe, er ikke dialog. De skal alligevel ind under gaten, før den første executor, der ændrer maskinens tilstand, kan findes.

To muligheder blev overvejet:

- **(a)** Gate 1.1 med to handlingsfamilier gennem de samme otte lag.
- **(b)** Nye EDP-typer til systemhandlinger.

## Beslutning: (a)

> "Vi skal altså have to handlingsfamilier, men kun én autoritativ sikkerhedsgrænse." — ejer

| Familie | Repræsenterer | Kontrakt |
|---|---|---|
| **EDP** | Brugerrettede intentioner og handlinger i en samtale | `specs/EDP-1.0.md` |
| **EiraSystemAPI** | Kontrollerede, typede operationer på operativsystemet | `docs/architecture/eira-system-api.md` (operation-id + typet input) |

Begrundelsen er, at de to familier har forskellige formål, risikoprofiler og autorisationsbehov, og det skal arkitekturen afspejle. EDP's handlingstaksonomi forbliver ren kommunikation.

## Ufravigelige krav

1. **Ingen bypass.** EiraSystemAPI er aldrig en alternativ vej uden om gaten. Alle systemhandlinger går gennem samtlige otte lag. Et direkte kald til en systemoperation, der ændrer tilstand (fx via Tauri `eira_system`), skal fejle, og en test skal bevise det.
2. **Fælles sikkerhedsmodel.** Identitet, session, policy, risikovurdering (reversibilitet), brugerens samtykke, udførelse og audit håndteres af *den samme* `Gate`, med samme beslutningsmodel (PASS/REJECT/CLARIFY), samme fejlkoder, samme audit-kæde og samme recovery.
3. **Mindst mulige rettigheder.** EiraSystemAPI bruger eksplicitte, typede og afgrænsede operationer (en lukket liste af operation-id'er, hver med et skema og en policy-post i gatens registry). AI må foreslå en operation, men må aldrig selv bestemme eller tildele de rettigheder, den kræver. Rettigheder kommer kun fra policy og fra `identityd`.

## Konsekvenser for implementeringen

**Ingen ny parallel arkitektur og ingen nye komponenter.** Ændringerne sker inde i den eksisterende `app/gate/`:

- **Lag 1–3** vælger skema ud fra familien:
  - EDP-konvolut (`edp: "1.0"`) eller EiraSystemAPI-request (`eira_system: "1"`, `operation`, `input`).
  - Ukendt familie giver `REJECT (E_SYNTAX)`.
- **Lag 4** bruger det samme policy-registry, med nøgler pr. familie (`edp:utterance`, `system:power.request_action`) og reversibilitet pr. operation. En operation uden policy-post er ikke tilladt.
- **Lag 5–8** er uændrede: samtykke bundet til hash og gengivelse, autorisation fra `identityd`, atomar claim, én executor pr. operation med engangsbillet.
- **Executoren for systemoperationer** bliver `SystemExecutor` i gaten. Den kalder de eksisterende D-Bus-tjenester (logind, NetworkManager, CUPS). EiraOS erstatter dem ikke (Platform Principles).
- **Tauri `eira_system`** beholder kun læseoperationer. Operationer, der ændrer tilstand, findes kun bag `gate.confirm`.
- **CEL-constraints** fra den tidligere `intent.execute` foldes ind i lag 4's policy i stedet for at leve som en anden policy-motor.

**Versionering:** Valideringsrækkefølge og beslutningsmodel er uændrede, så dette er en minor-ændring (Gate 1.1, GATE-KERNEL §10).

**Rækkefølge** (GATE-KERNEL bilag A):
1. De gamle veje omdirigeres (gjort i samme PR som denne ADR).
2. Deterministisk renderer.
3. Gate 1.1 med EiraSystemAPI-familien og den første `SystemExecutor`.
4. Procesidentitet og `identityd`.
5. Audit-anker.
