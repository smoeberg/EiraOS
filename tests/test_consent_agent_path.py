"""EIRA-CONSENT-AGENT §3, §5.2–§5.4, §7: only the setgid consent agent may
consent; it gets the key only when it runs on the session's own compositor."""

from __future__ import annotations

import sqlite3
from types import SimpleNamespace

import pytest

from app.auth import consent_agent
from app.gate import GateCode, consent_path
from app.gate.caller import Caller, acting_as
from app.gate.policy import Origin
from tests.callers import CONSENT_KEY, HUMAN_UID
from tests.test_gate_kernel import envelope, raw
from tests.test_gate_kernel import world as world  # noqa: F401  (fixture)

CONSENT_GID = 777
AGENT = Caller(uid=HUMAN_UID, pid=5000, model=False, gid=CONSENT_GID)


@pytest.fixture(autouse=True)
def consent_group(monkeypatch):
    monkeypatch.setattr(consent_path, "consent_gid", lambda: CONSENT_GID)


# --- §3: nobody else may hold the GID (fail closed) ---------------------------------


class FakeGrp:
    def __init__(self, groups):
        self.groups = groups

    def getgrnam(self, name):
        if name not in self.groups:
            raise KeyError(name)
        gid, members = self.groups[name]
        return SimpleNamespace(gr_gid=gid, gr_mem=members)


class Agent:
    def __init__(self, uid=0, gid=CONSENT_GID, mode=0o102755):
        self.result = SimpleNamespace(st_uid=uid, st_gid=gid, st_mode=mode)

    def stat(self):
        return self.result


def check(monkeypatch, tmp_path, groups=None, users=(), gshadow="eira-consent:!::\n", agent=None):
    groups = groups if groups is not None else {"eira-consent": (CONSENT_GID, []), "eira": (900, []),
                                                  "eira-clients": (901, []), "eira-model": (902, [])}
    monkeypatch.setattr(consent_path, "grp", FakeGrp(groups))
    monkeypatch.setattr(consent_path.pwd, "getpwall",
                        lambda: [SimpleNamespace(pw_name=n, pw_gid=g) for n, g in users])
    shadow = tmp_path / "gshadow"
    shadow.write_text(gshadow)
    return consent_path.require_consent_path(gshadow=shadow, agent=agent or Agent())


def test_a_correct_installation_passes(monkeypatch, tmp_path):
    assert check(monkeypatch, tmp_path) == CONSENT_GID


@pytest.mark.parametrize(("kwargs", "reason"), [
    ({"groups": {}}, "does not exist"),
    ({"groups": {"eira-consent": (1500, [])}}, "not a system gid"),
    ({"groups": {"eira-consent": (CONSENT_GID, []), "eira-clients": (CONSENT_GID, [])}}, "shares its gid"),
    ({"groups": {"eira-consent": (CONSENT_GID, ["mallory"])}}, "has members"),
    ({"users": [("mallory", CONSENT_GID)]}, "primary group"),
    ({"gshadow": "eira-consent:$6$salt$hash::\n"}, "group password"),
    ({"agent": Agent(uid=1000)}, "must be root:eira-consent 2755"),
    ({"agent": Agent(gid=0)}, "must be root:eira-consent 2755"),
    ({"agent": Agent(mode=0o100755)}, "must be root:eira-consent 2755"),  # setgid bit removed
])
def test_anything_that_lets_someone_else_hold_the_gid_stops_the_daemons(monkeypatch, tmp_path, kwargs, reason):
    with pytest.raises(consent_path.ConsentPathBroken, match=reason):
        check(monkeypatch, tmp_path, **kwargs)


# --- §7: the gate takes decisions only from the agent --------------------------------


def require_agent(world):
    world.gate._gate._consent_agent_required = lambda: True


def proposed(world):
    proposal = world.gate.propose(raw(envelope()), "s-anne", Origin.USER)
    record = world.store.find("dlg-0001")
    return proposal.content_hash, record["rendering_hash"]


def test_the_app_or_any_user_program_gets_e_consent_path(world):
    require_agent(world)
    digest, rhash = proposed(world)
    result = world.gate.grant_consent("dlg-0001", digest, rhash, "s-anne")  # the app, with a valid proof
    assert result.code is GateCode.E_CONSENT_PATH


