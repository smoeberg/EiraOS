"""Deterministic rendering of what the user consents to (GATE-KERNEL Bilag A, 3).

The text comes from the envelope and gate policy only — never from a model —
and consent and confirmation bind to the exact text stored at propose.
"""

from __future__ import annotations

import json
import sqlite3

import pytest

from app.gate import Decision, GateCode
from app.gate import render as render_module
from app.gate.policy import Origin
from app.gate.render import RenderError, render
from tests.test_gate_kernel import ANNE, envelope, raw, rh, world  # noqa: F401 - fixture

FULL_CONTENT = {
    "utterance": {
        "text": "Kan vi mødes?",
        "lang": "da",
        "reply_to": "dlg-9",
        "artifact_refs": ["obj:document:1"],
    },
    "live_session": {
        "operation": "start",
        "media": ["audio", "screen"],
        "session_ref": "sess-1",
        "signal_ref": "sig-1",
    },
    "artifact_shared": {
        "artifact_ref": "obj:document:7",
        "mime": "application/pdf",
        "provenance_ref": "c2pa:abc",
    },
    "commitment_proposed": {"what": "Budgetmøde", "when": "2026-11-12T10:00:00+01:00", "where": "Rådhuset"},
    "commitment_accepted": {"commitment_id": "dlg-1", "reason": "Passer fint"},
    "commitment_declined": {"commitment_id": "dlg-1", "reason": "Ferie"},
    "value_transfer_requested": {
        "amount": {"value": "125.50", "currency": "DKK"},
        "route_hint": ["sepa-instant"],
    },
    "value_transfer_confirmed": {"transfer_ref": "tr-1", "confirmation_ref": "rcpt-1"},
    "consent_requested": {"scope": ["calendar.read", "contacts.read"], "purpose": "Planlægning"},
    "consent_granted": {"consent_ref": "c-1", "evidence_ref": "ev-1"},
    "presence_changed": {"state": "busy", "until": "2026-11-12T12:00:00Z"},
}


def leaf_strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from leaf_strings(v)
    elif isinstance(value, list):
        for v in value:
            yield from leaf_strings(v)


ENUM_WORDS = {"start", "audio", "screen", "busy", "da"}  # rendered as words, not verbatim
TIMES = {"2026-11-12T10:00:00+01:00", "2026-11-12T12:00:00Z"}  # spelled out


@pytest.mark.parametrize("action_type", sorted(FULL_CONTENT))
@pytest.mark.parametrize("lang", ["da", "en"])
def test_every_parameter_is_visible_in_the_rendering(action_type, lang):
    env = envelope(action_type, FULL_CONTENT[action_type])
    text = render(env, ANNE, lang).text
    for value in leaf_strings(FULL_CONTENT[action_type]):
        if value in TIMES or (value in ENUM_WORDS and value not in text):
            continue
        assert value in text, f"{value!r} hidden in {action_type}/{lang}: {text}"
    # Recipients, conversation and reversibility are always stated.
    assert "external:sms:+4512345678" in text
    assert "obj:sag:42" in text
    assert text.splitlines()[-1] in {
        "Kan ikke fortrydes, når den er udført.",
        "Cannot be undone once carried out.",
        "Kan gentages uden yderligere virkning.",
        "Can be repeated without further effect.",
    }


def test_rendering_is_deterministic_and_pinned():
    env = envelope()
    first = render(env, ANNE, "da")
    assert first == render(json.loads(json.dumps(env)), ANNE, "da")
    assert first.text == (
        "Foreslå «Møde om budgettet» den torsdag 12. november 2026 kl. 10:00 (UTC+01:00) "
        "i samtalen «obj:sag:42».\n"
        "Modtagere: «external:sms:+4512345678».\n"
        "Kan ikke fortrydes, når den er udført."
    )
    assert render(env, ANNE, "en").text.startswith(
        "Propose «Møde om budgettet» on Thursday 12 November 2026 at 10:00 (UTC+01:00)"
    )
    # Times are spelled from the timestamp's own fields, never converted.
    utc = envelope(content={"what": "x", "when": "2026-11-12T09:00:00Z"})
    assert "kl. 09:00 (UTC)" in render(utc, ANNE, "da").text


