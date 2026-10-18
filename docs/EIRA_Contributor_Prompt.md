# EiraOS — Bidragsyder-prompt (AGENTS / AI-udviklere)

Du er en bidragyder på EiraOS. Læs dette FØR du skaber en branch.

## 1. Kontekst (læs i denne rækkefølge)
1. `README.md` — projektets formål
2. `docs/specs/EIRA_Desktop_Architecture_v1.0.md` — primær GUI-spec
3. `docs/specs/EIRA_Ubuntu_Integration_v0.1.md` — Ubuntu-beslutninger
4. `docs/EIRA_GUI_Audit_Checklist.md` — aktuel sprint og gates
5. GitHub issue tildelt dig (fx #23 for Sprint 0)

## 2. Hårde regler (overtrædelse = afvist PR)
- `main` må ALDRIG pushes til direkte. Alt sker i en branch.
- Branch-navn: `audit/<emne>`, `feat/<sprint>-<emne>` eller `fix/<sprint>-<emne>`
- Ingen HTTP i produktion: UI taler KUN JSON-RPC over /run/eira/*.sock
- Ingen Electron, ingen custom compositor, ingen GNOME-afhængighed
- Ingen store omskrivninger: én leverance pr. PR, main forbliver brugbar
- Daemons holder logikken; UI er "dumt og smukt"
- Fejl til bruger: altid `user_message` (UX regel 5)
- Dansk dokumentation, engelsk kode-kommentarer

## 3. Workflow pr. opgave
1. Få tildelt issue af Søren Moeberg (owner) eller via /space/task
2. Opret branch fra main
3. Implementér + dokumentér (kode OG docs skal matche)
4. Kør tests + Ubuntu smoke-tests (sæt op hvis Sprint kræver det)
5. Åbn PR med "beviser": kommando-output, wayland-info/systemctl-status, screenshots
6. Gå videre til næste opgave — godkendelse sker async

## 4. Godkendelsesflow
- Søren Moeberg (owner) godkender alle merges til main
- Projektlederen (Eira machine) gennemgår teknisk compliance mod reglerne ovenfor
- En PR mergees først når BEGGE har godkendt
- Feedback gives som PR-comments; du retter på samme branch

## 5. Definition of Done
- [ ] Code review bestået (to godkendelser)
- [ ] Tests + integrationstest kører
- [ ] Dokumentation opdateret
- [ ] Intent Audit events logges hvor relevant
- [ ] Sprint-gate fra EIRA_GUI_Audit_Checklist.md opfyldt

## 6. Prompt-skabelon til ny opgave (bruges af Søren)

    Du arbejder på EiraOS (github.com/smoeberg/EiraOS).
    Opgave: <ISSUE-NR + titel>
    Sprint: <sprint-nr og gate fra docs/EIRA_GUI_Audit_Checklist.md>
    Scope: <konkret leverance, filer der må røres>
    Ikke i scope: <eksplicit liste>
    Acceptkriterier: <målbart gate-kriterium>
    Lever PR mod main med beviser. Følg docs/EIRA_GUI_Audit_Checklist.md regler.
