# EIRA Change Management — Pilot v0.1

**Status:** Normativ — champion, HR/IT, kommunikation  
**Dato:** 4. juli 2026  
**Formål:** Organisatorisk accept, træning og feedback for Fase 0–1 (~50 PC)  
**Relateret:**
- [EIRA_Enterprise_Endpoint_Transition_v1.0.md](../../../company/EIRA_Enterprise_Endpoint_Transition_v1.0.md)
- [EIRA_User_Experience_Logic_v0.1.md](EIRA_User_Experience_Logic_v0.1.md)
- [EIRA_Pilot_Validation_Plan_v0.1.md](EIRA_Pilot_Validation_Plan_v0.1.md) (V-ADOPT)
- [EIRA_BCP_Endpoint_Fallback_v0.1.md](EIRA_BCP_Endpoint_Fallback_v0.1.md)
- [EIRA_Strategic_Reality_Check_v0.1.md](EIRA_Strategic_Reality_Check_v0.1.md) §6 punkt 5

---

## 1. Kernebeslutning

> **Brugere adopterer ikke "Linux" eller "paritet" — de adopterer en arbejdsdag med færre systemskift og tydeligere handlinger.**

Teknisk gate uden change management = pilot der dør på uge 3. Dette dokument operationaliserer punkt 4 fra enterprise-analysen.

---

## 2. Målgrupper og budskaber

| Gruppe | Primær frygt | Budskab (30 sek) |
|--------|--------------|------------------|
| **Vidensarbejder** | "Hvor er mine filer?" / "Kan jeg ikke bare…" | *"Du beskriver hvad du vil opnå — EIRA finder vejen. Samme login som i dag."* |
| **Leder** | Produktivitetst tab | *"Én afdeling, 90 dage, rollback hvis det ikke virker."* |
| **IT L1** | Ticket-storm | *"10 FAQ — eskalér kun det der ikke står her."* |
| **Champion** | Politisk risiko | *"Du har mandat til at stoppe — ikke til at presse."* |
| **Indkøb** | Lock-in | *"Hybrid og fallback er i kontrakten."* |

**Sig aldrig:** "EIRA erstatter Windows."  
**Sig:** "Ny arbejdsflade for opgaver der passer — med plan B."

---

## 3. Roller

| Rolle | Ansvar | Tid (pilot) |
|-------|--------|-------------|
| **Champion** | Mandat, kommunikation, eskalering til IT-chef | 2–4t/uge |
| **Pilot-leder (EIRA)** | Onboarding, feedback-syntese, L1 triage | Efter aftale |
| **IT L1** | FAQ, OU/fallback ifm. BCP | Eksisterende |
| **Superbruger (2–3)** | Tidlige testere, peer-support | 1t/uge |
| **HR / kommunikation** | Intranet-tekst, mødebooking | 1 gang |

---

## 4. Tidsplan (Fase 1, ~50 PC)

| Uge | Aktivitet | Output |
|-----|-----------|--------|
| **−2** | Champion-briefing (60 min) | Champion accepterer mandat skriftligt |
| **−1** | Intranet + kort video (3 min) | "Hvad er anderledes" |
| **0** | Onboarding dag 1 (2t) | Alle pilot-brugere har set demo + øvet login |
| **0–1** | Walk-the-floor | Champion + superbruger på kontoret |
| **2** | Pulse survey (5 spørgsmål) | Baseline |
| **4** | Office hours (45 min) | Åbent spørgsmål |
| **8** | Survey + champion 1:1 IT-chef | Fortsæt / juster / BCP |
| **12** | Go/no-go input | Validation Plan V-ADOPT |

---

## 5. Onboarding (2 timer — dag 1)

### 5.1 Agenda

| Min | Emne | Format |
|-----|------|--------|
| 0–10 | Hvorfor pilot — ikke big bang | Champion |
| 10–25 | Live demo: morgenbriefing, godkend, step-up | EIRA |
| 25–40 | **Øvelse 1:** Login (passkey/kort) | Alle |
| 40–55 | **Øvelse 2:** Find og godkend én opgave | Par |
| 55–70 | **Øvelse 3:** Skriv intention i feltet nederst | Individ |
| 70–85 | Hvad I *ikke* skal kunne endnu (ærlig liste) | EIRA |
| 85–110 | FAQ + "hvor får jeg hjælp" | L1 + champion |
| 110–120 | Feedback-slips / Teams-kanal | Alle |

### 5.2 "Hvad vi ikke lover" (læs højt)

1. Ikke alle Windows-programmer — hybrid findes.  
2. Ikke egen printer hvis den ikke er på Support Matrix.  
3. Ikke filer og mapper som I kender dem — handlinger og relationer.  
4. Ikke perfekt fra dag 1 — I har rollback og champion.  
5. Ikke IT-support til Ubuntu — kontakt L1 med skærmbillede.

*Fuldt dokument:* udfyld i [Business Plan Sprint](../../../company/EIRA_Business_Plan_Sprint_v0.1.md) Spor 2.

### 5.3 Øvelseskort (print/digital)

**Øvelse 2 — Godkend noget der venter på dig**

1. Læs øverste handlingskort.  
2. Tryk [Godkend] eller [Vis først].  
3. Læs *hvorfor* EIRA foreslår det.  
4. Bekræft.  
5. ✓ Færdig — ingen Public360 åbnet.

---

## 6. Introduktion af Intent Interface

