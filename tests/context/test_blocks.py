"""B-1, B-2, B-3 (EIRA-CONTEXT §6.2; testplan §4), level N1."""

from __future__ import annotations

import ast
import inspect
import json
import os
from pathlib import Path

import pytest

from app.context import blocks
from app.context.blocks import Context, decrypt_block, encrypt_block, new_context_id
from app.context.errors import E_CONTEXT_INTEGRITY, ContextError
from tests.context import reference as ref

VECTORS = Path(__file__).resolve().parents[1] / "vectors" / "context"
REPO = Path(__file__).resolve().parents[2]


def _vector(name: str) -> dict:
    return json.loads((VECTORS / name).read_text())


# --- B-1: block_id is computed from exactly the encrypted plaintext ----------------


def test_b1_a_roundtrip_and_the_id_is_the_reference_hmac(ctx):
    plaintext = b"Referat\n" * 100
    block_id, block = encrypt_block(plaintext, ctx)
    assert decrypt_block(block_id, block, ctx) == plaintext
    assert block_id == ref.block_id(ctx.cmk, plaintext)


@pytest.mark.parametrize("case", ["version", "salt", "nonce", "ciphertext", "tag"])
def test_b1_b_any_changed_byte_gives_integrity_and_no_plaintext(case):
    vectors = _vector("block-v2-negative.json")
    v = next(c for c in vectors["cases"] if c["name"] == case)
    context = Context(v["context_id"], bytes.fromhex(vectors["cmk"]))
    with pytest.raises(ContextError) as failed:
        decrypt_block(v["block_id"], bytes.fromhex(v["block"]), context)
    assert failed.value.code == E_CONTEXT_INTEGRITY


def test_b1_c_an_id_that_is_not_the_hmac_of_the_content_is_caught_on_read():
    vectors = _vector("block-v2-negative.json")
    v = next(c for c in vectors["cases"] if c["name"] == "id_not_hmac_of_content")
    cmk = bytes.fromhex(vectors["cmk"])
    # The AEAD itself is valid (the broken writer used the correct AAD) ...
    assert ref.unseal(cmk, v["context_id"], ref.BLOCK, v["block_id"], bytes.fromhex(v["block"]))
    # ... so only the HMAC check on read catches it.
    with pytest.raises(ContextError) as failed:
        decrypt_block(v["block_id"], bytes.fromhex(v["block"]), Context(v["context_id"], cmk))
    assert failed.value.code == E_CONTEXT_INTEGRITY


def test_b1_d_encrypt_block_takes_only_the_plaintext_and_the_context():
    params = list(inspect.signature(encrypt_block).parameters)
    assert params == ["plaintext", "context"]
    for name in params:
        assert not any(word in name for word in ("id", "salt", "nonce", "key")), name


def test_b1_d_no_caller_passes_more_than_plaintext_and_context():
    calls = []
    for path in (REPO / "app").rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call):
                func = node.func
                name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
                if name == "encrypt_block":
                    calls.append(path)
                    assert len(node.args) == 2 and not node.keywords, f"{path}:{node.lineno}"
    assert calls, "encrypt_block has callers in app/ (the context writer)"


def test_b1_e_same_plaintext_same_id_but_fresh_ciphertext(ctx):
    first_id, first = encrypt_block(b"same", ctx)
    second_id, second = encrypt_block(b"same", ctx)
    assert first_id == second_id
    assert first[1:33] != second[1:33] and first[33:45] != second[33:45] and first != second


def test_b1_f_vectors_both_ways():
    v = _vector("block-v2.json")
    context = Context(v["context_id"], bytes.fromhex(v["cmk"]))
    assert decrypt_block(v["block_id"], bytes.fromhex(v["block"]), context) == bytes.fromhex(v["plaintext"])
    block_id, block = encrypt_block(bytes.fromhex(v["plaintext"]), context)
    assert block_id == v["block_id"]
    assert ref.unseal(context.cmk, context.context_id, ref.BLOCK, block_id, block) == bytes.fromhex(v["plaintext"])


# --- B-2: fresh salt and nonce on every encryption ------------------------------


def test_b2_a_no_repeats_in_100_000_encryptions(ctx):
    salts, nonces, blobs = set(), set(), set()
    for _ in range(100_000):
        _, block = encrypt_block(b"x", ctx)
        salts.add(block[1:33])
        nonces.add(block[33:45])
        blobs.add(block)
    assert len(salts) == len(nonces) == len(blobs) == 100_000


def test_b2_b_salt_and_nonce_come_from_the_csprng_on_every_call(ctx, monkeypatch):
    requested = []
    real = os.urandom

    def spy(n):
        requested.append(n)
        return real(n)

    monkeypatch.setattr(blocks.os, "urandom", spy)
    encrypt_block(b"a", ctx)
    encrypt_block(b"a", ctx)
    assert requested == [32, 12, 32, 12]


# --- B-3: the AAD binds context_id and block_id ----------------------------------


def test_b3_a_a_block_cannot_move_to_another_context_with_the_same_cmk(ctx):
    block_id, block = encrypt_block(b"secret", ctx)
    other = Context(new_context_id(), ctx.cmk)
    with pytest.raises(ContextError) as failed:
        decrypt_block(block_id, block, other)
    assert failed.value.code == E_CONTEXT_INTEGRITY


def test_b3_b_a_block_cannot_move_to_another_valid_block_id(ctx):
    block_id, block = encrypt_block(b"secret", ctx)
    other_id, _ = encrypt_block(b"other", ctx)
    with pytest.raises(ContextError) as failed:
        decrypt_block(other_id, block, ctx)
    assert failed.value.code == E_CONTEXT_INTEGRITY


@pytest.mark.parametrize("case", ["wrong_context_id", "wrong_block_id"])
def test_b3_vectors(case):
    vectors = _vector("block-v2-negative.json")
    v = next(c for c in vectors["cases"] if c["name"] == case)
    with pytest.raises(ContextError):
        decrypt_block(v["block_id"], bytes.fromhex(v["block"]), Context(v["context_id"], bytes.fromhex(vectors["cmk"])))


def test_the_cmk_is_never_in_a_repr(ctx):
    assert ctx.cmk.hex() not in repr(ctx) and str(ctx.cmk) not in repr(ctx)
