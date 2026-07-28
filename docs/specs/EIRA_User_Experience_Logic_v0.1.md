# EIRA OS � Brugeroplevelse og brugslogik v0.1

**Status:** Produkt-UX � brugerens perspektiv  
**Dato:** 26. juni 2026  
**M�lgruppe:** Produkt, design, udvikling  
**Ikke dette dokument:** IT, Fleet Control, adaptere, Ubuntu (se andre specs)

---

## 1. Det brugeren skal forst� (�t princip)

> **Du beskriver hvad du vil opn�. EIRA finder vejen.**

Brugeren er ikke ansat til at navigere systemer. Brugeren er ansat til at l�se opgaver.

EIRA fjerner:
- startmenu, skrivebord, filer, mapper, programnavne  
- "�bn SharePoint ? find dokument ? �bn Public360 ? log ind ? godkend"

EIRA giver:
- **handlinger** prioriteret efter hvad der betyder noget **nu**

---

## 2. Opm�rksomhedsk�den � brugerens mentale model

Alt i EIRA f�lger samme k�de. Brugeren beh�ver ikke kende begreberne � men oplevelsen er bygget p� dem:

```
Tilstand  ?  Fokus  ?  Akt�rer  ?  Intention  ?  Handling
```

| Led | Hvad brugeren oplever | Eksempel |
|-----|----------------------|----------|
| **Tilstand** | "Hvilken del af livet er jeg i?" | Arbejde / M�de / Fritid |
| **Fokus** | "Hvad arbejder jeg med lige nu?" | Kommunepilot / Et specifikt projekt |
| **Akt�rer** | "Hvem er relevant?" � ikke "hvem er online" | Lars, �konichefen, sagsbehandlingen |
| **Intention** | "Hvad vil jeg?" (tekst eller knap) | Godkend budget |
| **Handling** | Det systemet g�r bagved | Godkendelse i Public360 |

**Brugeren t�nker i m�l og relationer � ikke i filstier.**

---

## 3. Hvad brugeren ser (og ikke ser)

### Ser

- �n flade: **EIRA Explorer** (fullscreen shell)  
- Personlig hilsen + **prioriterede handlinger**  
- Relationer: `Budget 2026 ? Sag 2024-15 ? Lars`  
- Forklaring f�r handling: *hvorfor* systemet foresl�r noget  
- �t inputfelt � altid (overstyring)

### Ser aldrig

- SharePoint, Public360, KMD OPUS som navne i daglig brug  
- Filer, mapper, stier  
- Ubuntu, terminal, apt (medmindre Builder Mode)  
- Adaptere, API'er, tokens  

---

## 4. En typisk arbejdsdag (narrativ)

### Morgen � ankomst

```
1. Mette �bner EIRA PC (passkey / kort login)
2. Sk�rmen viser:

   Hej Mette � Arbejde � Fokus: Kommunepilot

   ? Budget 2026 mangler godkendelse f�r kl. 17
      Sag 2024-15 � fra �koniteamet
      [Godkend]  [Vis f�rst]

   ? M�de om 30 min � materiale klar
      [�bn materiale]

   ? 2 beskeder venter (mindre vigtigt � foldet sammen)

3. Mette trykker [Godkend]
```

### Mellem handling � systemet arbejder

```
4. EIRA viser:

   ?? Jeg vil godkende budget_2026.docx i sag 2024-15
      Fordi: det er det budget der venter i dit fokus,
      og fristen er i dag kl. 17.

      [Bekr�ft]  [V�lg andet budget]  [Annuller]

5. (Evt.) MitID Erhverv � kun fordi godkendelse kr�ver det:
   "Denne handling kr�ver organisationstillidelse"
   [Forts�t med MitID Erhverv]

6. ? Budget godkendt
   Kort bekr�ftelse � Mette er f�rdig. Ingen Public360.
```

### Resten af dagen

- Nye handlinger dukker op efterh�nden som agenten prioriterer  
- Mette skifter fokus: "Skift til Skolebyggeri-projekt" � listen �ndrer sig  
- Kun **�n ting skriger ad gangen** �verst (regel 4)

---

## 5. Explorer Mode � brugslogik

**95% af brugere. Hele livet i Explorer.**

| Element | Funktion |
|---------|----------|
| **Hilsen + tilstand/fokus** | Kontekst � hvorfor vises dette? |
| **Handlingskort** | Prioriteret liste � ikke notifikationer fra 10 apps |
| **Prim�r knap** | Den foresl�ede handling |
| **Sekund�r** | Vis, udskyd, afvis |
| **Inputfelt** | Altid nederst � fri intention eller overstyring |
| **Foldet st�j** | Mindre vigtige ting � tilg�ngelige, ikke skrigende |

**Ingen filer. Ingen mapper. Kun handlinger.**

### Inputfeltet � altid �ben

Brugeren kan altid skrive:
- `Godkend budget`
- `Send referat til Lars`
- `Hvad venter p� mig?`
- `Skift fokus til Skolebyggeri`

Systemet parser ? viser forslag ? bruger bekr�fter. **Aldrig silent execute.**

---

## 6. Seks UX-regler (normative)

