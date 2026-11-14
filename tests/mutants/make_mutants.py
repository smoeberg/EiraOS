"""Generates tests/mutants/CTX-*.patch (EIRA-CONTEXT testplan §2).

Each mutant is a small, realistic bug that breaks one invariant. A mutant is
a list of exact text replacements in the current source; this script turns
it into a unified diff with a ``Tests:`` header naming the tests that must
catch it. ``scripts/check-mutants.sh`` applies them one at a time.

Run from the repository root after changing app/context/:
    python3 tests/mutants/make_mutants.py
A replacement that no longer matches fails loudly: update the mutant, never
drop it.
"""

from __future__ import annotations

import difflib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
T = "tests/context"
HOME = f"{T}/home/test_home.py::"
KEY = "tests/test_device_key_tpm.py::"

MUTANTS: dict[str, dict] = {
    # B-1: block_id is computed from exactly the encrypted plaintext.
    "CTX-B1-1": {
        "why": "block_id is taken from the file path",
        "tests": [f"{T}/test_blocks.py", f"{T}/test_manifests.py"],
        "edits": [
            ("app/context/blocks.py",
             "def encrypt_block(plaintext: bytes, context: Context) -> tuple[str, bytes]:",
             "def encrypt_block(plaintext: bytes, context: Context, path: str = \"\") -> tuple[str, bytes]:"),
            ("app/context/blocks.py",
             "    block_id = _block_id(plaintext, context)\n    return block_id, seal(",
             "    block_id = sha256(path.encode()).hexdigest() if path else _block_id(plaintext, context)\n"
             "    return block_id, seal("),
            ("app/context/home.py",
             "            block_id, block = encrypt_block(piece, self.context)",
             "            block_id, block = encrypt_block(piece, self.context, path)"),
        ],
    },
    "CTX-B1-2": {
        "why": "block_id is taken from a sequence number",
        "tests": [f"{T}/test_blocks.py"],
        "edits": [
            ("app/context/blocks.py",
             "    block_id = _block_id(plaintext, context)\n    return block_id, seal(",
             "    global _SEQ\n    _SEQ += 1\n    block_id = sha256(str(_SEQ).encode()).hexdigest()\n"
             "    return block_id, seal("),
            ("app/context/blocks.py", "_HEADER = 1 + SALT_SIZE + NONCE_SIZE\n",
             "_HEADER = 1 + SALT_SIZE + NONCE_SIZE\n_SEQ = 0\n"),
        ],
    },
    "CTX-B1-3": {
        "why": "the HMAC check on read is removed",
        "tests": [f"{T}/test_blocks.py"],
        "edits": [
            ("app/context/blocks.py",
             "    if not hmac.compare_digest(_block_id(plaintext, context), block_id):",
             "    if False:"),
        ],
    },
    "CTX-B1-4": {
        "why": "encrypt_block gets an optional block_id parameter",
        "tests": [f"{T}/test_blocks.py"],
        "edits": [
            ("app/context/blocks.py",
             "def encrypt_block(plaintext: bytes, context: Context) -> tuple[str, bytes]:",
             "def encrypt_block(plaintext: bytes, context: Context, block_id: str | None = None) -> tuple[str, bytes]:"),
            ("app/context/blocks.py",
             "    block_id = _block_id(plaintext, context)\n    return block_id, seal(",
             "    block_id = block_id or _block_id(plaintext, context)\n    return block_id, seal("),
        ],
    },
    # B-2: fresh salt and nonce on every encryption.
    "CTX-B2-1": {
        "why": "a fixed nonce",
        "tests": [f"{T}/test_blocks.py"],
        "edits": [("app/context/blocks.py", "    nonce = os.urandom(NONCE_SIZE)\n", "    nonce = bytes(NONCE_SIZE)\n")],
    },
    "CTX-B2-2": {
        "why": "the salt is reused per context",
        "tests": [f"{T}/test_blocks.py"],
        "edits": [
            ("app/context/blocks.py", "    salt = os.urandom(SALT_SIZE)\n",
             "    salt = _SALTS.setdefault(context.context_id, os.urandom(SALT_SIZE))\n"),
            ("app/context/blocks.py", "_HEADER = 1 + SALT_SIZE + NONCE_SIZE\n",
             "_HEADER = 1 + SALT_SIZE + NONCE_SIZE\n_SALTS: dict = {}\n"),
        ],
    },
    "CTX-B2-3": {
        "why": "the nonce is derived from block_id",
        "tests": [f"{T}/test_blocks.py"],
        "edits": [("app/context/blocks.py", "    nonce = os.urandom(NONCE_SIZE)\n",
                   "    nonce = sha256(name.encode()).digest()[:NONCE_SIZE]\n")],
    },
    # B-3: the AAD binds context_id and block_id.
    "CTX-B3-1": {
        "why": "AAD without context_id",
        "tests": [f"{T}/test_blocks.py"],
        "edits": [("app/context/blocks.py", "    aad = (label + context.context_id + name).encode()\n",
                   "    aad = (label + name).encode()\n", 2)],
    },
    "CTX-B3-2": {
        "why": "AAD without block_id",
        "tests": [f"{T}/test_blocks.py"],
        "edits": [("app/context/blocks.py", "    aad = (label + context.context_id + name).encode()\n",
                   "    aad = (label + context.context_id).encode()\n", 2)],
    },
    "CTX-B3-3": {
        "why": "empty AAD",
        "tests": [f"{T}/test_blocks.py"],
        "edits": [("app/context/blocks.py", "    aad = (label + context.context_id + name).encode()\n",
                   "    aad = b\"\"\n", 2)],
    },
    # M-1: unknown or tampered manifests are ignored and audited.
    "CTX-M1-1": {
        "why": "the signature check is removed",
        "tests": [f"{T}/test_manifests.py"],
        "edits": [("app/context/manifest.py", "    if not verify(key, signature, sealed):\n",
                   "    if False:\n")],
    },
    "CTX-M1-2": {
        "why": "the Merkle check is removed",
        "tests": [f"{T}/test_manifests.py"],
        "edits": [("app/context/manifest.py",
                   "    if manifest[\"merkle_root\"] != merkle_root(manifest_block_ids(manifest)):\n",
                   "    if False:\n")],
    },
    "CTX-M1-3": {
        "why": "the current device list is fetched but not used to judge the new one",
        "tests": [f"{T}/test_manifests.py"],
        "edits": [("app/context/devices.py", "        signer = current.key_of(signer_name)\n",
                   "        signer = keys.get(signer_name)\n")],
    },
    "CTX-M1-4": {
        "why": "the audit event is left out (the test needs ignored *and* audited)",
        "tests": [f"{T}/test_manifests.py"],
        "edits": [("app/context/manifest.py",
                   "        audit(\"context.manifest_ignored\", {\"context_id\": context.context_id, \"manifest\": name,\n"
                   "                                           \"reason\": reason})\n",
                   "        pass\n")],
    },
    # U-1: a Linux UID never leaves the device.
    "CTX-U1-1": {
        "why": "uid is added to the manifest",
        "tests": [f"{T}/test_uid.py"],
        "edits": [
            ("app/context/manifest.py", "                 \"files\", \"documents\", \"merkle_root\"}",
             "                 \"files\", \"documents\", \"merkle_root\", \"uid\"}"),
            ("app/context/home.py", "            \"merkle_root\": \"\",\n",
             "            \"merkle_root\": \"\",\n            \"uid\": os.getuid(),\n"),
        ],
    },
    # X-1: the exit guarantee.
    "CTX-X1-1": {
        "why": "EiraOS writes something only EiraOS understands (compressed file data)",
        "tests": [f"{T}/test_export.py"],
        "edits": [("app/context/home.py", "        for piece in chunks(data):\n",
                   "        import zlib\n        for piece in chunks(zlib.compress(data)):\n")],
    },
    # H-1: an existing object is never overwritten; a home that cannot
    # promise that is refused before use.
    "CTX-H1-1": {
        "why": "S3 PUT is sent without If-None-Match",
        "tests": [HOME + "test_h1_a_an_existing_block_is_never_overwritten"],
        "edits": [("app/context/remote.py",
                   'self._signed("PUT", self._path(name), data, {"If-None-Match": "*"})',
                   'self._signed("PUT", self._path(name), data, {})')],
    },
    "CTX-H1-2": {
        "why": "WebDAV PUT is sent without If-None-Match",
        "tests": [HOME + "test_h1_a_an_existing_block_is_never_overwritten"],
        "edits": [("app/context/remote.py",
                   'content=data, headers={"If-None-Match": "*"})',
                   'content=data, headers={})')],
    },
    "CTX-H1-3": {
        "why": "attach trusts a 412 without reading the probe back",
        "tests": [HOME + "test_h1_c_a_home_that_overwrites_is_refused"],
        "edits": [("app/context/remote.py", "        if home.get(probe) != first:", "        if False:")],
    },
    "CTX-H1-4": {
        "why": "a manifest collision is ignored instead of refused",
        "tests": [HOME + "test_h1_d_a_second_manifest_at_the_same_path_is_refused_and_audited"],
        "edits": [("app/context/home.py",
                   '            raise ContextError(E_CONTEXT_INTEGRITY, f"manifest {name} already exists")',
                   '            pass')],
    },
    # A-1 (EIRA-CONTEXT §5.0): the device key is made in the TPM and cannot
    # leave it. CTX-A1-6 (software key imported into the TPM) needs an import
    # path tpm2-openssl does not offer; it stays for N3. CTX-A1-1, -3, -4, -5
    # belong to F2.4 (sealing) and Fleet.
    "CTX-A1-2": {
        "why": "the device key is made in software and written as a file",
        "tests": [KEY + "test_t_a1_f_the_key_is_a_tpm_blob_that_cannot_be_exported"],
        "edits": [
            ("app/rights/devicekey.py",
             '_openssl("genpkey", *PROVIDERS, "-propquery", "?provider=tpm2", "-algorithm", "EC",',
             '_openssl("genpkey", "-algorithm", "EC",'),
            ("app/rights/devicekey.py", "        if not path.read_bytes().startswith(TSS2_HEADER):",
             "        if False:"),
            ("app/rights/devicekey.py", "        missing = REQUIRED_ATTRIBUTES - attributes(path)",
             "        missing = set()"),
        ],
    },
    "CTX-A1-8": {
        "why": "with the installed OPENSSL_CONF the default provider makes the key",
        "tests": [KEY + "test_the_key_is_made_in_the_tpm_with_the_installed_openssl_conf"],
        "edits": [
            ("app/rights/devicekey.py", '*PROVIDERS, "-propquery", "?provider=tpm2", "-algorithm"',
             '*PROVIDERS, "-algorithm"'),
        ],
    },
    "CTX-A1-7": {
        "why": "a device without a TPM is enrolled anyway",
        "tests": [KEY + "test_t_a1_g_enroll_without_a_tpm_writes_nothing_and_exits_2"],
        "edits": [
            ("app/rights/enroll.py", "    if not devicekey.tpm_present():  # before anything is written",
             "    if False:  # before anything is written"),
            ("app/rights/devicekey.py",
             "    if not tpm_present():\n        raise NoTpm(\"this device has no TPM 2.0; managed requires one\")\n",
             ""),
        ],
    },
}


def main() -> None:
    for old in OUT.glob("CTX-*.patch"):
        old.unlink()
    for name, mutant in MUTANTS.items():
        changed: dict[str, str] = {}
        for edit in mutant["edits"]:
            path, before, after = edit[:3]
            count = edit[3] if len(edit) > 3 else 1
            text = changed.get(path) or (ROOT / path).read_text(encoding="utf-8")
            found = text.count(before)
            if found != count:
                raise SystemExit(f"{name}: expected {count} match(es) in {path}, found {found}: {before!r}")
            changed[path] = text.replace(before, after)
        diff = []
        for path, text in sorted(changed.items()):
            original = (ROOT / path).read_text(encoding="utf-8")
            diff += difflib.unified_diff(original.splitlines(keepends=True), text.splitlines(keepends=True),
                                         fromfile=f"a/{path}", tofile=f"b/{path}")
        header = f"Mutant {name}: {mutant['why']}\nTests: {' '.join(mutant['tests'])}\n\n"
        (OUT / f"{name}.patch").write_text(header + "".join(diff), encoding="utf-8")
    print(f"{len(MUTANTS)} mutants written to {OUT}")


if __name__ == "__main__":
    main()
