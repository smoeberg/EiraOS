# ADR-0009 — Datalagets byggesten: biblioteker ja, NextGraph som platform nej

**Status:** Foreslået, til ejerens accept (13. november 2026). Retningen er ejerens; udformningen er et forslag.
**Gælder for:** kontekster (EIRA-CONTEXT, især synkronisering), udviklingsplanens F2.6, `graphd` og universets model (ADR-0004 D4)
**Relateret:** [ADR-0003](ADR-0003-rettigheder-fra-fleet.md), [ADR-0004](ADR-0004-gui-arkitektur-vendor-neutral.md), [ADR-0005](ADR-0005-kontekster-og-datas-hjem.md), [EIRA-CONTEXT](../../specs/EIRA-CONTEXT-1.0.md), [EIRA-CONTEXT-testplan](../../specs/EIRA-CONTEXT-1.0-TESTPLAN.md), [EIRA-FLEET-RIGHTS-API](../../specs/EIRA-FLEET-RIGHTS-API-1.0.md)

## Normativ regel

> **EiraOS bygger datalaget på åbne, udskiftelige biblioteker, ikke på en anden platform. Det lag, der afgør hvem der må hvad, hvem man er, og hvor data bor, skriver EiraOS selv.**

## Kontekst

Et eksternt råd (13. november 2026) foreslog at basere EiraOS' distribuerede data-, synkroniserings- og samarbejdslag på NextGraph (local-first, CRDT, RDF, E2EE-replikering). Ejerens spørgsmål var: hvad kan vi undgå at udvikle selv ved at bruge NextGraph?

Gennemgangen viste:

- **Det meste er allerede besluttet eller bygget.** EIRA-CONTEXT 1.0 og testplanen er accepteret. F2.1 (lagerformatet og `eira-context-export`) er leveret på N1. F2.6 (synkronisering med et åbent CRDT, tilbagekaldelse og rotation) er planlagt.
- **NextGraphs tungeste dele er andres biblioteker.** NextGraphs verifier integrerer Oxigraph (RDF/SPARQL), Yrs og Automerge (CRDT). De kan bruges direkte uden NextGraph.
- **Det NextGraph selv tilføjer**, er repo-format, synkroniseringsprotokol, broker, wallet og capability-model (`ng-repo`, `ng-net`, `ng-verifier`, `ng-wallet`, `ng-broker`). Netop dér har EiraOS de hårdeste krav: exit uden EiraOS, kontekst-hjem over S3/WebDAV uden broker (F2.2), rettigheder fra Fleet (ADR-0003), identitet fra `identityd` og eID-forankret genoprettelse (ADR-0005 K5).
- **Modenhed:** NextGraph er alpha, og dens dokumentation angiver (november 2026), at der ikke er gennemført nogen sikkerhedsrevision.
- **Licens:** Apache 2.0 / MIT. Lån af kode er tilladt med attribution.

## Beslutninger (forslag)

### N1 — Tre lag, tre svar

| Lag | Beslutning | Begrundelse |
|---|---|---|
| **CRDT-motor** (F2.6) | **Brug et åbent bibliotek direkte:** Automerge (foretrukket, allerede nævnt i F2.1 og F2.6) eller Yrs. Valget træffes i F2.6 mod invarianterne S-1 og R-1 | Det sværeste at få rigtigt; modent og udskifteligt |
| **Grafdatabase** (`graphd`, ADR-0004 D4) | **Hvis** graphd's model bliver RDF: Oxigraph direkte. Om modellen skal være RDF, er en selvstændig beslutning (N4) | Undgår en egen triple store og SPARQL |
| **Lagerformat og synkronisering** (F2.1, F2.6) | **Vores eget.** Lagerformatet er leveret (F2.1). Til synkroniseringen bruges NextGraphs sync-protokol og nøglerotation som forlæg; enkelte moduler må lånes med attribution, hvis de passer til EIRA-CONTEXT | Formatet bærer exit-garantien og skal virke over S3/WebDAV uden broker |
| **Identitet, wallet, rettigheder, brokere** | **Overtages ikke** | Ville skabe en rettighedsmodel og en identitet ved siden af Fleet, gaten og `identityd` |

### N2 — Ingen anden kilde til rettigheder

Intet bibliotek eller protokol i datalaget må afgøre adgang. Adgang til en kontekst og dens data følger af Fleets rettighedssæt og gaten. Kryptografiske nøgler i synkroniseringen er en *følge* af en rettighed, aldrig kilden til den: tilbagekaldes en rettighed i Fleet, roteres nøglerne (R-1), ikke omvendt.

### N3 — Data fra andre går samme vej

Ændringer, der kommer ind via synkronisering fra andre enheder eller personer, lander som hændelser via outbox og Event Store og valideres som alle andre. De skrives aldrig direkte i tilstanden uden om gaten.

### N4 — RDF er en særskilt beslutning

At gøre graphd's universets model til RDF er en beslutning om datamodellen, ikke om lagring. Den træffes i en egen ADR, før Oxigraph tages ind.

### N5 — Afhængigheder skal kunne skiftes ud

CRDT-motor og grafdatabase ligger bag en intern grænseflade i EiraOS. Det, `eira-context-export` skal kunne læse, er et dokumenteret, åbent format (EIRA-CONTEXT §6), ikke et biblioteks interne format.

## Konsekvenser

- **EIRA-CONTEXT:** ingen ændring af kontrakten.
- **F2.6:** CRDT-motoren er Automerge eller Yrs bag en grænseflade. Før implementeringen gennemgås NextGraphs nøglerotation ved fjernelse af medlemmer og deres sync-protokol som forlæg for R-1; resultatet skrives som et notat til F2.6.
- **Afhængighedspolitik:** Automerge/Yrs og (betinget af N4) Oxigraph optages som godkendte afhængigheder med fastlåst version og licens.
- **Ingen NextGraph-afhængighed** i pakken. Genovervejes kun efter O-1.

## Åbne spørgsmål

- **O-1 Genovervejelse.** NextGraph kan overvejes igen som afhængighed, hvis der foreligger en uafhængig sikkerhedsrevision, formatet er stabilt (ikke alpha), og identitet, rettigheder og brokere kan fravælges helt.
- **O-2 Automerge eller Yrs.** Afgøres i F2.6 ud fra testplanens invarianter, ressourceforbrug og integration.
- **O-3 RDF for graphd.** Egen ADR (N4).

## Ikke-mål

- NextGraph som systemkerne eller datafundament.
- En rettighedsmodel, identitet eller wallet i datalaget ved siden af Fleet, gaten og `identityd`.
- Afhængighed af offentlig brokerinfrastruktur.
