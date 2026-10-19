# Changelog

Alle væsentlige ændringer i EiraOS dokumenteres her. Datoer angiver leveringsperioden, ikke nødvendigvis en publiceret release.

## [0.4.0] — foreslået release, ikke tagget endnu

### Sprint 4 — Intent og CEL
- Indførte en begrænset CEL-kompatibel policy-evaluator med eksplicit understøttede AST-noder, kompleksitetsgrænser og fail-closed resultat ved evalueringsfejl.
- Tilføjede versionsstyret SQLite-lagring af policy-regler med historik, aktivering/deaktivering og standardpolitikker for betalinger, bevillinger, byggetilladelser, sagsfrister og habilitet.
- Koblede `intentd` til policy-store og transformation engine, så forslag evalueres mod gældende constraints før state anvendes.
- Udvidede intent-parseren med regelbaserede forslag, valgfri lokal Mistral/Ollama-parser, validering af strukturerede resultater og indlejring af kontekst i forslag.

### Sprint 3 — Veritas Shield
- Tilføjede Veritas-daemonens IPC-integrationstest og dækning af evaluering, health, socket-rettigheder og shutdown-livscyklus.
- Dokumenterede fail-closed-adfærd ved fejl i individuelle Veritas-lag samt at dæmonen forbliver tilgængelig efter en fejlet evaluering.

### Sprint 2 — Daemons og IPC
- Udvidede JSON-RPC-daemonregistrering og health-endpoints på tværs af kernekomponenter.
- Strammede JSON-RPC-kontraktvalidering, fejlens `user_message`-felt og peer-credential-/Unix-socket-adgangskontrol.
- Tilføjede systemd-units og deployment-script til at starte daemonerne under dedikeret `eira`-bruger/-gruppe.

### Release-forbehold
- Denne changelog opsummerer kode og tests, der er til stede i repositoryets Sprint 2–4-linje; den er ikke i sig selv dokumentation for en publiceret binær release.
- Foreslået Git-tag: `v0.4.0`. Opret først tag efter review, grøn CI og ejerens releasebeslutning.

## Tidligere versioner

Tidligere historik er endnu ikke samlet i denne fil.
