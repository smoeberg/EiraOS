"""X-1: the exit guarantee (EIRA-CONTEXT §6.5; testplan §4).

The reference tool reads a home that EiraOS wrote, with nothing but the CMK,
in a separate Python process that cannot import EiraOS (``python -I`` from an
empty directory, no PYTHONPATH). The testplan's N2 version runs it in a clean
container; this is the N1 approximation of that.
"""

from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric import ec

from app.context.devices import accept_device_list, make_device_list
from app.context.home import ContextWriter
from tests.context.conftest import ISSUED

REPO = Path(__file__).resolve().parents[2]
TOOL = REPO / "tools" / "eira-context-export" / "eira_context_export.py"


def _run(home: Path, cmk: bytes, out: Path, tmp: Path) -> subprocess.CompletedProcess:
    cmk_file = tmp / "cmk.hex"
    cmk_file.write_text(cmk.hex())
    empty = tmp / "empty"
    empty.mkdir(exist_ok=True)
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "PYTHONHOME")}
    return subprocess.run(
        [sys.executable, "-I", str(TOOL), "--home", str(home), "--cmk-file", str(cmk_file), "--out", str(out)],
        cwd=empty, env=env, capture_output=True, text=True, timeout=120,
    )


def test_x1_the_tool_imports_nothing_from_eiraos():
    tree = ast.parse(TOOL.read_text(encoding="utf-8"))
    roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".")[0])
    assert roots <= set(sys.stdlib_module_names) | {"cryptography", "__future__"}, roots


def test_x1_a_files_come_back_byte_for_byte_without_eiraos(home, ctx, device, tmp_path):
    files = {
        "Referater/2026-11-20.txt": "Bestyrelsesmøde. Æ ø å.\n".encode(),
        "Billeder/stor.bin": os.urandom(1_500_000),  # several blocks
        "tom.txt": b"",
        "slettes.txt": "væk".encode(),
    }
    writer = ContextWriter(home, ctx, device)
    writer.write_record({"eira_context": "1", "context_id": ctx.context_id, "display_name": "Bestyrelse",
                         "kind": "personal"})
    for path, data in files.items():
        writer.add_file(path, data)
    writer.commit()
    writer.delete_file("slettes.txt")
    writer.add_file("Referater/2026-11-20.txt", "Rettet referat.\n".encode())
    writer.commit()
    home.put_if_absent("keys/devices.signed",
                       make_device_list(ctx.context_id, 1, [(device.public_key(), "file")], device, issued_at=ISSUED))

    out = tmp_path / "export"
    result = _run(home.root, ctx.cmk, out, tmp_path)
    assert result.returncode == 0, result.stderr + result.stdout

    assert (out / "files" / "Referater/2026-11-20.txt").read_bytes() == "Rettet referat.\n".encode()
    assert (out / "files" / "Billeder/stor.bin").read_bytes() == files["Billeder/stor.bin"]
    assert (out / "files" / "tom.txt").read_bytes() == b""
    assert not (out / "files" / "slettes.txt").exists()
    assert json.loads((out / "context.json").read_text())["display_name"] == "Bestyrelse"


def test_x1_a_two_devices_changing_the_same_file_both_come_out(home, ctx, tmp_path, audit):
    a = ec.generate_private_key(ec.SECP256R1())
    b = ec.generate_private_key(ec.SECP256R1())
    raw = make_device_list(ctx.context_id, 1, [(a.public_key(), "tpm"), (b.public_key(), "tpm")], a, issued_at=ISSUED)
    assert accept_device_list(raw, context_id=ctx.context_id, current=None, org_key=None, audit=audit)
    home.put_if_absent("keys/devices.signed", raw)
    for key, text in ((a, b"from A"), (b, b"from B")):
        writer = ContextWriter(home, ctx, key)
        writer.write_record({"eira_context": "1", "context_id": ctx.context_id, "display_name": "x",
                             "kind": "personal"})
        writer.add_file("same.txt", text)
        writer.commit()

    out = tmp_path / "export"
    assert _run(home.root, ctx.cmk, out, tmp_path).returncode == 0
    contents = sorted(p.read_bytes() for p in (out / "files").iterdir())
    assert contents == [b"from A", b"from B"]  # nothing dropped silently


def test_x1_a_forged_objects_are_reported_not_written(home, ctx, device, tmp_path):
    writer = ContextWriter(home, ctx, device)
    writer.write_record({"eira_context": "1", "context_id": ctx.context_id, "display_name": "x", "kind": "personal"})
    writer.add_file("ok.txt", b"ok")
    writer.commit()
    home.put_if_absent("keys/devices.signed",
                       make_device_list(ctx.context_id, 1, [(device.public_key(), "file")], device, issued_at=ISSUED))
    # A manifest from a device that is not on the list.
    stranger = ec.generate_private_key(ec.SECP256R1())
    other = ContextWriter(home, ctx, stranger)
    other.add_file("evil.txt", b"evil")
    other.commit()

    out = tmp_path / "export"
    assert _run(home.root, ctx.cmk, out, tmp_path).returncode == 0
    assert (out / "files" / "ok.txt").read_bytes() == b"ok"
    assert not (out / "files" / "evil.txt").exists()
    report = json.loads((out / "export.json").read_text())
    assert [i["reason"] for i in report["ignored"]] == ["unknown_device"]


def test_the_tool_refuses_a_path_outside_its_output(home, ctx, device, tmp_path):
    """A signed manifest with "../" must not make the tool write outside OUT."""
    import app.context.manifest as m

    writer = ContextWriter(home, ctx, device)
    writer.write_record({"eira_context": "1", "context_id": ctx.context_id, "display_name": "x", "kind": "personal"})
    writer.add_file("ok.txt", b"ok")
    # Bypass the writer's own check, as a buggy or hostile writer would.
    original = m.safe_path
    m.safe_path = lambda path: True
    try:
        writer.files["../../escaped.txt"] = {**writer.files["ok.txt"], "path": "../../escaped.txt"}
        writer.commit()
    finally:
        m.safe_path = original
    home.put_if_absent("keys/devices.signed",
                       make_device_list(ctx.context_id, 1, [(device.public_key(), "file")], device, issued_at=ISSUED))
    out = tmp_path / "deep" / "export"
    result = _run(home.root, ctx.cmk, out, tmp_path)
    assert result.returncode == 1
    assert not list(tmp_path.rglob("escaped.txt"))
