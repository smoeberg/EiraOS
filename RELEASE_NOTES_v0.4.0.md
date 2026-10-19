# EiraOS v0.4.0 — release-notes (forslag)

**Status:** Udkast til releaseforberedelse — ikke udgivet.  
**Foreslået tag:** `v0.4.0`

EiraOS v0.4.0 samler Sprint 2–4's arbejde med daemon/IPC-infrastruktur, Veritas Shield og policy-styret intent-eksekvering.

- **Daemons og IPC:** Udvidet JSON-RPC-registrering, health-metoder, validering, socket-adgangskontrol samt systemd-deployment.
- **Veritas Shield:** Integrationstest af Unix-socket-IPC, evaluering og shutdown; dokumenteret fail-closed-håndtering af lagfejl.
- **Intent og CEL:** Begrænset CEL-kompatibel evaluator, versionsstyret policy-store og intentd-integration, så transformationer kontrolleres mod policy-constraints.
- **Intent-parser:** Regelbaseret parsing med valgfri lokal Mistral/Ollama-struktureret parser.

**Før tagning:** Afslut code review, bekræft at alle tre CI-jobs er grønne på den endelige main, og få releasegodkendelse fra Søren. Dette dokument er releaseforberedelse, ikke bekræftelse på at release er publiceret.
