# EIRA Identity Strategy v0.2

**Status:** Udkast ? strategisk specifikation  
**Dato:** 26. juni 2026  
**Projekt:** EIRA OS  
**?ndringer fra v0.1:** Enterprise IdP-connectors (Microsoft Entra ID, Google Workspace)  
**Relateret:** EIRA Open Architecture v1.0, EIRA Identity Specification v0.1

---

## 1. Form?l

Dette dokument definerer EIRA OS' identitetsarkitektur: **EIRA Identity Bridge** og companion-appen **EIRA Authenticator**.

Kernebeslutning:

> EIRA bygger mod EU's wallet-protokoller (OID4VP/OID4VCI). Danmark og Tyskland implementeres som **country packs**. Microsoft og Google implementeres som **IdP-connectors** ? ikke som erstatning for eID ved h?j assurance.

---

## 2. Problemstilling

EIRA OS whitepaper og pr?sentation identificerer login som en central smertepunkt, men specificerer kun LDAP/Active Directory under Enterprise Governance. Det er utilstr?kkeligt for:

- Kommunal/offentlig sektor i Danmark og Tyskland
- Step-up autentificering ved sensitive intentioner ("Godkend budget")
- Handling p? vegne af organisation (ikke kun privatperson)
- Europ?isk skalering (eIDAS 2.0 / EUDI Wallet)
- Hybrid-milj?er med Microsoft 365 / Google Workspace (dominerende i kommuner)
- Overgangsfasen 2026?2030 hvor nationale eID'er og wallets sameksisterer

---

## 3. Strategiske principper

| # | Princip | Betydning |
|---|---------|-----------|
| 1 | **EUDI-first (protokol)** | Kerneimplementering mod OID4VP/OID4VCI og ARF ? ikke mod ?t nationalt brand |
| 2 | **Country packs** | Landespecifik eID-logik isoleres i plugins (`dk-pack`, `de-pack`) |
| 3 | **IdP connectors** | Enterprise-login (Microsoft, Google, SAML/OIDC) som separat spor |
| 4 | **Organisationsidentitet er separat** | Borger-wallet ? medarbejder-rolle |
| 5 | **Step-up, ikke alt-eller-intet** | Entra til daglig brug; eID/wallet n?r handlingen kr?ver det |
| 6 | **Local-first** | Tokens og sessions lokalt; brokere kun ved behov |
| 7 | **Ingen vendor lock-in** | ?bne standarder; exit til anden wallet/IdP mulig |

---

## 4. Arkitekturplacering

EIRA OS har i dag 7 lag. Identitet tilf?jes som **Lag 1.5: Identity Layer** mellem Pr?sentation og Agent Engine.

```
LAG 1   ? Pr?sentation (Explorer Mode / Builder Mode)
LAG 1.5 ? Identity Layer
          ??? eira-identityd (desktop daemon)
          ??? EIRA Authenticator (mobil + desktop companion)
          ??? Session & token vault (lokal, krypteret)
          ??? Step-up policy engine
          ??? OID4VP/OID4VCI verifier
          ??? Country pack loader (dk, de)
          ??? IdP connector loader (Microsoft, Google, SAML/OIDC)
LAG 2   ? Agent Engine
LAG 3   ? Intent Interface
LAG 4   ? Capability Layer
LAG 5   ? Objektgraf (tynd cache)
LAG 6   ? Adapter Layer
LAG 7   ? Kildesystemer
```

### 4.1 Komponenter

| Komponent | Teknologi (forel?big) | Ansvar |
|-----------|----------------------|--------|
| `eira-identityd` | Rust | Sessions, tokens, policy, pack/connector-loading |
| `eira-auth-app` | Tauri (mobil + desktop) | Wallet-brokering, brugerudfordringer, godkendelser |
| `eira-identity-core` | Rust | OID4VP/OID4VCI, ARF/HAIP, trust lists, OIDC |
| `eira-identity-dk` | Rust | MitID, AltID, MitID Erhverv broer |
| `eira-identity-de` | Rust | EUDI Wallet, BundID, eID broer |
| `eira-identity-idp` | Rust | Microsoft Entra ID, Google Workspace, generisk OIDC/SAML |
| Policy config | YAML | `/etc/eira/identity_policy.yaml` |

---

## 5. EIRA Identity Bridge ? f?lles kerne

### 5.1 Protokoller

| Protokol | Standard | Anvendelse |
|----------|----------|------------|
| **OID4VP** | OpenID4VP + HAIP | Wallet-pr?sentationer (country packs) |
| **OID4VCI** | OpenID4VCI | Modtag credentials (fremtidig) |
| **OIDC + PKCE** | RFC 7636 | MitID, Entra ID, Google, BundID |
| **SAML 2.0** | OASIS | Legacy Entra, tyske Landes-IdP'er |
| **WebAuthn / Passkeys** | W3C | OS-unlock og daglig session |

