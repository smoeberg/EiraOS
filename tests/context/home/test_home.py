"""H-1 and B-3 c (EIRA-CONTEXT §6.1, §6.2; testplan §4), level N2."""

from __future__ import annotations

import os
import threading

import pytest

from app.context.blocks import decrypt_block, encrypt_block
from app.context.errors import E_CONTEXT_HOME_UNSUPPORTED, E_CONTEXT_INTEGRITY, ContextError
from app.context.home import ContextWriter, block_path
from app.context.remote import WebDavHome, attach
from tests.context.home.conftest import RACY
from tests.context.home.faulty_server import serve

pytestmark = pytest.mark.home


def test_h1_a_an_existing_block_is_never_overwritten(remote_home, ctx):
    block_id, first = encrypt_block(b"referat", ctx)
    _, second = encrypt_block(b"referat", ctx)  # another valid ciphertext, same id
    assert first != second
    assert remote_home.put_if_absent(block_path(block_id), first) is True
    assert remote_home.put_if_absent(block_path(block_id), second) is False  # "exists", not an error
    assert remote_home.get(block_path(block_id)) == first


def test_h1_b_concurrent_uploads_of_the_same_block_have_one_winner(remote_home, ctx, request):
    if remote_home.server_name in RACY:
        request.applymarker(pytest.mark.xfail(reason="check-then-write server (testplan finding 6)",
                                              strict=False))
    repetitions = int(os.environ.get("EIRA_TEST_H1B_REPETITIONS", "100"))
    for repetition in range(repetitions):
        plaintext = f"blok {repetition}".encode()
        versions = [encrypt_block(plaintext, ctx) for _ in range(20)]
        block_id = versions[0][0]
        results: list[tuple[bool, bytes]] = []
        lock = threading.Lock()
        start = threading.Barrier(20)

        def upload(blob: bytes) -> None:
            start.wait()
            written = remote_home.put_if_absent(block_path(block_id), blob)
            with lock:
                results.append((written, blob))

        threads = [threading.Thread(target=upload, args=(blob,)) for _, blob in versions]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        winners = [blob for written, blob in results if written]
        assert len(winners) == 1, (repetition, len(winners))
        assert remote_home.get(block_path(block_id)) == winners[0]
        assert all(decrypt_block(block_id, blob, ctx) == plaintext for _, blob in versions)


def test_h1_c_a_compliant_home_is_accepted(remote_home):
    assert attach(remote_home) is remote_home


@pytest.mark.parametrize("mode", ["ignores", "lies"])
def test_h1_c_a_home_that_overwrites_is_refused(mode):
    server, url = serve(mode)
    try:
        with pytest.raises(ContextError) as refused:
            attach(WebDavHome(url))
        assert refused.value.code == E_CONTEXT_HOME_UNSUPPORTED
    finally:
        server.shutdown()


def test_h1_c_the_faulty_test_servers_are_faulty_and_the_honest_one_is_not():
    """The tests above prove nothing if the test servers do not misbehave."""
    honest, honest_url = serve("honest")
    try:
        assert attach(WebDavHome(honest_url))
    finally:
        honest.shutdown()


def test_h1_d_a_second_manifest_at_the_same_path_is_refused_and_audited(remote_home, ctx, device, audit):
    first = ContextWriter(remote_home, ctx, device, audit=audit)
    first.add_file("a.txt", b"1")
    name = first.commit()
    before = remote_home.get(f"manifests/{name}")
    second = ContextWriter(remote_home, ctx, device, audit=audit)  # does not know seq 1 exists
    second.add_file("a.txt", b"2")
    with pytest.raises(ContextError) as refused:
        second.commit()
    assert refused.value.code == E_CONTEXT_INTEGRITY
    assert audit.events[-1] == ("context.manifest_collision", {"context_id": ctx.context_id, "manifest": name})
    assert remote_home.get(f"manifests/{name}") == before


def test_b3_c_a_block_copied_to_another_id_cannot_be_read(remote_home, ctx):
    block_id, block = encrypt_block(b"hemmeligt", ctx)
    other_id, _ = encrypt_block(b"andet", ctx)
    remote_home.put_if_absent(block_path(block_id), block)
    remote_home.put_if_absent(block_path(other_id), remote_home.get(block_path(block_id)))  # the copy
    with pytest.raises(ContextError) as failed:
        decrypt_block(other_id, remote_home.get(block_path(other_id)), ctx)
    assert failed.value.code == E_CONTEXT_INTEGRITY
    assert decrypt_block(block_id, remote_home.get(block_path(block_id)), ctx) == b"hemmeligt"
