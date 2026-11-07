"""Deterministisk gengivelse af det, brugeren samtykker til (GATE-KERNEL bilag A, punkt 3).

Rendereren læser kun den validerede konvolut og gatens egen policy, aldrig
modellen. Samme konvolut, version og sprog giver altid samme tekst, byte for
byte. Teksten gemmes sammen med handlingen ved ``propose``. Samtykke og
bekræftelse binder til dens hash, så en revision kan genskabe præcis det,
brugeren så, også efter at rendereren har fået en ny version.

Alt brugerleveret indhold sættes i «…». Usynlige tegn, retningsstyring
(bidi-overrides, nul-bredde-tegn osv.), særlige mellemrum og rendererens egne
afgrænsere vises som ⟨U+XXXX⟩, og linjeskift som ⏎. Så kan en tekst ikke se ud
til at sige noget andet, end den gør, eller forfalske en linje i gengivelsen.
"""

from __future__ import annotations

import hashlib
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.gate.policy import Reversibility, policy_for

RENDERER_VERSION = "1"
LANGUAGES = ("da", "en")

_DA_MONTHS = (
    "januar", "februar", "marts", "april", "maj", "juni",
    "juli", "august", "september", "oktober", "november", "december",
)  # fmt: skip
_DA_DAYS = ("mandag", "tirsdag", "onsdag", "torsdag", "fredag", "lørdag", "søndag")
_EN_MONTHS = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)  # fmt: skip
_EN_DAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")

_T = {
    "da": {
        "utterance": "Send beskeden «{text}»",
        "reply": " som svar på {reply_to}",
        "artifacts": " med vedhæftede referencer {refs}",
        "commitment_proposed": "Foreslå «{what}»",
        "when": " den {when}",
        "where": " sted «{where}»",
        "commitment_accepted": "Acceptér forslaget {commitment_id}",
        "commitment_declined": "Afslå forslaget {commitment_id}",
        "reason": " med begrundelsen «{reason}»",
        "artifact_shared": "Del {artifact_ref}",
        "mime": " ({mime})",
        "provenance": " med oprindelsesreference {provenance_ref}",
        "live_session": {
            "start": "Start et opkald",
            "join": "Deltag i opkaldet",
            "end": "Afslut opkaldet",
            "reject": "Afvis opkaldet",
        },
        "media": " med {media}",
        "session_ref": " ({session_ref})",
        "signal_ref": " signal {signal_ref}",
        "value_transfer_requested": "Anmod om en betaling på {value} {currency}",
        "route_hint": " foreslået betalingsvej {routes}",
        "value_transfer_confirmed": "Registrér bekræftet betaling {transfer_ref}",
        "confirmation_ref": " med kvittering {confirmation_ref}",
        "consent_requested": "Bed om samtykke til {scope} med formålet «{purpose}»",
        "consent_granted": "Giv samtykke {consent_ref}",
        "evidence_ref": " dokumenteret ved {evidence_ref}",
        "presence_changed": "Sæt din status til {state}",
        "until": " indtil {until}",
        "states": {
            "available": "tilgængelig",
            "busy": "optaget",
            "away": "væk",
            "offline": "offline",
            "unknown": "ukendt",
        },
        "media_names": {"audio": "lyd", "video": "video", "screen": "skærmdeling"},
        "in": "i samtalen {conversation}",
        "to": "Modtagere: {recipients}.",
        "nobody": "Ingen andre modtagere.",
        "valid_from": "Gælder fra {valid_from}.",
        "irreversible": "Kan ikke fortrydes, når den er udført.",
        "idempotent": "Kan gentages uden yderligere virkning.",
        "compensable": "Kan rulles tilbage med en kompenserende handling.",
        "and": " og ",
        "at": "kl.",
        "observer": "observatør",
        "service": "tjeneste",
    },
    "en": {
        "utterance": "Send the message «{text}»",
        "reply": " as a reply to {reply_to}",
        "artifacts": " with attached references {refs}",
        "commitment_proposed": "Propose «{what}»",
        "when": " on {when}",
        "where": " at «{where}»",
        "commitment_accepted": "Accept the proposal {commitment_id}",
        "commitment_declined": "Decline the proposal {commitment_id}",
        "reason": " giving the reason «{reason}»",
        "artifact_shared": "Share {artifact_ref}",
        "mime": " ({mime})",
        "provenance": " with provenance reference {provenance_ref}",
        "live_session": {
            "start": "Start a call",
            "join": "Join the call",
            "end": "End the call",
            "reject": "Reject the call",
        },
        "media": " with {media}",
        "session_ref": " ({session_ref})",
        "signal_ref": " signal {signal_ref}",
        "value_transfer_requested": "Request a payment of {value} {currency}",
        "route_hint": " suggested payment route {routes}",
        "value_transfer_confirmed": "Record confirmed payment {transfer_ref}",
        "confirmation_ref": " with receipt {confirmation_ref}",
        "consent_requested": "Ask for consent to {scope} for the purpose «{purpose}»",
        "consent_granted": "Grant consent {consent_ref}",
        "evidence_ref": " evidenced by {evidence_ref}",
        "presence_changed": "Set your status to {state}",
        "until": " until {until}",
        "states": {
            "available": "available",
            "busy": "busy",
            "away": "away",
            "offline": "offline",
            "unknown": "unknown",
        },
        "media_names": {"audio": "audio", "video": "video", "screen": "screen sharing"},
        "in": "in the conversation {conversation}",
        "to": "Recipients: {recipients}.",
        "nobody": "No other recipients.",
        "valid_from": "Takes effect from {valid_from}.",
        "irreversible": "Cannot be undone once carried out.",
        "idempotent": "Can be repeated without further effect.",
        "compensable": "Can be rolled back with a compensating action.",
        "and": " and ",
        "at": "at",
        "observer": "observer",
        "service": "service",
    },
}