### 5.2 To spor ? ikke ?n login

```
???????????????????????????????????????????????????????????????
?                    EIRA Identity Bridge                      ?
???????????????????????????????????????????????????????????????
?  Country packs (eID)     ?  IdP connectors (enterprise)      ?
?  AltID / EUDI Wallet     ?  Microsoft Entra ID               ?
?  MitID / MitID Erhverv   ?  Google Workspace                 ?
?  BundID / eID            ?  LDAP / AD, generisk OIDC/SAML    ?
???????????????????????????????????????????????????????????????
?              Step-up policy engine (v?lger spor)             ?
???????????????????????????????????????????????????????????????
```

| Spor | Form?l | Typisk assurance |
|------|--------|------------------|
| **IdP connector** | Daglig org-login, M365/Google, SSO til adaptere | `session` ? `eid_low` |
| **Country pack** | Step-up, signering, offentlige tjenester | `eid_high` ? `qualified_sign` |

---

## 6. Step-up policy engine

### 6.1 Assurance levels

| Niveau | Beskrivelse | Typisk kilde |
|--------|-------------|--------------|
| `session` | Daglig OS-session | Passkey / PIN |
| `eid_low` | Verificeret identitet, lav | Entra/Google med MFA, BundID basic |
| `eid_high` | St?rk identitet | MitID, eID, EUDI PID |
| `org_acting` | Handle p? vegne af organisation | MitID Erhverv, lokal IdP |
| `qualified_sign` | Juridisk bindende signatur | MitID QES, EUDI QES (V2) |

### 6.2 Policy-eksempel (hybrid)

```yaml
identity_policy:
  default_assurance: session

  idp_connectors:
    - id: entra-primary
      type: microsoft_entra
      tenant_id: "${ENTRA_TENANT_ID}"
      client_id: "${ENTRA_CLIENT_ID}"
      default_for_org_login: true
      max_assurance: eid_low

  step_up_rules:
    - action: read
      resource: sharepoint_document
      min_assurance: session
      accept_idp: [entra-primary]

    - action: approve
      resource: budget
      min_assurance: org_acting
      require_country_pack: [dk, de]

    - action: sign
      resource: legal_document
      min_assurance: qualified_sign
      require_country_pack: [dk, de]
```

**Regel:** Microsoft/Google l?ser *"hvem er du i organisationen"*. Country packs l?ser *"bevis det juridisk"*.

---

## 7. Enterprise IdP-connectors: Microsoft og Google

### 7.1 Kan vi underst?tte det?

**Ja.** OIDC og SAML er allerede i protokolstacken. Microsoft Entra ID og Google Workspace er **IdP-connectors** ? ikke country packs.

### 7.2 Microsoft Entra ID (Azure AD) ? P0

De fleste danske og tyske kommuner k?rer M365. EIRA integrerer med SharePoint og Outlook ? disse forventer Entra-tokens.

| Aspekt | Detalje |
|--------|---------|
| Protokol | OIDC (prim?r), SAML 2.0 (legacy) |
| Flow | Authorization Code + PKCE |
| MFA | Entra Conditional Access ? EIRA l?ser `amr`/`acr` claims |
| Tokens | Access token til Graph API, SharePoint-, Outlook-adaptere |
| Roller | Entra-grupper ? EIRA roller via policy mapping |

**Typisk flow:**
1. Medarbejder logger ind med Microsoft (Entra + MFA)
2. EIRA modtager id_token med `oid`, `tid`, grupper
3. Daglige handlinger ? Entra-session er nok
4. "Godkend budget" ? step-up til MitID Erhverv / EUDI Wallet

### 7.3 Google Workspace ? P2

| Variant | Anvendelse | Assurance |
|---------|------------|-----------|
| **Google Workspace** | Organisationer med Google | `eid_low` med admin-MFA |
| **Google personlig** | Privat/BYOD | `session` ? ikke kommunal produktion |

Sj?ldnere i dansk/tysk offentlig sektor end Entra. Implement?r som connector.

### 7.4 Suver?nitet (Schrems II)

| Bekymring | EIRA-h?ndtering |
|-----------|-----------------|
| Data til US-cloud | Tokens caches lokalt; minimale API-kald |
| Entra EU | Anbefal EU data residency for kommuner |
| Fallback | Passkey + lokal IdP uden Microsoft/Google |

IdP-connectorer er **broer, ikke ejere** af identiteten.

