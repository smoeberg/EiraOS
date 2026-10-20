# EiraOS v0.4.0 — release-notes (forslag)

**Status:** Udkast til releaseforberedelse — ikke udgivet.  
**Foreslået tag:** `v0.4.0`

**Auditstatus:** Se [Sprint 4 cross-audit](audit/Sprint4_Cross_Audit.md) og [GUI-readiness audit](EIRA_GUI_Audit_v1.0.md). Disse er statiske reviews; de dokumenterer ikke i sig selv en publiceret release eller en gennemført Ubuntu 24.04 boot-/installationsaccepttest.

EiraOS v0.4.0 samler Sprint 2–4's arbejde med daemon/IPC-infrastruktur, Veritas Shield og policy-styret intent-eksekvering.

- **Daemons og IPC:** Udvidet JSON-RPC-registrering, health-metoder, validering, socket-adgangskontrol samt systemd-deployment.
- **Veritas Shield:** Integrationstest af Unix-socket-IPC, evaluering og shutdown; dokumenteret fail-closed-håndtering af lagfejl.
- **Intent og CEL:** Begrænset CEL-kompatibel evaluator, versionsstyret policy-store og intentd-integration, så transformationer kontrolleres mod policy-constraints.
- **Intent-parser:** Regelbaseret parsing med valgfri lokal Mistral/Ollama-struktureret parser.

**Før tagning:** Afslut code review, bekræft at alle tre CI-jobs er grønne på den endelige main, og få releasegodkendelse fra Søren. Dette dokument er releaseforberedelse, ikke bekræftelse på at release er publiceret.
