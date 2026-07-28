# EIRA � Success / Failure Matrix v0.1

**Status:** Strategisk vurdering � �rlig, ikke hype  
**Dato:** 26. juni 2026  
**Form�l:** 25 medvind + 25 modvind � hvad forst�rkes, hvad mitigeres p� forh�nd  
**Relateret:** [EIRA_Strategic_Reality_Check_v0.1.md](EIRA_Strategic_Reality_Check_v0.1.md), [EIRA_Risk_Sprint_0-1_v0.1.md](EIRA_Risk_Sprint_0-1.md)

---

## S�dan l�ses matricen

| Symbol | Betydning |
|--------|-----------|
| **Kontrol** | H�j / Medium / Lav / Ingen � hvor meget EIRA-teamet kan p�virke udfaldet |
| **Status** | ? D�kket i specs � ?? Delvist � ? Ikke adresseret � ?? Ekstern afh�ngighed |

**Kerneindsigt (begge lister er sande):**

> Det afg�rende er om **indt�gt fra wedges (ECK, Fleet, Audit, services)** kommer ind hurtigt nok til at overleve de **18�36 m�neder** det politiske spor kr�ver. Det er det punkt med **h�jest kontrol** lige nu.

---

# DEL A � 25 grunde til at det lykkes

## A1. Strukturelle / politiske medvind

| # | Grund | G�re det bedre? | Handling |
|---|-------|-----------------|----------|
| 1 | NIS2 ? Intent Audit forspring | **Ja** | Skriv NIS2?Intent Audit mapping (1-side til CISO). Compliance Engine P1. |
| 2 | EU-datasuver�nitet / Schrems II | **Ja** | Salgs-one-pager: "local-first + EU" med konkrete dataflows � ikke abstrakt. |
| 3 | Digst / BMI eID-infrastruktur | **Ja** | Hold dk-pack/de-pack som roadmap; **s�lg Entra-first** nu, eID som fase 2. |
| 4 | EUDI Wallet 2027 | **Ja** | Position�r som "EUDI-ready architecture" � dokumenteret i Identity Strategy. |
| 5 | Microsoft licens-smerte | **Medium** | TCO-model i `company/` � sammenlign EIRA PC + bundle vs. M365+E5 per seat. |
| 6 | KL/KOMBIT f�llesindk�b | **Ja** | Udbudstekst-kladde f�rdig **f�r** politisk m�de � ikke efter. |
| 7 | Open Architecture s�nker leverand�r-modstand | **Ja** | "Leverand�r beholder kunde" narrativ i hver adapter-samtale. Certificeringsprogram tidligt. |

## A2. Produktdifferentiering

| # | Grund | G�re det bedre? | Handling |
|---|-------|-----------------|----------|
| 8 | Intent Audit � Windows kan ikke nemt kopiere | **Ja** | **Demo f�rste** til IT/CISO � ikke Explorer. CEF/Wazuh live dag 1. |
| 9 | "Hvorfor blokeret" + rationale | **Ja** | Rationale PoC er make-or-break (R2) � prioriter over Fleet UI-polish. |
| 10 | Adapter Standard netv�rkseffekt | **Medium** | SDK + Test Suite public **f�r** leverand�r-m�de. 2 reference-adaptere i video. |
| 11 | Policy-as-code (YAML/git) | **Ja** | Policy Compiler arkitektur � vis git-diff i Portal (P2). |
| 12 | Hybrid-first s�nker risiko | **Ja** | Sig det **f�rst** i hvert salgsm�de � allerede i Enterprise IT. |
| 13 | Egne reference-adaptere | **Ja** | **M365-first wedge** � fastl�s som pilot-default. |
| 14 | Rule-first / fail-closed | **Ja** | Behold kill criterion. Brug som **trust signal** i CISO-materiale. |

## A3. Eksekvering / team

