"""Two rights sets activated at the same time (fundregister S-23, UDVIKLINGSPLAN F1.7).

`contract.verify` judges a set against the active one (§4 rule 3: the version
only goes up; the same version with other content is a conflict). The check
and the install used to be separate steps, so two sets verified against the
same old set could both pass, and whichever wrote last won: a newer version
could be replaced by an older one, and two different sets with the same
version ("ambiguous policy") could both be accepted. The cache now installs
only while the set a verdict was judged against is still active, and the
agent judges again when it is not.
"""

from __future__ import annotations

import random
import threading

import pytest

from app.gate.policy import REGISTRY
from app.rights import agent, contract
from app.rights.cache import RightsCache, Superseded
from tests.rights_helpers import DEVICE, TestFleet
from tests.test_gate_kernel import BootClock, Clock


@pytest.fixture
def fleet(tmp_path):
    fleet = TestFleet(tmp_path / "rights", Clock(), boot_clock=BootClock())
    fleet.grant("device:local")
    fleet.cache.store_key_material(*fleet.key_material())
    fleet.publish()  # version 1 is active
    return fleet


def _signed(fleet: TestFleet, version: int, *, extra_grant: str | None = None) -> bytes:
    saved = fleet.version, list(fleet.grants)
    fleet.version = version
    if extra_grant:
        fleet.grant(extra_grant)
    raw = contract.canonical(fleet.document())
    fleet.version, fleet.grants = saved
    return raw


def _verify(fleet: TestFleet, raw: bytes) -> contract.Verdict:
    verdict = contract.verify(
        raw, anchors=fleet.anchors, device=DEVICE, active=fleet.cache.active_meta(),
        now=fleet.clock(), registry=REGISTRY,
    )
    assert verdict.ok, verdict.reason
    return verdict


def _apply(fleet: TestFleet, raw: bytes, cache: RightsCache | None = None) -> contract.Verdict:
    return agent.apply(
        raw, anchors=fleet.anchors, device=DEVICE, cache=cache or fleet.cache,
        registry=REGISTRY, wall_now=fleet.clock(),
    )


def _active_version(fleet: TestFleet) -> int:
    return fleet.cache.active_meta().version


def test_a_verdict_judged_against_a_replaced_set_is_not_installed(fleet):
    v2, v3 = _signed(fleet, 2), _signed(fleet, 3)
    verdict_v2, verdict_v3 = _verify(fleet, v2), _verify(fleet, v3)  # both against v1
    fleet.cache.install(v3, verdict_v3, fleet.clock())
    with pytest.raises(Superseded):
        fleet.cache.install(v2, verdict_v2, fleet.clock())
    assert _active_version(fleet) == 3


def test_two_sets_with_the_same_version_cannot_both_be_activated(fleet):
    first, second = _signed(fleet, 2), _signed(fleet, 2, extra_grant="obj:project:p-1")
    assert contract.content_hash(contract.parse(first)) != contract.content_hash(contract.parse(second))
    verdict_first, verdict_second = _verify(fleet, first), _verify(fleet, second)
    fleet.cache.install(first, verdict_first, fleet.clock())
    with pytest.raises(Superseded):
        fleet.cache.install(second, verdict_second, fleet.clock())
    assert fleet.cache.active_meta().content_hash == verdict_first.content_hash


class _Interleaving(RightsCache):
    """Activates `other` between the agent's check and its install, once."""

    def __init__(self, base: RightsCache, fleet: TestFleet, other: bytes):
        super().__init__(base.directory, boot_clock=base._boot_clock,
                         enrollment_path=base._enrollment_path)
        self._fleet, self._other, self._done = fleet, other, False

    def install(self, raw, verdict, wall_now):
        if not self._done:
            self._done = True
            other_verdict = _verify(self._fleet, self._other)
            super().install(self._other, other_verdict, wall_now)
        return super().install(raw, verdict, wall_now)


def test_agent_judges_again_and_refuses_a_rollback(fleet):
    v2, v3 = _signed(fleet, 2), _signed(fleet, 3)
    cache = _Interleaving(fleet.cache, fleet, v3)
    verdict = _apply(fleet, v2, cache)
    assert (verdict.ok, verdict.reason) == (False, contract.Reason.VERSION_ROLLBACK)
    assert _active_version(fleet) == 3


def test_agent_refuses_an_ambiguous_set_activated_at_the_same_time(fleet):
    first, second = _signed(fleet, 2), _signed(fleet, 2, extra_grant="obj:project:p-1")
    cache = _Interleaving(fleet.cache, fleet, first)
    verdict = _apply(fleet, second, cache)
    assert (verdict.ok, verdict.reason) == (False, contract.Reason.VERSION_CONFLICT)
    assert fleet.cache.active_meta().content_hash == contract.content_hash(contract.parse(first))


def test_the_same_set_activated_twice_at_once_is_a_noop(fleet):
    v2 = _signed(fleet, 2)
    cache = _Interleaving(fleet.cache, fleet, v2)
    verdict = _apply(fleet, v2, cache)
    assert verdict.ok and verdict.noop
    assert _active_version(fleet) == 2


@pytest.mark.parametrize("seed", range(5))
def test_concurrent_activations_end_on_the_highest_version(fleet, seed):
    raws = {version: _signed(fleet, version) for version in range(2, 8)}
    order = list(raws)
    random.Random(seed).shuffle(order)
    barrier = threading.Barrier(len(order))
    results: dict[int, contract.Verdict] = {}

    def run(version: int) -> None:
        cache = RightsCache(fleet.cache.directory, boot_clock=fleet.cache._boot_clock,
                            enrollment_path=fleet.cache._enrollment_path)
        barrier.wait()
        results[version] = _apply(fleet, raws[version], cache)

    threads = [threading.Thread(target=run, args=(v,)) for v in order]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
    assert _active_version(fleet) == 7
    assert results[7].ok
    for version, verdict in results.items():
        assert verdict.ok or verdict.reason == contract.Reason.VERSION_ROLLBACK, (version, verdict)
    current = fleet.cache.current(fleet.clock())
    assert current is not None and current.version == 7