| # | Regel | I praksis |
|---|-------|-----------|
| 1 | Brugeren ser **�t system** | Kun "EIRA" � aldrig "�bn Public360" |
| 2 | Brugeren **handler** � systemet finder vej | Knap / intention, ikke navigation |
| 3 | Vis **relationer**, ikke stier | Budget ? Sag ? Person |
| 4 | **�n ting** skriger ad gangen | Prioritering � resten foldes |
| 5 | **Forklar hvorfor** | Rationale f�r hver handling |
| 6 | Brugeren kan **altid overstyre** | Inputfelt + alternativer |

Regel 5 og 6 er make-or-break (se Risk Sprint 0-1).

---

## 7. Agentens rolle (usynlig for brugeren)

Brugeren ser **resultatet** af agenten � ikke agenten:

```
Bagved:
  Analyzer    ? hvad findes p� tv�rs af adaptere?
  Prioritizer ? hvad er vigtigst i dette fokus?
  Suggester   ? hvilken handling foresl�s?
  Executor    ? kald adapter efter bekr�ftelse

Foran:
  "Budget 2026 mangler godkendelse f�r kl. 17"
```

Agenten er ** ikke en chatbot**. Den er en **prioriteringsmotor** der kun taler n�r den har noget konkret.

---

## 8. Bekr�ftelsesflow (brugerens sikkerhedsnet)

Hver ikke-trivial handling genneml�ber:

```
Foresl�  ?  Forklar  ?  Bekr�ft  ?  Udf�r  ?  Bekr�ft resultat
```

| Confidence | Brugeroplevelse |
|------------|-----------------|
| H�j | Kort rationale + [Bekr�ft] |
| Medium | Valg mellem kandidater |
| Lav | "Hvad mener du?" � ingen udf�relse |

**Step-up (MitID m.fl.)** er et ekstra trin i samme flow � med forklaring, ikke som separat login-helvede.

---

## 9. Tilstand og fokus � brugerlogik

### Tilstand (sj�ldent skiftet manuelt)

| Tilstand | Effekt |
|----------|--------|
| Arbejde | Alle arbejds-handlinger, adaptere aktiv |
| M�de | Kalender, materialer, korte handlinger |
| Fritid | Arbejdssystemer d�mpet (p� arbejds-PC: policy) |
| Krise | Kun kritiske handlinger � alt andet skjult |

IT kan l�se tilstande p� arbejds-PC. Privat EIRA PC: bruger v�lger.

### Fokus (skiftes ofte)

- "Kommunepilot", "Skolebyggeri", "Budget 2026"  
- Skift via input: `Skift fokus til Skolebyggeri`  
- Hele handlingslisten genberegnes  

**Fokus reducerer st�j** � det er EIRA's erstatning for "mapper og favoritter".

---

## 10. Builder Mode � bevidst undtagelse

| | Explorer | Builder |
|---|----------|---------|
| Hvem | Alle medarbejdere | IT, udviklere |
| UI | Chrome-shell, handlinger | Terminal, Docker, logs |
| Ubuntu synlig? | Nej | Ja |

Standardbrugeren ved ikke Builder findes.

---

## 11. Fejl og gr�nser (brugerens oplevelse)

| Situation | Hvad brugeren ser |
|-----------|-------------------|
| Adapter nede | "Public360 er midlertidigt utilg�ngelig � pr�v igen om 10 min" |
| Offline | "Begr�nset tilstand � du kan l�se cachede ting, ikke godkende" |
| Policy blokerer | "Din organisation tillader ikke denne handling" + hvorfor |
| EIRA g�ttede forkert | Bruger retter ? systemet l�rer (uden at genere) |

Aldrig: stack traces, HTTP-fejl, adapter-navne.

---

## 12. Brugslogik vs. teknisk arkitektur

| Brugeroplevelse | Teknik (skjult) |
|-----------------|----------------|
| Handlingskort | Agent + Intent + Objektgraf |
| Godkend | Adapter ? Public360 |
| Forklar hvorfor | Rationale extraction |
| MitID-trin | Identity step-up |
| Fokus skifter | Context i objektgraf |

Brugeren beh�ver ikke kende h�jre kolonne.

---

## 13. Successkriterier (bruger-pilot)

| Metrik | M�l |
|--------|-----|
| Tid til f�rste handling | < 30 sek efter login |
| Systemnavne n�vnt af bruger | 0 i interview |
| "Forstod hvorfor EIRA foreslog X" | ? 8/10 |
| Rettelser per dag | ? 2 |
| Foretr�kker EIRA fremfor gammel PC | ? 90% |

---

## 14. �n s�tning til design og udvikling

> **EIRA er ikke et sted man g�r hen. Det er det sted man starter � med det ene der betyder noget nu, og �n s�tning der �bner resten.**

---

## Relaterede dokumenter (operationalisering)

| Spørgsmål | Dokument |
|-----------|----------|
| Visuelt sprog (Calm Command) | [UX Visual Language](EIRA_UX_Visual_Language_v0.1.md) |
| Produktvision (horisont) | [Situation UI Vision](EIRA_Situation_UI_Vision_v0.1.md) |
| Hero og klynger | [Prioritization Heuristics](EIRA_Prioritization_Heuristics_v0.1.md) |
| Shell og IPC | [Desktop Architecture v1.0](EIRA_Desktop_Architecture_v1.0.md) |
| Prototype UI | [phase1/ui](../../prototype/phase1/ui/) |
| Navigation | [Document Map](../EIRA_Document_Map_v0.1.md) |

---

*EIRA OS � Brugeroplevelse og brugslogik v0.1*