def test_the_agent_with_its_proof_can_consent_and_confirm(world):
    require_agent(world)
    digest, rhash = proposed(world)
    with acting_as(AGENT):
        assert world.gate.grant_consent("dlg-0001", digest, rhash, "s-anne").code is None
        assert world.gate.confirm("dlg-0001", digest, rhash, "s-anne").decision.value == "PASS"


def test_the_agent_without_a_proof_is_still_refused(world):
    require_agent(world)
    digest, rhash = proposed(world)
    with acting_as(AGENT):
        result = world.gate._gate.grant_consent("dlg-0001", digest, rhash, "s-anne", proof=None)
    assert result.code is GateCode.E_CONSENT_PROOF


def test_the_agent_reads_what_it_shows_from_the_gate(world):
    require_agent(world)
    digest, rhash = proposed(world)
    assert world.gate.rendering_for("dlg-0001", "s-anne") is None  # not the agent
    with acting_as(AGENT):
        shown = world.gate.rendering_for("dlg-0001", "s-anne")
        assert (shown["content_hash"], shown["rendering"]["hash"], shown["next"]) == (digest, rhash, "consent")
        world.gate.grant_consent("dlg-0001", digest, rhash, "s-anne")
        assert world.gate.rendering_for("dlg-0001", "s-anne")["next"] == "confirm"
        assert world.gate.rendering_for("dlg-0001", "s-bo") is None  # not Bo's action


def test_a_development_machine_keeps_the_app_path(world):
    digest, rhash = proposed(world)  # installed() is false in tests
    assert world.gate.grant_consent("dlg-0001", digest, rhash, "s-anne").code is None


# --- §5.2–§5.3: registration on the session's compositor, then the key --------------

LEADER, LAUNCHER, COMPOSITOR, AGENT_PID, SHELL, NESTED = 100, 200, 300, 5000, 400, 500


def proc_tree(tmp_path, *, nested_session="2", compositor_uid=HUMAN_UID):
    proc, sessions = tmp_path / "proc", tmp_path / "sessions"
    sessions.mkdir(parents=True)
    (sessions / "2").write_text(f"UID={HUMAN_UID}\nLEADER={LEADER}\n")
    tree = {  # pid: (ppid, start, uid, sessionid)
        LEADER: (1, 10, 0, "2"),
        LAUNCHER: (LEADER, 11, HUMAN_UID, "2"),
        COMPOSITOR: (LAUNCHER, 12, compositor_uid, "2"),
        SHELL: (COMPOSITOR, 13, HUMAN_UID, "2"),
        NESTED: (SHELL, 14, HUMAN_UID, nested_session),
        AGENT_PID: (COMPOSITOR, 15, HUMAN_UID, "2"),
    }
    for pid, (ppid, start, uid, sid) in tree.items():
        d = proc / str(pid)
        d.mkdir(parents=True)
        # Fields after "(comm)": state, ppid, 17 more, then starttime (field 22).
        rest = ["S", str(ppid)] + ["0"] * 17 + [str(start)] + ["0"] * 5
        (d / "stat").write_text(f"{pid} (proc name) {' '.join(rest)}\n")
        (d / "status").write_text(f"Name:\tx\nUid:\t{uid}\t{uid}\t{uid}\t{uid}\n")
        (d / "sessionid").write_text(sid)
        (d / "loginuid").write_text(str(uid))
    return proc, sessions


@pytest.fixture
def tree(tmp_path, monkeypatch):
    proc, sessions = proc_tree(tmp_path)
    monkeypatch.setattr(consent_agent, "PROC", proc)
    monkeypatch.setattr(consent_agent, "LOGIND_SESSIONS", sessions)
    db = str(tmp_path / "app.db")
    conn = sqlite3.connect(db)
    conn.execute("""CREATE TABLE sessions (session_id TEXT, os_uid INTEGER, authenticated_at TEXT,
                    identity TEXT, expires_at TEXT, consent_key TEXT, logind_session TEXT)""")
    conn.executemany("INSERT INTO sessions VALUES (?, ?, ?, ?, ?, ?, ?)", [
        ("s-old", HUMAN_UID, "2026-11-11T08:00:00Z", "did:eira:anne", "2099-01-01T00:00:00Z", "aa" * 32, "2"),
        ("s-new", HUMAN_UID, "2026-11-11T09:00:00Z", "did:eira:anne", "2099-01-01T00:00:00Z", CONSENT_KEY, "2"),
        ("s-elsewhere", HUMAN_UID, "2026-11-11T10:00:00Z", "did:eira:anne", "2099-01-01T00:00:00Z",
         "bb" * 32, "7"),
        ("s-expired", HUMAN_UID, "2026-11-11T11:00:00Z", "did:eira:anne", "2000-01-01T00:00:00Z", "cc" * 32, "2"),
    ])
    conn.commit()
    return SimpleNamespace(proc=proc, db=db)