| # | Grund | G�re det bedre? | Handling |
|---|-------|-----------------|----------|
| 15 | Erfaring (Ukraine, CareApp, PIM) | **Ja** | Navngiv 2-3 **genbrugelige komponenter** (auth, fleet patterns) � reducer ny kode. |
| 16 | Dokumentationsdisciplin (kill criteria, spikes) | **Medium** | **Stop docs n�r vertical slice starter** � max 1 arkitekt-doc per uge herefter. |
| 17 | �rlig intern svaghedsanalyse | **Ja** | Opdater denne matrix kvartalsvis � levende dokument. |

## A4. Marked / timing

| # | Grund | G�re det bedre? | Handling |
|---|-------|-----------------|----------|
| 18 | Ingen dominerende EU OS-konkurrent endnu | **Medium** | Overv�g EU sovereign desktop-initiativer � 1�/kvartal competitive scan. |
| 19 | Budgetpres i kommuner | **Ja** | Pris fra slide 10 (899 DKK/�r) valideret mod reel TCO � opdater hvis forkert. |
| 20 | Tyskland / BundID som plan B marked | **Lav nu** | Ikke s�lg Tyskland f�r DK-reference � men hold de-pack i arkitektur. |
| 21 | SMB hurtigere end udbud | **Ja** | **Aktivt unders�g:** SMB med M365-frustration som paid pilot f�r kommune. |

## A5. Strategisk forsvar

| # | Grund | G�re det bedre? | Handling |
|---|-------|-----------------|----------|
| 22 | Plan B (spikes, Entra-only, Legacy Bridge) | **Ja** | Factory Enroll + Policy Compiler nu spec'et � **ship** dem. |
| 23 | Wedge-strategi (M365, Fleet+Audit) | **Ja** | **Beslut indt�gtsmodel uge 1:** hvad s�lges f�r pilot? ECK? Fleet licens? |
| 24 | EU AI Act bygget ind | **Ja** | ai_metadata i Object Graph � vis i audit demo. |
| 25 | Open Architecture overlever produktfiasko | **Medium** | Public�r Adapter + Intent Spec som **�ben standard** uafh�ngigt af EIRA OS salg. |

---

# DEL B � 25 grunde til at det g�r galt

## B1. Marked / adoption

| # | Risiko | Kontrol | Mitigation (eksisterende) | G�re p� forh�nd |
|---|--------|---------|---------------------------|-----------------|
| 1 | R1b � leverand�rer bygger ikke adaptere | Lav | Reality Check wedges; EIRA ejer reference | **Betalt integration** som service; udbudstekst; aldrig vente p� KMD |
| 2 | Udbud 12�24 mdr vs. indt�gtsbehov 6 mdr | Medium | Wedges: Fleet, Audit, ECK, SMB | **Indt�gtsplan med m�ned 3�6 milestones** � ikke kun pilot |
| 3 | Ingen vil v�re first mover | Medium | Hybrid; frivillig afdeling; 50 PC | Find **1 IT-chef champion** med personlig gevinst (audit, karriere) |
| 4 | IT-konservatisme strukturel | Lav | Fleet paritet, �rlig Windows-matrix | S�lg **til CISO f�r borgmester**; ikke "ny computer" men "bedre kontrol" |
| 5 | Fagsystem kr�ver Windows kontraktuelt | Lav | Hybrid; Legacy Runtime KVM/RDP | **Pilot-selektion:** afdelinger uden kontraktklausul; dokument�r i salg |

## B2. Teknisk usikkerhed

