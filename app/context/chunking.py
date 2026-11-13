"""Content-defined chunking (EIRA-CONTEXT §6.2): FastCDC with normalised
chunking, min 256 KiB, average 1 MiB, max 4 MiB. A file at or below the
minimum is one block.

The gear table is fixed: GEAR[i] = first 8 bytes (big-endian) of
SHA-256("eira-ctx-gear-v1" || i). Chunk boundaries only affect deduplication;
a reader never needs them, it concatenates a file's blocks in order.
"""

from __future__ import annotations

from hashlib import sha256

MIN_SIZE = 256 * 1024
AVG_SIZE = 1024 * 1024
MAX_SIZE = 4 * 1024 * 1024
_M64 = (1 << 64) - 1
GEAR = [int.from_bytes(sha256(b"eira-ctx-gear-v1" + bytes([i])).digest()[:8], "big") for i in range(256)]
# Normalisation level 2 around 2^20: harder to cut before the average, easier after.
_MASK_S = ((1 << 22) - 1) << (64 - 22)
_MASK_L = ((1 << 18) - 1) << (64 - 18)


def _cut(data: memoryview, min_size: int, avg_size: int, max_size: int) -> int:
    n = len(data)
    if n <= min_size:
        return n
    end = min(n, max_size)
    normal = min(end, avg_size)
    h = 0
    i = min_size
    while i < normal:
        h = ((h << 1) + GEAR[data[i]]) & _M64
        if not h & _MASK_S:
            return i + 1
        i += 1
    while i < end:
        h = ((h << 1) + GEAR[data[i]]) & _M64
        if not h & _MASK_L:
            return i + 1
        i += 1
    return end


def chunks(data: bytes, *, min_size: int = MIN_SIZE, avg_size: int = AVG_SIZE,
           max_size: int = MAX_SIZE) -> list[bytes]:
    """The file split into blocks; joined, they are the file."""
    if not data:
        return [b""]
    view = memoryview(data)
    out = []
    while view:
        size = _cut(view, min_size, avg_size, max_size)
        out.append(bytes(view[:size]))
        view = view[size:]
    return out