class RenderError(ValueError):
    pass


@dataclass(frozen=True)
class Rendering:
    text: str
    lang: str
    version: str
    hash: str

    def as_dict(self) -> dict[str, str]:
        return {"text": self.text, "lang": self.lang, "version": self.version, "hash": self.hash}


def rendering_hash(text: str, lang: str, version: str) -> str:
    material = f"eira-render\x00{version}\x00{lang}\x00{text}".encode()
    return "sha256:" + hashlib.sha256(material).hexdigest()


def _visible(value: str) -> str:
    """Make every character that could hide or reorder text visible."""
    out = []
    for char in value:
        category = unicodedata.category(char)
        if char == "\n":
            # A line break could fake an extra line ("Kan fortrydes."): show it.
            out.append("⏎")
        elif char == "\t":
            out.append("⇥")
        elif char in "«»⏎⇥⟨⟩":
            # Our own delimiters and markers cannot be forged from inside.
            out.append(f"⟨U+{ord(char):04X}⟩")
        elif category in {"Cc", "Cf", "Co", "Cn", "Zl", "Zp", "Zs"} and char != " ":
            out.append(f"⟨U+{ord(char):04X}⟩")
        else:
            out.append(char)
    return "".join(out)


def _q(value: str) -> str:
    return _visible(value)


def _ref(value: str) -> str:
    return f"«{_visible(value)}»"


def _list(values: list[str], lang: str, *, wrap=_ref) -> str:
    items = [wrap(v) for v in values]
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + _T[lang]["and"] + items[-1]


def _time(value: str, lang: str) -> str:
    """Spelled out from the timestamp's own fields; never converted to
    another timezone, so the text cannot drift with the machine's settings."""
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return _ref(value)
    if moment.tzinfo is None:
        return _ref(value)
    offset = moment.strftime("%z")
    offset = "UTC" if offset == "+0000" else f"UTC{offset[:3]}:{offset[3:]}"
    clock = f"{moment.hour:02d}:{moment.minute:02d}"
    if lang == "da":
        day = _DA_DAYS[moment.weekday()]
        month = _DA_MONTHS[moment.month - 1]
        return f"{day} {moment.day}. {month} {moment.year} {_T['da']['at']} {clock} ({offset})"
    day = _EN_DAYS[moment.weekday()]
    month = _EN_MONTHS[moment.month - 1]
    return f"{day} {moment.day} {month} {moment.year} {_T['en']['at']} {clock} ({offset})"


