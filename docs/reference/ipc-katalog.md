# IPC-katalog

**Genereret** af `scripts/ipc_catalog.py --write` fra daemons' egne registreringer. Ret ikke i hånden; CI fejler, hvis dokumentet ikke svarer til koden.

Hver metode har en adgangsklasse ([`app/ipc/access.py`](../../app/ipc/access.py)). Socket-gruppen `eira-clients` og IPC-tokenet er ikke en grænse mod desktop-brugeren; klasserne er.

| Klasse | Betydning |
|---|---|
| `read` | Læser kun. Enhver klient på socketen. |
| `daemon_write` | Ændrer tilstand. Kun EiraOS' egne tjenester (samme UID); serveren tjekker det. |
| `caller` | Handleren afgør ud fra kalderen fra kernen (`SO_PEERCRED`). |
| `signed` | Handleren tjekker et kryptografisk bevis i forespørgslen. |
| `refused` | Afviser altid; gammel vej, der skal gennem gaten. |
| `open_write` | **Kendt hul:** ændrer tilstand uden tjek. Lukkes af det nævnte plan-id. |

## `stated` — `/run/eira/stated.sock`

| Metode | Klasse | Bemærkning |
|---|---|---|
| `audit.append` | `daemon_write` |  |
| `audit.verify` | `read` |  |
| `health` | `read` |  |
| `state.append` | `daemon_write` |  |
| `state.get` | `read` |  |
| `state.get_by_hash` | `read` |  |
| `state.get_history` | `read` |  |
| `state.list` | `read` |  |
| `state.sync_pull` | `read` |  |
| `state.sync_push` | `daemon_write` |  |

## `identityd` — `/run/eira/identityd.sock`

| Metode | Klasse | Bemærkning |
|---|---|---|
| `health` | `read` |  |
| `identity.consent_agent_register` | `caller` |  |
| `identity.consent_key_claim` | `caller` |  |
| `identity.login_complete` | `caller` |  |
| `identity.login_start` | `caller` |  |
| `identity.logout` | `caller` |  |
| `identity.providers` | `read` |  |
| `identity.session` | `caller` |  |
| `identity.step_up` | `refused` |  |
| `identity.verify_production_certificate` | `daemon_write` |  |

## `fleetd` — `/run/eira/fleetd.sock`

| Metode | Klasse | Bemærkning |
|---|---|---|
| `fleet.device.enroll` | `signed` |  |
| `fleet.device.revoke` | `caller` |  |
| `fleet.pairing.create` | `caller` |  |
| `health` | `read` |  |
| `sync.handshake` | `signed` |  |
| `sync.push_blocks` | `signed` |  |
| `sync.request_blocks` | `signed` |  |

## `veritasd` — `/run/eira/veritasd.sock`

| Metode | Klasse | Bemærkning |
|---|---|---|
| `health` | `read` |  |
| `veritas.evaluate` | `read` |  |
| `veritas.process_evidence` | `read` |  |

## `intentd` — `/run/eira/intentd.sock`

| Metode | Klasse | Bemærkning |
|---|---|---|
| `capability.list` | `read` |  |
| `conversation.awaiting` | `caller` |  |
| `conversation.events` | `caller` |  |
| `conversation.list` | `caller` |  |
| `conversation.members` | `caller` |  |
| `dashboard.get` | `caller` |  |
| `events.since` | `caller` |  |
| `gate.capabilities` | `caller` |  |
| `gate.confirm` | `caller` |  |
| `gate.consent` | `caller` |  |
| `gate.propose` | `caller` |  |
| `gate.rendering` | `caller` |  |
| `gate.status` | `caller` |  |
| `health` | `read` |  |
| `intent.confirm` | `refused` |  |
| `intent.execute` | `refused` |  |
| `journey.advance` | `refused` |  |
| `journey.get` | `read` |  |
| `journey.list` | `read` |  |
| `presentation.mode_get` | `caller` |  |
| `presentation.mode_set` | `caller` |  |

## `graphd` — `/run/eira/graphd.sock`

| Metode | Klasse | Bemærkning |
|---|---|---|
| `graph.context` | `read` |  |
| `graph.provenance.trace` | `read` |  |
| `graph.spatial_snapshot` | `read` |  |
| `graph.temporal_query` | `read` |  |
| `health` | `read` |  |

## `delegationd` — `/run/eira/delegationd.sock`

| Metode | Klasse | Bemærkning |
|---|---|---|
| `delegation.check` | `caller` |  |
| `delegation.create` | `caller` |  |
| `delegation.list` | `caller` |  |
| `delegation.proposal` | `caller` |  |
| `delegation.propose` | `caller` |  |
| `delegation.revoke` | `caller` |  |
| `health` | `read` |  |

## `modeld` — `/run/eira-model/modeld.sock`

| Metode | Klasse | Bemærkning |
|---|---|---|
| `health` | `read` |  |
| `model.prepare` | `caller` |  |
