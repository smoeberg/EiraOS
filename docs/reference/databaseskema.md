# Databaseskemaet — én vej

**Besluttet i:** [udviklingsplan](../UDVIKLINGSPLAN.md) F1.10 (fundregister S-21, D-12).

EiraOS har én vej til databaseskemaet: **hvert modul, der ejer en tabel, opretter og opgraderer den selv, når det åbner databasen** (`init_db()` og de tilsvarende `_init_db`/`SCHEMA`-blokke). Der er ingen Alembic og intet separat migrationstrin.

## Hvorfor ikke Alembic

- Den installerede pakke har aldrig kørt Alembic. Daemons starter under systemd uden et migrationstrin, og `alembic` var hverken i `requirements.txt` eller i pakken. Kun CI og `debian/rules` installerede det.
- Alembic kendte kun to tabeller (`objects`, `audit_events`), mens koden har over tyve. Når CI kørte `alembic upgrade head` først, fik `audit_events` Alembics kolonner, og `CREATE TABLE IF NOT EXISTS` i `app/session_store.py` gjorde derefter ingenting: et andet skema i CI end på en maskine (skema-drift).
- Databaserne er SQLite-filer, som hver har én ejer-daemon og én tjenestebruger. Den daemon, der åbner filen, er det eneste sted, et skema kan opgraderes uden et ekstra trin under installation og opdatering.

## Reglerne

1. **Opret med `CREATE TABLE IF NOT EXISTS`** (og `CREATE INDEX IF NOT EXISTS`) i det modul, der ejer tabellen. Et andet modul læser eller skriver kun gennem ejermodulet.
2. **Opgradér additivt.** En ny kolonne tilføjes med `PRAGMA table_info` + `ALTER TABLE … ADD COLUMN`, med en standardværdi, så gamle rækker er gyldige. En kolonne, der ikke længere bruges, bliver stående (fx `sessions.consent_key`), indtil en særskilt oprydning med test fjerner den.
3. **Initialiseringen er idempotent.** At åbne den samme fil to gange, eller en fil fra en ældre version, giver samme skema som en ny fil. `tests/test_schema_one_path.py` tjekker det for app-databasen.
4. **En ændring, der ikke kan gøres additivt** (omdøbning, ændret type, ny primærnøgle, sletning af data), er en egen funktion i ejermodulet med en test, der starter fra den gamle form (som `_migrate_p0` og `_migrate_oidc` i `app/database.py`), og en linje i CHANGELOG.
5. **Hemmeligheder på disk fjernes ved opgradering** med `PRAGMA secure_delete=ON` (som samtykkenøglerne i `app/session_store.py`).

## Databaserne

| Fil på en installeret maskine | Miljøvariabel | Ejer (tjeneste) | Tabeller oprettes i |
|---|---|---|---|
| `/data/eira-app.db` | `EIRA_APP_DB` (`EIRA_DB_PATH` i tests) | `identityd`, `intentd` (gaten), `graphd`, `delegationd` | `app/database.py`, `app/session_store.py`, `app/gate/store.py`, `app/gate/executors.py`, `app/conversation/feed.py`, `app/auth/delegation.py`, `app/auth/consent_agent.py` |
| `/data/eira.db` | `EIRA_STATE_DB` | `stated` (Rust, `crates/eira-stated`) | `crates/eira-stated/src/lib.rs` |
| `/data/eira-fleet/inventory.db` | `EIRA_APP_DB` for `fleetd` | `fleetd` | `app/fleet/device_registry.py` |
| `/run/eira/consent-keys.db` (tmpfs, aldrig på disk) | `EIRA_CONSENT_KEY_DB` | `identityd` skriver; gaten og `delegationd` læser | `app/consent_keys.py` |
| Rettighedscachen (`/data/rights/`, JSON-filer, ikke SQL) | `EIRA_RIGHTS_DIR` | `eira-governance-agent` | `app/rights/cache.py` |

`app/core/store.py` og `app/core/policy_store.py` er biblioteker uden fast fil (standard `:memory:`); den, der giver dem en sti, ejer filen.
