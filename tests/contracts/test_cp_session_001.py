"""Contract acceptance tests — CP-SESSION-001, CP-IDENTITY-001."""

from __future__ import annotations

import uuid

import pytest

from app.database import init_db
from app.daemons import identityd
from app.session_store import ensure_session, get_session, update_assurance


@pytest.fixture(autouse=True)
def _db():
    init_db()
    yield


def test_cp_session_s1_step_up_isolation():
  """CP-SESSION-001 S1 — step-up på A påvirker ikke B."""
  sid_a = ensure_session(str(uuid.uuid4()), "a@test.dk")
  sid_b = ensure_session(str(uuid.uuid4()), "b@test.dk")

  identityd.identity_step_up({"session_id": sid_a})

  assert get_session(sid_a)["assurance_level"] == "org_acting"
  assert get_session(sid_b)["assurance_level"] == "eid_low"


def test_cp_session_s3_auto_provision():
  """CP-SESSION-001 S3 — ukendt session_id provisioneres."""
  sid = str(uuid.uuid4())
  assert ensure_session(sid, "new@test.dk") == sid
  assert get_session(sid) is not None
  assert ensure_session(sid, "new@test.dk") == sid


def test_cp_identity_s1_isolated_step_up():
  """CP-IDENTITY-001 S1 — samme som session isolation via identity daemon."""
  sid_a = str(uuid.uuid4())
  sid_b = str(uuid.uuid4())
  ensure_session(sid_a)
  ensure_session(sid_b)

  identityd.identity_step_up({"session_id": sid_a})

  assert get_session(sid_a)["assurance_level"] == "org_acting"
  assert get_session(sid_b)["assurance_level"] == "eid_low"
