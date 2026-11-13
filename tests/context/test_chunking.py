"""Chunking (EIRA-CONTEXT §6.2): boundaries are content-defined and bounded."""

from __future__ import annotations

import os

from app.context.chunking import MAX_SIZE, MIN_SIZE, chunks


def test_small_files_are_one_block():
    assert chunks(b"") == [b""]
    assert chunks(b"x" * MIN_SIZE) == [b"x" * MIN_SIZE]


def test_chunks_join_to_the_file_and_respect_the_bounds():
    data = os.urandom(6 * 1024 * 1024)
    parts = chunks(data)
    assert b"".join(parts) == data
    assert all(len(p) <= MAX_SIZE for p in parts)
    assert all(len(p) >= MIN_SIZE for p in parts[:-1])
    assert len(parts) > 1


def test_boundaries_follow_content_so_an_insert_only_changes_nearby_blocks():
    data = os.urandom(5 * 1024 * 1024)
    before = chunks(data)
    after = chunks(data[:100] + b"inserted" + data[100:])
    assert before[-1] == after[-1]  # the tail realigns: deduplication works
