# Bidrag til EiraOS

Gælder mennesker og AI-assistenter. Afløser den arkiverede [bidragyder-prompt](docs/archive/sprints/EIRA_Contributor_Prompt.md), som peger på filer, der ikke længere gælder.

> **AI'en foreslår. Gaten afgør. Systemet udfører.**

## 1. Læs først

1. [`README.md`](README.md): hvad EiraOS er, og hvad der virker i dag.
2. [`docs/UDVIKLINGSPLAN.md`](docs/UDVIKLINGSPLAN.md): rækkefølgen, og hvad hvert trin skal leve op til. Dens status står øverst i filen. Er den et forslag, er den endnu ikke ejerens beslutning.
3. [`docs/MASTER-PLAN-1.0.md`](docs/MASTER-PLAN-1.0.md): principperne, statusordene og definition of done.
4. [`specs/README.md`](specs/README.md): kontrakterne (Gate Kernel, EDP, samtykkeagent, rettigheder, identitet, samtale, AI-interface).
5. [`docs/decisions/`](docs/decisions/): ADR'erne. En ADR, ejeren har accepteret, ændres kun af ejeren.
6. [`docs/reviews/GENNEMGANG-2026-11-12.md`](docs/reviews/GENNEMGANG-2026-11-12.md): kendte fejl og svagheder (fundregistret).

## 2. Hårde regler

- **Ejeren merger.** Ingen merger egne eller andres PR'er uden ejerens udtrykkelige accept.
- **Alt, der ændrer noget, går gennem gaten.** Ingen knap, daemon eller model kalder systemet direkte (ADR-0001, ADR-0002). Læsning må gå udenom; skrivning må ikke.
- **Rettigheder kommer kun fra Fleet** gennem rettigheds-API'et (ADR-0003). Fleet-kode hører ikke hjemme i dette repository.
- **Kun samtykkeagenten kan samtykke og bekræfte** (EIRA-CONSENT-AGENT). Eira UI viser aldrig gatens gengivelse som en flade at godkende på. Appen sender kun `action_id` til agenten.
- **Modellen foreslår, aldrig mere.** Den kører som `eira-model` uden net og må kun foreslå under en delegation fra mennesket (EIRA Delegation v1.1).
- **Identitet kommer fra kernen**, ikke fra en parameter: kalderen er den proces, der står på socketen (`SO_PEERCRED`). En klient kan ikke navngive en anden brugers session eller tilstand.
- **Ingen test fjernes for at få CI grøn.** En test, der er forkert, rettes, og begrundelsen står i PR'en.

## 3. En ny beskyttet handling fra ende til anden

Eksemplet er strøm (`system:power.request_action`, leveret i F1b), en EiraSystemAPI-handling. EDP-handlinger i en samtale følger samme vej med `app/gate/edp.py` i stedet for `system.py`.

| Trin | Hvor | Hvad |
|---|---|---|
| 1. Skema | `app/gate/system.py`, `OPERATIONS` | Lukket JSON-skema uden ekstra felter. En ukendt operation giver `E_SCHEMA`. |
| 2. Policy | `app/gate/policy.py`, `ActionPolicy` | Reversibilitet, hvem der må foreslå (`user`/`model`), krævet sikkerhedsniveau og grænser. Irreversibelt betyder samtykke hver gang. |
| 3. Gengivelse | `app/gate/system.py`, `SENTENCES`, via `app/gate/render.py` | Den præcise sætning, personen ser i samtykkeagenten, på dansk og engelsk, med advarsler. Samtykket binder til denne tekst (hash). |
| 4. Executor | `app/gate/executors.py`, registreret i `default_registry` | Udfører først efter bekræftelse, fejler lukket, og rapporterer en synlig tilstand (`requested`, `executed`, `failed`). |
| 5. Rettighed | Fleet-rettighedssættet | Handlingen skal være givet for domænet (fx `device:local`). Uden rettighed afviser lag 6 med `E_UNAUTHORIZED`. |
| 6. AppArmor og systemd | `packaging/apparmor/`, `systemd/` | Executoren kører i `intentd`. Den skal have præcis de stier og D-Bus-kald, den bruger, og ikke flere. |
| 7. Model (valgfrit) | `app/model/rules.py`, `app/model/daemon.py` | Kun hvis modellen må foreslå den: genkend hele sætninger, afstå ellers. Modellen kalder aldrig systemet. |
| 8. UI | `ui/src/lib/intent.ts` | Forslag, beslutning i agenten og gatens egen status bagefter. Én sand besked pr. udfald (MASTER-PLAN princip 13). |
| 9. Test | `tests/` | Hvert lag har sin test. Der skal også være en test af hele kæden i processen, som `tests/test_intent_to_gate.py`, og en test af, at modellen ikke kan samtykke. |
| 10. VM-check | `packaging/installer/ci/eira-ci-report` | Det, der kan bevises på den installerede pakke, som desktop-brugeren (`runuser -u "$USER_NAME"`). |
| 11. Audit | automatisk | Gaten skriver hver beslutning i sin egen audit-kæde. En executor skriver ikke sin egen audit. |

Nye IPC-metoder skal have en adgangsklasse (`app/ipc/access.py`), ellers kan de ikke registreres. Kataloget genereres derefter: `python3 scripts/ipc_catalog.py --write`. CI fejler, hvis det afviger fra koden.

## 4. Før en PR

```bash
python3 -m pytest -q tests          # 900+ tests
ruff check .
python3 scripts/ipc_catalog.py --check
(cd ui && npx tsc --noEmit -p . && npx vitest run)
(cd ui/src-tauri && cargo test)     # hvis Tauri-koden er ændret
cargo test -p eira-consent-agent    # hvis agenten er ændret
```

CI kører også *Ubuntu 26.04 Packaging Acceptance*, når pakning, UI, systemd eller scripts ændres. Det job bygger pakken og ISO'en, installerer den i en VM og kører `eira-ci-report` (omkring en halv time).

## 5. PR'en

- **Én PR pr. trin i planen**, med trinnets nummer i titlen (fx "F1.5: …").
- **Beskrivelsen** siger: hvad der var galt, hvad der er ændret, hvordan det er afprøvet (også hvad der *ikke* er afprøvet), og hvad der ikke er med.
- **Afviger PR'en fra planen**, står det i beskrivelsen, og planen rettes i samme PR.
- **Dokumentation** opdateres i samme PR: planen, fundregistret, kontraktens statustabel og `CHANGELOG.md`.
- **Dokumentation skrives på dansk**, kode og kodekommentarer på engelsk.