| # | Risiko | Kontrol | Mitigation | G�re p� forh�nd |
|---|--------|---------|------------|-----------------|
| 6 | Legacy Bridge / FUSE urobust | H�j | Portal-first; spike; Plan B | **2-uges spike uge 1**; kill ? KVM/M365 Web only |
| 7 | VPN pre-login blocker | H�j | OpenConnect; Factory Enroll cert | **VPN matrix test** p� kommunens VPN **f�r** pilot-commit |
| 8 | EDR-partner ikke valgt | H�j | Wazuh+Falco i bundle | **V�lg partner inden uge 4** � CrowdStrike/MDE/Wazuh-managed |
| 9 | Wayland/XWayland glitches | Medium | labwc; Explorer fullscreen | Test **whitelisted apps** p� reference-PC; dokument�r kendte issues |
| 10 | Intent confidence fejler; kill criterion udl�ses | H�j | Rule-first; Rationale PoC; 50 intentions | **Indsaml 50 reelle intentioner nu**; rule-only demo hvis LLM fejler |
| 11 | Fleet Control kun design | H�j | Factory Enroll; Agent Protocol | **Fleet MVP scope:** enroll + heartbeat + bundle + wipe � intet mere i pilot |

## B3. Ressourcer / eksekvering

| # | Risiko | Kontrol | Mitigation | G�re p� forh�nd |
|---|--------|---------|------------|-----------------|
| 12 | 3�4 produkter samtidig, lille team | H�j | Vertical slice; Entra-only; Fleet MVP | **�n beslutning:** Sprint 0 scope � skriftligt, max 6 komponenter |
| 13 | Grundl�gger �konomi � projekt kv�les | **H�j** | ECK wedge; services; SMB | **Indt�gtsdeadline:** konkret bel�b + kilde inden m�ned 3 |
| 14 | Scope for stort � historiske fiaskoer | H�j | Reality Check; docs discipline | **Ship commit uge 2** � governance-agent hello world |
| 15 | Ukraine-team afh�ngighed | Medium | � | Kontrakt/retainer; **lokal backup** p� kritisk komponent |
| 16 | Microsoft/EU "god nok" sovereign pakke | Lav | Intent Audit differentiator | Overv�g; **dobbelt ned p� audit+datasuver�nitet** som ikke-M365-kopi |

## B4. Strategisk / politisk

| # | Risiko | Kontrol | Mitigation | G�re p� forh�nd |
|---|--------|---------|------------|-----------------|
| 17 | Sovereignty = retorik uden budget | Lav | NIS2 compliance angle | S�lg **compliance + audit** � ikke ideologi alene |
| 18 | KL/KOMBIT sluger tid uden indt�gt | Medium | Parallel spor | **Tidsbudget:** max 20% founder-tid p� politik indtil indt�gt |
| 19 | Pilot-KPI'er ikke n�et | H�j | Realistiske KPI'er; pilot-selektion | **V�lg pilot-afdeling uden VBA/makroer**; s�nk NPS-m�l hvis n�dvendigt |
| 20 | Forsikring/cert-krav Windows | Lav | Hybrid | Dokument **"hvad vi ikke lover"**; EDR+audit som erstatning for skabelon |

## B5. Eksistentielle

| # | Risiko | Kontrol | Mitigation | G�re p� forh�nd |
|---|--------|---------|------------|-----------------|
| 21 | Adapter Standard h�ne-�g | Medium | EIRA ejer adaptere; Open Standard | **Standard kan leve** selv uden leverand�rer (A25) |
| 22 | Identity for ambiti�s | H�j | Sprint 1 Entra-only | **Hold linjen** � ingen EUDI i Sprint 1 kode |
| 23 | Founder fuldtidsjob ? momentum tabt | **H�j** | � | **Beslut nu:** minimum viable indt�gt vs. fuldtidsjob trigger |
| 24 | Mange specs, ingen shipping | **H�j** | Vertical slice defineret | **Freeze docs** efter denne matrix � kode f�r n�ste spec |
| 25 | Perfekt produkt, ingen vil v�re reference | Medium | Champion IT-chef; hybrid | **Betalt pilot** eller **risiko-deling** med f�rste kommune |

---

# DEL C � Prioriteret handlingsliste (kontrollerbare nu)

## G�r inden uge 4 (h�j kontrol, h�j impact)