def peer(pid=AGENT_PID, uid=HUMAN_UID, gid=CONSENT_GID):
    return SimpleNamespace(pid=pid, uid=uid, gid=gid)


def test_the_agent_on_the_session_compositor_registers_and_gets_the_newest_key(tree):
    assert consent_agent.register(peer(), COMPOSITOR, tree.db)["logind_session"] == "2"
    claimed = consent_agent.claim_key(peer(), tree.db)
    assert (claimed["session_id"], claimed["consent_key"]) == ("s-new", CONSENT_KEY)


@pytest.mark.parametrize(("who", "compositor", "reason"), [
    (peer(gid=HUMAN_UID), COMPOSITOR, "only the consent agent"),       # the app or any user program
    (peer(), SHELL, "not the session's compositor"),                    # a nested compositor in the session
    (peer(), 1, "compositor_pid"),
])
def test_registration_is_refused(tree, who, compositor, reason):
    with pytest.raises(consent_agent.Refused, match=reason):
        consent_agent.register(who, compositor, tree.db)


def test_a_compositor_in_another_logind_session_is_refused(tmp_path, monkeypatch):
    proc, sessions = proc_tree(tmp_path, nested_session="9")
    monkeypatch.setattr(consent_agent, "PROC", proc)
    monkeypatch.setattr(consent_agent, "LOGIND_SESSIONS", sessions)
    with pytest.raises(consent_agent.Refused, match="another logind session"):
        consent_agent.register(peer(), NESTED, str(tmp_path / "db"))


def test_a_nested_compositor_in_the_same_session_is_refused(tmp_path, monkeypatch):
    proc, sessions = proc_tree(tmp_path, nested_session="2")
    monkeypatch.setattr(consent_agent, "PROC", proc)
    monkeypatch.setattr(consent_agent, "LOGIND_SESSIONS", sessions)
    with pytest.raises(consent_agent.Refused, match="not the session's compositor"):
        consent_agent.register(peer(), NESTED, str(tmp_path / "db"))


def test_a_compositor_of_another_user_is_refused(tmp_path, monkeypatch):
    proc, sessions = proc_tree(tmp_path, compositor_uid=1001)
    monkeypatch.setattr(consent_agent, "PROC", proc)
    monkeypatch.setattr(consent_agent, "LOGIND_SESSIONS", sessions)
    with pytest.raises(consent_agent.Refused, match="does not run as this user"):
        consent_agent.register(peer(), COMPOSITOR, str(tmp_path / "db"))


def test_only_a_registered_agent_gets_the_key(tree):
    with pytest.raises(consent_agent.Refused, match="not registered"):
        consent_agent.claim_key(peer(), tree.db)
    consent_agent.register(peer(), COMPOSITOR, tree.db)
    with pytest.raises(consent_agent.Refused, match="only the consent agent"):
        consent_agent.claim_key(peer(gid=HUMAN_UID), tree.db)


def test_a_restarted_compositor_ends_the_registration(tree):
    consent_agent.register(peer(), COMPOSITOR, tree.db)
    stat = tree.proc / str(COMPOSITOR) / "stat"
    stat.write_text(stat.read_text().replace(" 12 ", " 99 "))  # same pid, new start time
    with pytest.raises(consent_agent.Refused, match="gone"):
        consent_agent.claim_key(peer(), tree.db)
    with pytest.raises(consent_agent.Refused, match="not registered"):
        consent_agent.claim_key(peer(), tree.db)


def test_a_reused_agent_pid_is_not_registered(tree):
    consent_agent.register(peer(), COMPOSITOR, tree.db)
    stat = tree.proc / str(AGENT_PID) / "stat"
    stat.write_text(stat.read_text().replace(" 15 ", " 98 "))
    with pytest.raises(consent_agent.Refused, match="not registered"):
        consent_agent.claim_key(peer(), tree.db)




def test_without_a_session_a_bypass_still_gets_e_consent_path(world):
    require_agent(world)
    digest, rhash = proposed(world)
    result = world.gate.grant_consent("dlg-0001", digest, rhash, "no-such-session")
    assert result.code is GateCode.E_CONSENT_PATH