**Metode:** Show — don't tell. Ingen "AI"-marketing.

| Gør | Gør ikke |
|-----|----------|
| "Skriv hvad du vil opnå" | "Chat med assistenten" |
| Vis rationale før bekræft | Auto-udfør uden forklaring |
| Én hero-opgave ad gangen | 15 notifikationer |
| "EIRA foreslår" | "EIRA ved" |

**30-sekunds script til champion:**

> *"Nederst skriver du som til en kollega: 'Godkend budget' eller 'Hvad venter på mig?'. EIRA viser hvad den mener — du siger ja eller nej. Den åbner ikke noget før du bekræfter."*

---

## 7. L1 runbook — 10 FAQ

| # | Bruger siger | L1 svar | Eskalér hvis |
|---|--------------|---------|--------------|
| 1 | Hvor er Outlook? | M365 i browser/Teams — samme konto | Mail sync fejler > 1t |
| 2 | Hvor er mine filer? | OneDrive/M365 — ikke lokale mapper | Data mangler |
| 3 | Printer virker ikke | Tjek IPP-liste i Support Matrix | Efter L0 CUPS 48t |
| 4 | VPN | Genstart PC; tjek ikon | NET-4 compliance rød |
| 5 | MitID / smartcard | Genindlæs kort; step-up igen | HW-2 fejler |
| 6 | "Det ligner ikke min gamle PC" | Forventet — kontakt champion | Massiv modstand |
| 7 | Kan jeg installere X? | Kun godkendte apps — anmod i Portal | Policy-blok |
| 8 | PC langsom | Support Bundle ét klik → L2 | PERF-3 |
| 9 | Jeg vil tilbage | Champion — ikke skændes; BCP Tier 3 | IT-chef |
| 10 | Fejlmeddelelse | Screenshot + device_id til L2 EIRA | P1 incident |

**Eskalering:** L1 → EIRA L1 (4t SLA pilot) → L2 engineering.

---

## 8. Modstand og feedback

### 8.1 Typiske modstandsmønstre

| Mønster | Respons |
|---------|---------|
| "Jeg er hurtigere på gammel PC" | Superbruger viser én gentagen opgave; mål tid uge 4 |
| "IT tvinger os" | Champion: frivillig afdeling; rollback mulig |
| "Det er AI — jeg stoler ikke" | Vis rationale + bekræft; rule-only mode |
| "Jeg finder ikke sagen" | Inputfelt: "Åbn sag om skolebyggeri" — træning |

### 8.2 Feedback-kanaler

| Kanal | Frekvens | Ejer |
|-------|----------|------|
| Teams #eira-pilot | Løbende | Champion |
| 5-spørgsmåls survey | Uge 2, 8, 12 | EIRA + champion |
| Office hours | Uge 4 | EIRA |
| L1 ticket-tags | Ugentlig rapport | IT |

### 8.3 Survey (5 spørgsmål)

1. Kan du udføre din vigtigste daglige opgave? (1–5)  
2. Forstår du hvorfor EIRA foreslår handlinger? (1–5)  
3. Hvor ofte var du frustreret denne uge? (1–5, lavt bedre)  
4. Ville du anbefale fortsættelse til kollega? (ja/nej)  
5. Én ting vi skal fixe først? (frit tekst)

**Kill threshold:** se [Validation Plan](EIRA_Pilot_Validation_Plan_v0.1.md) §5.3.

---

## 9. Kommunikationsskabeloner

### Intranet (uge −1)

**Titel:** Ny arbejdsflade i [afdeling] — frivillig pilot

> I [måned] får ca. 50 kollegaer en ny PC-oplevelse: samme login, færre systemskift, tydelige opgaver. Det er en **pilot med rollback** — ikke hele kommunen. Spørgsmål: [champion]. Info-møde: [dato].

### E-mail dag 0

> Din PC er klar. Log ind som vanligt. Onboarding [tid/sted]. Hjælp: [Teams-kanal]. Husk: du bekræfter handlinger — EIRA gætter ikke i skjul.

---

## 10. Integration med BCP

| Brugerreaktion | Change-respons | BCP |
|----------------|----------------|-----|
| Enkelt bruger desperation | Champion 1:1; evt. Tier 3 | BCP §5 Tier 3 |
| >25% negativ survey | Office hours + fix plan | Tier 1 degraded |
| Massiv modstand | IT-chef møde | Tier 4 vurdering |

---

## 11. Succesmetrikker (pilot)

| Metric | Mål uge 12 |
|--------|------------|
| Onboarding deltagelse | 100% |
| Survey svarrate | ≥ 70% |
| "Kerneopgave OK" | ≥ 80% |
| L1 tickets per bruger | ≤ 1.5 i pilot vs. baseline |
| Champion anbefaling | Fortsæt Fase 2 |

---

## 12. Leverancer-checkliste

| ☐ | Leverance | Frist |
|---|-----------|-------|
| ☐ | Champion mandat skriftligt | Uge −2 |
| ☐ | Intranet-tekst godkendt | Uge −1 |
| ☐ | Onboarding slides + øvelseskort | Uge −1 |
| ☐ | Teams-kanal oprettet | Uge 0 |
| ☐ | L1 FAQ printet / Confluence | Uge 0 |
| ☐ | Survey link klar | Uge 2 |
| ☐ | "Hvad vi ikke lover" 1-pager | Uge −1 |

---

*EIRA Change Management Pilot v0.1 — gennemgås med champion før Fase 1 start.*
