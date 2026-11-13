# EIRA-CONVERSATION-1.0 — Samtalelaget og hændelsesstrømmen

**Status:** Udkast, bindende som implementeringsmål. Implementeret i `app/conversation/` (november 2026).
**Afhænger af:** [GATE-KERNEL-1.0](GATE-KERNEL-1.0.md), [EDP-1.0](EDP-1.0.md), [EIRA-RIGHTS-SET-1.0](EIRA-RIGHTS-SET-1.0.md) §6.
**Input:** [Situation-layout november 2026](../docs/design/situation-layout-2026-11/README.md) §3 (hændelser og kilder).

## 1. Formål

Explorer viser opmærksomhed, ikke apps. Skærmene skal derfor læse fra én kilde: de hændelser, gaten har optaget, i de samtaler brugeren er en del af. Denne spec definerer:

1. **Medlemskab:** hvem der må handle i en samtale, og hvem der må se den.
2. **Hændelsesstrømmen:** hvordan Explorer læser hændelser, uden at kunne ændre noget.

Samtalen hører til *objektet* (`conversation_id` er en objektreference, EDP §4.1), ikke til en kanal eller en app.

## 2. Grundregler

1. **Medlemskab er samtaledata, ikke en rettighed** (RIGHTS-SET §6). Rettigheder kommer fra Fleet-sættet; medlemskab kommer fra samtalen selv.
2. **Medlemskab skrives kun af samtalelaget**, i samme transaktion som gaten optager en hændelse. Ingen IPC-metode tilføjer, ændrer eller fjerner et medlem.
3. **Strømmen er kun læsning.** Den viser, hvad der er optaget. Optaget er ikke leveret: `delivery` er `pending`, indtil en modtager har kvitteret.
4. **Hvad man ikke må se, findes ikke.** En samtale, brugeren ikke er medlem af, giver samme svar som en, der ikke eksisterer.

## 3. Medlemskab

### 3.1 Roller

| Rolle i `gate_members` | Kan se | Kan handle |
|---|---|---|
| `member` | ja | ja (lag 6 afgør hvad) |
| `observer` | ja | nej |

Kun verificerede lokale identiteter (`did:eira:…`) kan være medlemmer. En ekstern adresse (`external:sms:…`) er en modtager, ikke en der logger ind her. Deltagere med rollen `service` bliver aldrig medlemmer.

### 3.2 Hvem må handle (lag 4, domæne)

For en handling i samtalen *C* fra identiteten *P*:

- *P* er `member` af *C* → i domænet.
- *P* er `observer` af *C* → `REJECT E_POLICY` ("observer may not act").
- *C* har medlemmer, og *P* er ikke blandt dem → `REJECT E_POLICY` ("not a member").
- *C* har ingen medlemmer endnu → *P* må **åbne** samtalen, hvis *P* står som handlende deltager (`role: member`) i hændelsen. Om *P* overhovedet må handle på scopet, afgør lag 6 ud fra Fleet-sættet.

`device:local` er ikke en samtale. Dets domæne er mindst én gyldig grant på `device:local` for *P* (RIGHTS-SET §6); hvilken handling der er tilladt, afgør lag 6.

### 3.3 Hvordan medlemskab opstår

Når executoren optager en samtalehændelse, sker tre ting i **én** SQLite-transaktion (`BEGIN IMMEDIATE`):

1. Domænet (§3.2) kontrolleres igen. Har en anden åbnet samtalen siden lag 4, skrives intet, og handlingen går tilbage til `pending` (`E_EXECUTOR_UNAVAILABLE`); en ny bekræftelse afvises i lag 4.
2. Hændelsen tilføjes `conversation_feed` (append-only, triggere afviser `UPDATE` og `DELETE`).
3. Forfatteren og hver `did:eira`-deltager med rollen `member` eller `observer` bliver medlem med den rolle, hvis de ikke allerede er.

Outbox-rækken skrives i samme transaktion. Enten findes alle tre, eller ingen af dem; crash-recovery kan derfor stadig afgøre udfaldet ud fra outbox'en alene.

### 3.4 Medlemskab vokser kun

At adressere en `observer` som `member` forfremmer. Intet i en hændelse kan nedgradere eller fjerne et medlem.

**Åbent:** at forlade eller fjerne fra en samtale. Det kræver en ny handlingstype (EDP §3) med eget samtykke og egen policy og er bevidst ikke med i 1.0.

### 3.5 Kendte begrænsninger

- **Squatting:** Den første, der optager en hændelse i en tom samtale, bliver medlem. Det er begrænset af Fleet-sættet (scope pr. gruppe), ikke af samtalelaget. I standardsættet har enhver indlogget bruger `obj:sag:*`, så på en privat maskine med flere brugere kan én bruger åbne en sag før en anden. Samtaler bør derfor fremover oprettes med en id fra objektet (graphd), ikke en id, brugeren vælger.
- **Invitation ved adressering:** Et medlem kan gøre enhver lokal identitet til medlem ved at adressere den, som med cc i e-mail.
- **Modellen kan ikke læse strømmen.** Den kræver et menneske i en autentificeret session bundet til kalderens UID. Modellen får først adgang med "på vegne af"-delegationen (GATE-KERNEL bilag A pkt. 1).

