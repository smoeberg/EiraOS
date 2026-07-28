---
contract_id: CP-OIDC-001
version: 1.0.0
owner: programmer-a
status: active
schema: null
prototype_ref: ../../prototype/phase1/app/auth/oidc.py
depends_on: [CP-SESSION-001]
forbidden:
  - global logged_in_user
  - session state outside SQLite
  - storing raw id_token in audit log
---

# CP-OIDC-001 — Enterprise OIDC login (Azure AD / Entra)

## AGENT PROMPT

Implementer kontrakt **CP-OIDC-001** for EIRA phase1 Enterprise SSO.

**Kontekst:** Kommuner logger ind via Entra ID (OIDC). Efter login oprettes/opdateres en `sessions`-række. Alle login hændelser auditeres (NIS2).

**Din opgave:**
1. `app/auth/oidc.py` — OIDC config fra env, mock login (dev), claim mapping
2. `app/auth/audit.py` — `auth.login.success` / `auth.login.failure` i `audit_events`
3. HTTP: `GET /v1/auth/oidc/login`, `GET /v1/auth/oidc/callback`, `POST /v1/auth/oidc/mock-login`, `GET /v1/auth/oidc/config`
4. Map claims → session: `actor_id` (email/sub), `actor_name`, `org_unit` (tenant/org), `assurance_level=idp_authenticated`
5. Returnér `session_id` til klient — brug header `X-EIRA-Session-Id` herefter

**Invariants:**
1. Login opretter session via `session_store` — ingen parallel identity state
2. Audit logger kun metadata (actor_id hash ok, ikke fuld token)
3. Fejlet login auditeres uden at oprette session

**Out of scope (prototype):**
- JWT signatur validering mod Entra JWKS (P2)
- SAML, token refresh, logout

**Acceptance:**
- GIVEN mock login WHEN success THEN session + audit auth.login.success
- GIVEN mock login uden email WHEN fail THEN audit auth.login.failure
- GIVEN to sessions via OIDC WHEN step_up på A THEN B uændret (CP-SESSION-001)

--- END PROMPT ---
