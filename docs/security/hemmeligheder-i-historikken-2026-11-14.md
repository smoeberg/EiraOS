# Hemmeligheder i git-historikken — scanning 14. november 2026

**Hvorfor:** Repoet blev offentligt 14. november 2026. Hele historikken (alle grene, 811 commits) er scannet med gitleaks 8.28.0 og en målrettet søgning efter nøglefiler, databaser og kendte tokenformater. Scanningen kører nu i CI ved hver PR (`secret-scan`, [`.gitleaks.toml`](../../.gitleaks.toml)).

## Resultat

**Ingen adgangskoder, API-nøgler eller tokens til eksterne tjenester.** Gitleaks' fire fund er falske positiver og står med begrundelse i `.gitleaks.toml`: testcontainerens `eira:eira`, journalctl-flaget `--setup-keys`, Canonicals offentlige fingeraftryk og et domænenavn i en arkiveret spec.

Tre filer, der ikke burde have været committet, ligger i historikken:

| Fil | Commits | Indhold | Vurdering |
|---|---|---|---|
| `data/fleet_master.key` | tilføjet i `3b55e13`, fjernet i `9cfc635` (19. oktober) | 32 tilfældige bytes: den nøgle, `fleetd` krypterer synkroniserede tilstandsblokke med, genereret på en udviklingsmaskine | **Brændt.** En installeret maskine danner sin egen nøgle i `/data/eira-fleet`, så pakken er ikke ramt. Men nøglen må aldrig bruges igen, og en maskine, der har synkroniseret med den udviklingsopsætning, skal betragtes som afsløret |
| `data/eira.db` | `c1fd780` til `e2b3a93` (juli–august) | Testsessioner med opdigtede adresser (`mette@kommune.dk`, `a@test.dk`), mock-login-audit og to udløbne OIDC-state/verifier-par fra 7. juli | Ingen rigtige personer og intet, der kan bruges; ryddet op i `e2b3a93` |
| `eira_state.db` | `3b55e13` til `9cfc635` | Én test-audit-post (`system_test`) | Uden betydning |

**Afsenderadresser.** Commits bærer forfatternes e-mailadresser, også en arbejdsadresse og en privat adresse. De er nu offentlige og kan kun fjernes ved at omskrive historikken, hvilket ikke anbefales for et offentligt repo med åbne PR'er. Nye commits kan bruge GitHubs `noreply`-adresse.

## Hvis en rigtig hemmelighed lækker

1. Tilbagekald eller rotér den først; at slette den fra historikken er ikke nok, når repoet er offentligt.
2. Fjern den fra koden i en PR, og skriv rotationen ned her.
3. Overvej `git filter-repo` kun for personoplysninger, og kun efter ejerens beslutning.