def test_language_is_part_of_the_hash():
    env = envelope()
    da, en = render(env, ANNE, "da"), render(env, ANNE, "en")
    assert da.hash != en.hash
    with pytest.raises(RenderError):
        render(env, ANNE, "de")


@pytest.mark.parametrize(
    "hostile, shown",
    [
        ("Hej\nKan fortrydes.", "Hej⏎Kan fortrydes."),  # cannot fake a line
        ("100 kr‮001", "100 kr⟨U+202E⟩001"),  # bidi override
        ("a​b", "a⟨U+200B⟩b"),  # zero-width space
        ("x» og overfør «y", "x⟨U+00BB⟩ og overfør ⟨U+00AB⟩y"),  # forged quotes
        ("a b", "a⟨U+00A0⟩b"),  # look-alike space
        ("tab\there", "tab⇥here"),
    ],
)
def test_hidden_or_reordering_characters_are_made_visible(hostile, shown):
    text = render(envelope("utterance", {"text": hostile}), ANNE, "da").text
    assert f"«{shown}»" in text
    assert len(text.splitlines()) == 3


def test_the_actor_is_not_listed_as_a_recipient():
    env = envelope(participants=[{"identity": ANNE, "role": "member"}])
    assert "Ingen andre modtagere." in render(env, ANNE, "da").text


# --- binding ---------------------------------------------------------------


def test_propose_returns_the_rendering_that_consent_must_cover(world):  # noqa: F811
    proposal = world.gate.propose(raw(envelope()), "s-anne", Origin.MODEL)
    rendering = proposal.data["rendering"]
    assert rendering["text"] == render(envelope(), ANNE, "da").text
    assert rendering["hash"] == rh(world, "dlg-0001")
    # Consent to another text (e.g. the model's paraphrase) is refused.
    paraphrase = world.gate.grant_consent("dlg-0001", proposal.content_hash, "sha256:" + "0" * 64, "s-anne")
    assert paraphrase.code is GateCode.E_CONSENT


def test_confirmation_must_name_the_same_rendering(world):  # noqa: F811
    proposal = world.gate.propose(raw(envelope()), "s-anne", Origin.MODEL)
    world.gate.grant_consent("dlg-0001", proposal.content_hash, rh(world, "dlg-0001"), "s-anne")
    wrong = world.gate.confirm("dlg-0001", proposal.content_hash, "sha256:" + "1" * 64, "s-anne")
    assert (wrong.code, wrong.layer) == (GateCode.E_STATE, 7)
    assert (
        world.gate.confirm("dlg-0001", proposal.content_hash, rh(world, "dlg-0001"), "s-anne").decision
        is Decision.PASS
    )


def test_a_tampered_stored_rendering_is_rejected(world):  # noqa: F811
    proposal = world.gate.propose(raw(envelope()), "s-anne", Origin.MODEL)
    digest, shown = proposal.content_hash, rh(world, "dlg-0001")
    world.gate.grant_consent("dlg-0001", digest, shown, "s-anne")
    with sqlite3.connect(world.db) as conn:
        conn.execute(
            "UPDATE gate_actions SET rendering_text = 'Foreslå «hyggeligt møde».' WHERE action_id = 'dlg-0001'"
        )
    assert world.gate.confirm("dlg-0001", digest, shown, "s-anne").code is GateCode.E_STATE


