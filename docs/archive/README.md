# Arkiv

Dokumenter, der beskriver tidligere faser af EiraOS. De er bevaret for sporbarhedens skyld og er **ikke normative**. Hvor et arkiveret dokument og en gældende kontrakt eller ADR siger noget forskelligt, gælder kontrakten eller ADR'en.

**Gældende:** kontrakter i [`specs/`](../../specs/README.md), beslutninger i [`docs/decisions/`](../decisions/) og arkitektur i [`docs/architecture/`](../architecture/).

| Mappe | Indhold |
|---|---|
| [`sprints/`](sprints/) | Sprint 2–10: eksekveringsprompts, opsummeringer, Sprint 8-audits og cutover-tjekliste, sprintplan, implementeringstracker, GUI-audit, dokumentkort og v2.0-lineage |
| [`specs-v0/`](specs-v0/) | Den tidligere `docs/specs/`: arkitektur-, strategi-, pilot- og paritetsdokumenter fra før gaten, ADR-0003–0006 og kontrakterne i `specs/` |
| [`audit/`](audit/) | Statiske audits fra oktober 2026 (komponentkort A–F, sprint 4–7-krydsaudits, filhåndtering). Øjebliksbilleder; flere af fundene er rettet siden |
| [`contracts/`](contracts/) | Kontrakt-prompts, onboarding og Redmine-værktøj til den tidligere `prototype/phase1`-runtime, samt et forældet `eira-core` 0.2.0, der ikke er en del af workspacet (det gældende er `crates/eira-core`) |
| [`RELEASE_NOTES_v0.4.0.md`](RELEASE_NOTES_v0.4.0.md) | Udkast til release-noter for v0.4.0; aldrig udgivet. Gældende historik står i [`CHANGELOG.md`](../../CHANGELOG.md) |

Arkiveret 11. november 2026 (`audit/`, `contracts/` og release-noterne 12. november 2026). Filerne er flyttet uændret, så links mellem arkiverede dokumenter og til søsterrepoer (`eira-fleet-control`, `company`) kan være brudt.

To dokumenter fra `docs/specs/` var stadig normative og er flyttet til `specs/` i stedet:

- `EIRA_Delegation_Protocol_v1.0.md` → [`specs/EIRA-DELEGATION-PROTOCOL-1.1.md`](../../specs/EIRA-DELEGATION-PROTOCOL-1.1.md) (indholdet er v1.1)
- `PHASE-0-IPC-EVENT-BUS.md` → [`specs/PHASE-0-IPC-EVENT-BUS.md`](../../specs/PHASE-0-IPC-EVENT-BUS.md) (normativ for `crates/eira-core`)