def _sentence(action_type: str, content: dict[str, Any], lang: str) -> str:
    t = _T[lang]
    c = content
    if action_type == "utterance":
        s = t["utterance"].format(text=_q(c["text"]))
        if "reply_to" in c:
            s += t["reply"].format(reply_to=_ref(c["reply_to"]))
        if c.get("artifact_refs"):
            s += t["artifacts"].format(refs=_list(c["artifact_refs"], lang))
        if "lang" in c:
            s += f" [{_visible(c['lang'])}]"
        return s
    if action_type == "commitment_proposed":
        s = t["commitment_proposed"].format(what=_q(c["what"]))
        if "when" in c:
            s += t["when"].format(when=_time(c["when"], lang))
        if "where" in c:
            s += t["where"].format(where=_q(c["where"]))
        return s
    if action_type in ("commitment_accepted", "commitment_declined"):
        s = t[action_type].format(commitment_id=_ref(c["commitment_id"]))
        if "reason" in c:
            s += t["reason"].format(reason=_q(c["reason"]))
        return s
    if action_type == "artifact_shared":
        s = t["artifact_shared"].format(artifact_ref=_ref(c["artifact_ref"]))
        if "mime" in c:
            s += t["mime"].format(mime=_visible(c["mime"]))
        if "provenance_ref" in c:
            s += t["provenance"].format(provenance_ref=_ref(c["provenance_ref"]))
        return s
    if action_type == "live_session":
        s = t["live_session"][c["operation"]]
        if c.get("media"):
            s += t["media"].format(media=_list(c["media"], lang, wrap=lambda m: t["media_names"][m]))
        if "session_ref" in c:
            s += t["session_ref"].format(session_ref=_ref(c["session_ref"]))
        if "signal_ref" in c:
            s += t["signal_ref"].format(signal_ref=_ref(c["signal_ref"]))
        return s
    if action_type == "value_transfer_requested":
        amount = c["amount"]
        s = t["value_transfer_requested"].format(value=amount["value"], currency=amount["currency"])
        if c.get("route_hint"):
            s += t["route_hint"].format(routes=_list(c["route_hint"], lang))
        return s
    if action_type == "value_transfer_confirmed":
        s = t["value_transfer_confirmed"].format(transfer_ref=_ref(c["transfer_ref"]))
        if "confirmation_ref" in c:
            s += t["confirmation_ref"].format(confirmation_ref=_ref(c["confirmation_ref"]))
        return s
    if action_type == "consent_requested":
        return t["consent_requested"].format(scope=_list(c["scope"], lang), purpose=_q(c["purpose"]))
    if action_type == "consent_granted":
        s = t["consent_granted"].format(consent_ref=_ref(c["consent_ref"]))
        if "evidence_ref" in c:
            s += t["evidence_ref"].format(evidence_ref=_ref(c["evidence_ref"]))
        return s
    if action_type == "presence_changed":
        s = t["presence_changed"].format(state=t["states"][c["state"]])
        if "until" in c:
            s += t["until"].format(until=_time(c["until"], lang))
        return s
    raise RenderError(f"no rendering for {action_type!r}")


def _participant(p: dict[str, str], lang: str) -> str:
    label = _ref(p["identity"])
    if p["role"] == "member":
        return label
    return f"{label} ({_T[lang][p['role']]})"


def render(envelope: dict[str, Any], actor_identity: str, lang: str) -> Rendering:
    """Render a validated EDP envelope for ``actor_identity`` in ``lang``."""
    if lang not in LANGUAGES:
        raise RenderError(f"unsupported language {lang!r}")
    t = _T[lang]
    action = envelope["action"]
    action_type = action["type"]
    head = f"{_sentence(action_type, action['content'], lang)} {t['in'].format(conversation=_ref(envelope['conversation_id']))}."
    others = [p for p in envelope["participants"] if p["identity"] != actor_identity]
    lines = [head]
    lines.append(
        t["to"].format(recipients=_list(others, lang, wrap=lambda p: _participant(p, lang)))
        if others
        else t["nobody"]
    )
    valid_from = envelope["temporal"].get("valid_from")
    if valid_from:
        lines.append(t["valid_from"].format(valid_from=_time(valid_from, lang)))
    reversibility = policy_for(action_type).reversibility
    lines.append(t[Reversibility(reversibility).value])
    text = "\n".join(lines)
    return Rendering(text, lang, RENDERER_VERSION, rendering_hash(text, lang, RENDERER_VERSION))