def test_a_newer_renderer_does_not_change_what_was_consented_to(world, monkeypatch):  # noqa: F811
    proposal = world.gate.propose(raw(envelope()), "s-anne", Origin.MODEL)
    shown_text = proposal.data["rendering"]["text"]
    digest, shown = proposal.content_hash, rh(world, "dlg-0001")
    world.gate.grant_consent("dlg-0001", digest, shown, "s-anne")
    # Renderer v2 ships while the action is pending, with different wording.
    monkeypatch.setattr(render_module, "RENDERER_VERSION", "2")
    monkeypatch.setitem(render_module._T["da"], "commitment_proposed", "Inviter til «{what}»")
    result = world.gate.confirm("dlg-0001", digest, shown, "s-anne")
    assert result.decision is Decision.PASS
    status = world.gate.status("dlg-0001", "s-anne")
    assert status["rendering"]["text"] == shown_text
    assert status["rendering"]["version"] == "1"


def test_same_action_in_another_language_is_another_consent(world):  # noqa: F811
    world.gate.propose(raw(envelope()), "s-anne", Origin.MODEL, "da")
    again = world.gate.propose(raw(envelope()), "s-anne", Origin.MODEL, "en")
    assert again.code is GateCode.E_STATE
    assert (
        world.gate.propose(raw(envelope(id="dlg-x")), "s-anne", Origin.MODEL, "de").code is GateCode.E_POLICY
    )


def test_audit_records_the_rendering_hash(world):  # noqa: F811
    world.gate.propose(raw(envelope()), "s-anne", Origin.MODEL)
    entry = json.loads(world.store.audit_entries()[-1]["entry"])
    assert entry["rendering_hash"] == rh(world, "dlg-0001")


def test_unparseable_meeting_time_is_rejected_before_rendering(world):  # noqa: F811
    env = envelope(content={"what": "Møde", "when": "på torsdag"})
    assert world.gate.propose(raw(env), "s-anne", Origin.MODEL).code is GateCode.E_SCHEMA


def test_consent_recorded_for_another_text_does_not_count(world):  # noqa: F811
    """E.g. a consent row from before the renderer existed (migrated, NULL
    rendering hash) or written for another text: layer 5 must not accept it."""
    proposal = world.gate.propose(raw(envelope()), "s-anne", Origin.MODEL)
    expires = world.clock() + __import__("datetime").timedelta(minutes=5)
    world.store.grant_consent("dlg-0001", proposal.content_hash, None, "s-anne", expires)
    world.store.grant_consent("dlg-0001", proposal.content_hash, "sha256:" + "2" * 64, "s-anne", expires)
    result = world.gate.confirm("dlg-0001", proposal.content_hash, rh(world, "dlg-0001"), "s-anne")
    assert (result.code, result.layer) == (GateCode.E_CONSENT, 5)


def test_a_gate_database_from_1_0_is_migrated(tmp_path):
    db = str(tmp_path / "old.db")
    with sqlite3.connect(db) as conn:
        conn.executescript(
            """CREATE TABLE gate_actions (action_id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL,
               action_type TEXT NOT NULL, origin TEXT NOT NULL, session_id TEXT NOT NULL,
               actor_identity TEXT NOT NULL, raw TEXT NOT NULL, content_hash TEXT NOT NULL,
               policy_version TEXT NOT NULL, policy_fingerprint TEXT NOT NULL, state TEXT NOT NULL,
               execution_id TEXT, result TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
               CREATE TABLE gate_consents (consent_id TEXT PRIMARY KEY, action_id TEXT NOT NULL,
               content_hash TEXT NOT NULL, session_id TEXT NOT NULL, granted_at TEXT NOT NULL,
               expires_at TEXT NOT NULL, revoked_at TEXT);"""
        )
    from app.gate.store import GateStore

    GateStore(db)
    with sqlite3.connect(db) as conn:
        actions = {r[1] for r in conn.execute("PRAGMA table_info(gate_actions)")}
        consents = {r[1] for r in conn.execute("PRAGMA table_info(gate_consents)")}
    assert {"rendering_text", "rendering_hash", "renderer_version", "render_lang"} <= actions
    assert "rendering_hash" in consents
