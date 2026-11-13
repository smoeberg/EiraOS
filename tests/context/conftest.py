from __future__ import annotations

import os

import pytest
from cryptography.hazmat.primitives.asymmetric import ec

from app.context.blocks import Context, new_context_id
from app.context.devices import accept_device_list, make_device_list
from app.context.home import ContextWriter, LocalHome

ISSUED = "2026-11-13T12:00:00+00:00"


@pytest.fixture
def ctx() -> Context:
    return Context(new_context_id(), os.urandom(32))


@pytest.fixture
def device() -> ec.EllipticCurvePrivateKey:
    return ec.generate_private_key(ec.SECP256R1())


class Audit:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    def __call__(self, event: str, details: dict) -> None:
        self.events.append((event, details))


@pytest.fixture
def audit() -> Audit:
    return Audit()


@pytest.fixture
def home(tmp_path) -> LocalHome:
    return LocalHome(tmp_path / "home")


@pytest.fixture
def written(home, ctx, device, audit):
    """A home with a record, a device list and one manifest of two files."""
    writer = ContextWriter(home, ctx, device)
    writer.write_record({"eira_context": "1", "context_id": ctx.context_id, "display_name": "Test",
                         "kind": "personal"})
    raw = make_device_list(ctx.context_id, 1, [(device.public_key(), "file")], device, issued_at=ISSUED)
    home.put_if_absent("keys/devices.signed", raw)
    writer.add_file("Referater/a.txt", b"first file\n")
    writer.add_file("b.bin", os.urandom(300_000))
    name = writer.commit()
    devices = accept_device_list(raw, context_id=ctx.context_id, current=None, org_key=None, audit=audit)
    return writer, name, devices