| # | Handling | Adresserer |
|---|----------|------------|
| 1 | **Indt�gtsplan m�ned 3�6** (ECK / Fleet / services / SMB) | B2, B13, A23 |
| 2 | **Sprint 0 vertical slice** � skriftlig, max 6 komponenter | B12, B14, B24 |
| 3 | **F�rste git commit** � governance-agent eller enroll stub | B24, A16 |
| 4 | **EDR-partner beslutning** (Wazuh-only OK for pilot?) | B8 |
| 5 | **VPN test** p� target kommune eller lignende | B7 |
| 6 | **50 intentioner** indsamlet til R2 PoC | B10, A9 |
| 7 | **Pilot wedge:** M365-first + champion IT-chef | A13, B3, B25 |
| 8 | **Doc freeze** � kun kode + denne matrix opdateres | B24, A16 |

## G�r inden pilot-commit

| # | Handling | Adresserer |
|---|----------|------------|
| 9 | Legacy Bridge spike go/no-go | B6 |
| 10 | Factory Enroll kanal B (USB) testet | A22 |
| 11 | Fleet MVP: enroll + bundle + compliance % | B11 |
| 12 | NIS2/Intent Audit 1-pager til CISO | A1, A8 |
| 13 | Pilot-selektionskriterier (ingen VBA-afdeling) | B5, B19 |
| 14 | "Hvad vi ikke lover" til IT | B5, B20 |

## Accept�r (lav kontrol � ikke brug energi)

- Leverand�r frivillig adapter-adoption uden betaling (B1) � kun politik + betalt integration
- F�rste-mover politisk risiko hos kunden (B3, B25) � hybrid + frivillig afdeling
- Forsikringsskabeloner (B20) � dokument�r workaround
- EU-konkurrent med sovereign M365 (B16) � overv�g kun

---

# DEL D � Forst�rk de 5 st�rkeste kort

| Rang | Styrke | G�r endnu bedre |
|------|--------|-----------------|
| 1 | **Intent Audit** | Live demo til CISO **f�r** bruger-pilot |
| 2 | **Wedge / indt�gt uden R1b** | Skriv konkret pris + pipeline i `company/` |
| 3 | **�rlig arkitektur + kill criteria** | Brug i salg � "vi stopper hvis X" |
| 4 | **Factory Enroll + OSS bundle** | Ship kanal B � bevis zero-touch for 1 PC |
| 5 | **Hybrid + M365-first** | V�lg pilot-kommune der allerede er M365-tunge |

---

# DEL E � De 5 farligste modvind (tidligste advarsel)

| Rang | Risiko | Tidligste signal |
|------|--------|------------------|
| 1 | **Ingen indt�gt ? founder stopper** | M�ned 3 uden betalende kunde |
| 2 | **Docs uden kode** | Ingen commit uge 4 |
| 3 | **VPN/EDR blocker pilot** | IT siger nej i uge 1 teknisk review |
| 4 | **Intent kill criterion udl�ses** | PoC < 70% top-1 |
| 5 | **Fleet ikke klar til IT** | IT kr�ver wipe/compliance f�r 50 PC |

---

## �n s�tning

> **Succes-listen er jeres produkt og marked. Fejl-listen er jeres kalender og cashflow. Begge er sande � men kun wedges, vertical slice og indt�gtsdeadline er under fuld kontrol denne m�ned.**

---

## Relaterede dokumenter (operationalisering)

| Spørgsmål | Dokument |
|-----------|----------|
| Kvantitative gates | [Performance Acceptance](EIRA_Performance_Acceptance_v0.1.md) |
| Pilot og indtægt | [Business Plan Sprint](../../company/EIRA_Business_Plan_Sprint_v0.1.md) |
| Brugeraccept | [Change Management Pilot](EIRA_Change_Management_Pilot_v0.1.md) |
| Handlingsplan | [Sprint Plan](../Sprint_Plan_v0.1.md) |
| Navigation | [Document Map](../EIRA_Document_Map_v0.1.md) |

---

*EIRA Success / Failure Matrix v0.1 � opdater ved pilot-go/no-go.*
