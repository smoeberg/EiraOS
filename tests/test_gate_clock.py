from __future__ import annotations

import sys

import pytest

from app import clock
from app.clock import BootInstant, within


def test_within_same_boot():
    assert within(BootInstant("b", 100), BootInstant("b", 150), 100)
    assert not within(BootInstant("b", 100), BootInstant("b", 200), 100)


def test_within_rejects_other_boot_and_backwards_time():
    assert not within(BootInstant("a", 100), BootInstant("b", 101), 100)
    assert not within(BootInstant("b", 100), BootInstant("b", 99), 100)
    assert not within(None, BootInstant("b", 1), 100)


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="kernel boot_id")
def test_boot_now_uses_kernel_boot_id_and_boottime():
    first, second = clock.boot_now(), clock.boot_now()
    assert first.boot_id == clock.BOOT_ID_PATH.read_text().strip()
    assert second.ns >= first.ns


def test_without_boot_id_the_boot_is_the_process(monkeypatch, tmp_path):
    monkeypatch.setattr(clock, "BOOT_ID_PATH", tmp_path / "missing")
    instant = clock.boot_now()
    assert instant.boot_id.startswith("process:")