### 7.5 Afgr?nsning

| Underst?ttes | Underst?ttes ikke |
|--------------|-------------------|
| Entra OIDC + tokens til adaptere | Entra som eneste id for offentlige handlinger |
| Google Workspace OIDC | Privat Google i kommunal produktion |
| SAML federation | Microsoft Authenticator som erstatning for EIRA Authenticator |

---

## 8. Country Pack: `dk-pack` (Danmark)

(Sammenfattet ? u?ndret fra v0.1)

| System | Rolle | Protokol |
|--------|-------|----------|
| AltID | National EUDI Wallet | OID4VP |
| MitID | Step-up, signering | OIDC |
| MitID Erhverv | Organisationsidentitet | Lokal IdP / IdM API |
| NemLog-in | Offentlig federation | OIDC |

---

## 9. Country Pack: `de-pack` (Tyskland)

(Sammenfattet ? u?ndret fra v0.1)

| System | Rolle | Protokol |
|--------|-------|----------|
| EUDI Wallet | National wallet (2027) | OID4VP + HAIP |
| BundID | B?rgerkonto, SSO-hub | OIDC |
| eID / AusweisApp | St?rk identitet | eID-Server |
| Wallet-Adapter | Kommunal anbindelse | IT-PLR standard |

---

## 10. EIRA Authenticator

Identitetsmotoren ? ikke en TOTP-klon. Brokering desktop ? wallet, step-up UI, passkeys, approval queue.

---

## 11. Sprint 1 pilot ? MINIMUM scope (beslutning)

Arkitekturen forbliver EUDI-first i dokumentation. **Implementering i Sprint 1 er Entra-first.**

| In scope (Sprint 1) | Deferred (efter pilot-feedback) |
|---------------------|--------------------------------|
| Entra OIDC login | OID4VP / OID4VCI |
| Session assurance | MitID Erhverv step-up |
| Passkey | `dk-pack`, `de-pack` |
| Intent Audit med session identity | Delegation-model |
| Step-up UI mock (blokering + forklaring) | SAML legacy IdP |
| Policy YAML l?ses og h?ndh?ves | Faktisk wallet-flow |

Se [EIRA_Strategic_Reality_Check_v0.1.md](EIRA_Strategic_Reality_Check_v0.1.md) §4.

---

## 12. Tidsplan (opdateret)

| Fase | Periode | Leverance |
|------|---------|-----------|
| **Fase 0** | Q3 2026 | OID4VP kerne, passkey, policy engine |
| **Fase 0b** | Q3 2026 | **Microsoft Entra ID connector (OIDC)** |
| **Fase 1** | Q4 2026 | dk-pack + de-pack sandboxes |
| **Fase 2** | H1 2027 | MitID Erhverv, BundID, SAML |
| **Fase 3** | H2 2027 | Produktion eID + Google Workspace connector |

---

## 10. Identity som epistemisk rod

Runtime-dokumentation beskriver ofte Identity som "lag 1.5" eller lag 4 i stacken. Det er **implementeringsplacering**.

**Epistemisk** er Identity roden i hele platformen:

```
                    Identity
                        │
        ┌───────────────┼───────────────┐
        │               │               │
   Object Graph    Capability        Trust
        │               │               │
        └───────────────┼───────────────┘
                        │
                   Reasoning → AI
```

| Komponent | Afhængighed af Identity |
|-----------|------------------------|
| Object Graph | Kanter fra Identity (`delegates_to`, `reports_to`) har `evidence.method: identity_grant` |
| Capability | Manifests scoped til org/rolle fra session |
| Trust | Step-up, delegation og "hvem handlede" |
| Intent / Journey | `actor_id`, assurance, `delegated_for` |
| Reasoning / AI | Traverserer graf vægtet af kant-confidence — starter med identity-verificerede stier |

**Beslutning:** Alle adapter-sync'ede relationer skal bære evidens (se [Object Graph v0.3](EIRA_Object_Graph_Specification_v0.3.md)). Identity-satte kanter har højeste confidence og `verified: true`.

---

## 13. Referencer

| Ressource | URL |
|-----------|-----|
| Microsoft Entra ID ? OIDC | learn.microsoft.com/entra/identity-platform |
| Google Workspace OIDC | developers.google.com/identity |
| eIDAS 2.0 / EUDI Wallet ARF | EU Digital Identity Wallet Dev Hub |
| DIGST ? AltID | digst.dk |
| BMI ? German EUDI Wallet | bmi.usercontent.opencode.de |
| MitID Erhverv ? Lokal IdP | mitid-erhverv.dk |

---

*EIRA Identity Strategy v0.2 ? Fortroligt udviklingsdokument*
