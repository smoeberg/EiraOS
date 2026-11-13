# eira-context-export

Reads an EIRA context home **without EiraOS**: the exit guarantee of
[EIRA-CONTEXT 1.0 §6.5](../../specs/EIRA-CONTEXT-1.0.md). It needs only Python 3
and the `cryptography` package, and the context's master key (CMK).

```bash
pip install cryptography
python3 eira_context_export.py --home /path/to/home --cmk-file cmk.hex --out export/
```

The output is ordinary files (`export/files/`), the context record
(`export/context.json`), structured data in Automerge's own open format
(`export/documents/*.automerge`) and a report (`export/export.json`) of
what was exported and what was ignored and why. A file changed on several
devices is written once per version (`<path>.konflikt-<device>`): nothing is
dropped silently.

The tool verifies everything it reads: the signed device list, each
manifest's signature and Merkle root, and each block's authentication and
content id. Anything that fails is reported, never written.

The tool lives here until it gets its own repository (§6.5). It must keep
importing nothing from EiraOS; a test enforces that
(`tests/context/test_export.py`).

Not yet: Automerge documents as JSON (comes with the structured data in
UDVIKLINGSPLAN F2.6) and export with the recovery key instead of the CMK
(needs the recovery wrapping of §5.1).