## 4. Hændelsesstrømmen

### 4.1 Hændelse

```json
{
  "seq": 17,
  "event_id": "dlg-0001",
  "conversation_id": "obj:sag:42",
  "type": "commitment_proposed",
  "author": "did:eira:entra.…",
  "participants": [{"identity": "did:eira:entra.…", "role": "member"}],
  "content": {"what": "Møde om budgettet", "when": "2026-11-12T10:00:00+01:00"},
  "temporal": {"created_at": "…", "valid_from": null, "supersedes": null},
  "ref_id": null,
  "recorded_at": "2026-11-10T07:01:02.345Z",
  "delivery": "pending"
}
```

`author` er gatens handlende identitet (`gate_actions.actor_identity`), ikke et felt fra konvolutten. `ref_id` er `commitment_id` for svar.

### 4.2 Cursor og historik

- `seq` er global og stiger strengt. En klient gemmer den seneste `cursor` og spørger efter alt derefter.
- Cursoren flytter sig også forbi hændelser, brugeren ikke kan se. Klienten lærer aldrig, hvor de ligger, kun at der intet er til den.
- Et nyt medlem ser hele samtalens historik (`conversation.events`): samtalen hører til objektet, ikke til tidspunktet, hvor nogen blev tilføjet.

### 4.3 Afventer

`conversation.awaiting` er "venter på dig" i layoutet:

- `commitments`: `commitment_proposed`, hvor brugeren er handlende deltager og ikke forfatter, og som brugeren endnu ikke har accepteret eller afvist.
- `decisions`: gate-handlinger, der står `pending` for brugeren, fx et forslag fra modellen, med præcis den tekst, brugeren vil give samtykke til.

## 5. IPC (intentd)

Alle metoder ligger på `intentd.sock`, fordi gaten og dens database ligger dér. De kan flyttes til en egen pakket daemon med egen procesidentitet senere. Prototypen `presenced` er fjernet (UDVIKLINGSPLAN F1.2).

| Metode | Parametre | Svar |
|---|---|---|
| `events.since` | `session_id`, `cursor` (≥ 0), `limit` (≤ 200), `wait_ms` | `{events, cursor, more}` |
| `conversation.list` | `session_id` | samtaler med rolle, seneste `seq`, antal medlemmer |
| `conversation.events` | `session_id`, `conversation_id`, `before?`, `limit?` | historik, nyeste først |
| `conversation.members` | `session_id`, `conversation_id` | medlemmer og roller |
| `conversation.awaiting` | `session_id` | `{commitments, decisions}` (§4.3) |

### 5.1 Adgang

- Kalderen kommer fra forbindelsen (`SO_PEERCRED`). Sessionen skal være autentificeret, uudløbet og bundet til kalderens UID, og kalderen må ikke være modellen. Ellers `-32041 E_NO_SESSION`.
- En samtale, kalderen ikke kan se, og en, der ikke findes: begge `-32042 unknown conversation`.
- Læsninger auditeres ikke i gatens kæde; de ændrer intet.

### 5.2 Long-poll

`wait_ms > 0` og ingen nye hændelser: svaret venter, til intentd optager en hændelse, dog højst 20 sekunder (`MAX_WAIT_S`). Et wake-up for en hændelse, kalderen ikke kan se, giver en tom side med flyttet cursor. Appen bruger 3 sekunder (`LONG_POLL_MS`), så den holder sig under IPC-timeouten på 5 sekunder. JSON-RPC forbliver request/response; der er ingen push-framing.

## 6. Acceptkriterier → tests

| Krav | Test (`tests/test_conversation_layer.py`) |
|---|---|
| Ingen medlemmer ved installation; første hændelse åbner | `test_an_installed_machine_starts_with_no_members_and_the_first_event_opens_the_conversation` |
| Andre kan ikke handle | `test_others_cannot_act_in_a_conversation_they_are_not_part_of` |
| Adresseret deltager bliver medlem og kan svare | `test_an_addressed_participant_joins_and_can_answer` |
| Observatør ser, handler ikke | `test_an_observer_sees_but_cannot_act` |
| Medlemskab vokser kun | `test_membership_only_grows` |
| To kan ikke åbne samme samtale | `test_two_users_cannot_both_open_the_same_new_conversation` |
| Atomar skrivning | `test_feed_outbox_and_membership_are_written_together_or_not_at_all` |
| Append-only | `test_the_feed_is_append_only` |
| Kun synlige samtaler; cursor afslører intet | `test_each_user_sees_only_conversations_they_can_see` |
| Historik for nye medlemmer | `test_a_new_member_sees_the_history_of_the_object` |
| Kun læsninger eksponeret | `test_only_reads_are_exposed` |
| Egen session, ikke modellen | `test_the_stream_needs_the_user_s_own_session` |
| Skjult = manglende | `test_a_hidden_conversation_looks_like_a_missing_one` |
| `device:local` uden medlemskab | `tests/test_gate_system.py::test_device_actions_need_no_conversation_membership` |
| Installeret | VM-check `events-need-session` |

**Mutationstjek:** Hver af disse er fjernet én ad gangen, og testene fejlede hver gang: gentjek af domænet i transaktionen, observatør-afvisningen, medlemsfilteret i strømmen, og kravet om en menneskelig session.
