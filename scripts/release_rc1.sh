#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd -- "${SCRIPT_DIR}/.." && pwd)
OUTPUT_DIR=${EIRA_RELEASE_OUTPUT_DIR:-${REPO_ROOT}/dist/release}
ARTIFACTS_DIR=
GPG_KEY=${EIRA_RELEASE_GPG_KEY:-}
VERSION=1.0-RC1

usage() {
    cat >&2 <<'EOF'
Usage: release_rc1.sh --gpg-key KEY [--artifacts-dir DIR] [--output-dir DIR]

Runs every production gate, builds or verifies the .deb and ISO, creates a
SHA3-256 manifest, and produces a detached armored GPG signature. There is no
skip-tests mode for a pilot release candidate.
EOF
}

while (($#)); do
    case "$1" in
        --gpg-key)
            [[ $# -ge 2 ]] || { usage; exit 64; }
            GPG_KEY=$2
            shift 2
            ;;
        --artifacts-dir)
            [[ $# -ge 2 ]] || { usage; exit 64; }
            ARTIFACTS_DIR=$2
            shift 2
            ;;
        --output-dir)
            [[ $# -ge 2 ]] || { usage; exit 64; }
            OUTPUT_DIR=$2
            shift 2
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            usage
            exit 64
            ;;
    esac
done

[[ -n $GPG_KEY ]] || { echo "--gpg-key is required" >&2; exit 64; }

for tool in apparmor_parser cargo dpkg-deb gpg gradle npm python3 systemd-analyze tar xorriso; do
    command -v "$tool" >/dev/null 2>&1 || {
        echo "Production release tool missing: $tool" >&2
        exit 69
    }
done

python3 - <<'PY'
import socket
import tempfile
from pathlib import Path

with tempfile.TemporaryDirectory(prefix="eira-rc-socket-") as directory:
    path = Path(directory) / "gate.sock"
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        server.bind(str(path))
    finally:
        server.close()
PY

(
    cd -- "$REPO_ROOT"
    export EIRA_RELEASE_GATE=1
    export PYTHONPATH=.
    python3 -m pytest -q
    python3 -m ruff check app tests scripts
    npm ci --prefix ui --ignore-scripts
    npm test --prefix ui
    npm run build --prefix ui
    cargo test --workspace --all-targets
    cargo test --manifest-path ui/src-tauri/Cargo.toml --all-targets
    gradle --project-dir android test
    apparmor_parser -Q -q packaging/apparmor/usr.bin.eira-*
    systemd-analyze verify systemd/eira-*.service systemd/eira.target
)

if [[ -z $ARTIFACTS_DIR ]]; then
    ARTIFACTS_DIR=$(mktemp -d -t eira-rc-artifacts.XXXXXXXX)
    REMOVE_ARTIFACTS=1
    "${SCRIPT_DIR}/build_deb.sh" --output-dir "$ARTIFACTS_DIR"
    "${SCRIPT_DIR}/build_iso.sh" \
        --deb "${ARTIFACTS_DIR}/eira-os-core.deb" \
        --output-dir "$ARTIFACTS_DIR"
else
    REMOVE_ARTIFACTS=0
    ARTIFACTS_DIR=$(realpath -- "$ARTIFACTS_DIR")
fi

RELEASE_WORK=$(mktemp -d -t eira-rc-bundle.XXXXXXXX)
cleanup() {
    rm -rf -- "$RELEASE_WORK"
    if [[ ${REMOVE_ARTIFACTS:-0} -eq 1 ]]; then
        rm -rf -- "$ARTIFACTS_DIR"
    fi
}
trap cleanup EXIT INT TERM

DEB=${ARTIFACTS_DIR}/eira-os-core.deb
ISO=${ARTIFACTS_DIR}/EiraOS-${VERSION}-amd64.iso
for artifact in "$DEB" "$ISO"; do
    [[ -f $artifact && ! -L $artifact ]] || {
        echo "Required release artifact missing or unsafe: $artifact" >&2
        exit 66
    }
done
dpkg-deb --info "$DEB" >/dev/null
xorriso -indev "$ISO" -toc >/dev/null 2>&1

STAGE=${RELEASE_WORK}/EiraOS-${VERSION}
mkdir -p -- "$STAGE"
install -m 0644 -- "$DEB" "$ISO" "$STAGE/"
install -m 0644 -- \
    "${REPO_ROOT}/docs/EIRA_Sprint9_Execution_Prompts.md" \
    "${REPO_ROOT}/docs/EIRA_Sprint10_Execution_Prompts.md" \
    "$STAGE/"

python3 - "$STAGE" <<'PY'
import hashlib
import json
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
files = []
for path in sorted(item for item in root.iterdir() if item.is_file()):
    digest = hashlib.sha3_256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    files.append({"name": path.name, "sha3_256": digest.hexdigest(), "size": path.stat().st_size})
manifest = {"format": "eira-release-manifest-v1", "version": "1.0-RC1", "files": files}
(root / "MANIFEST.json").write_text(
    json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n",
    encoding="utf-8",
)
PY

mkdir -p -- "$OUTPUT_DIR"
OUTPUT_DIR=$(realpath -- "$OUTPUT_DIR")
BUNDLE=${OUTPUT_DIR}/EiraOS-${VERSION}.tar.gz
SOURCE_DATE_EPOCH=${SOURCE_DATE_EPOCH:-1785588000}
tar --sort=name --owner=0 --group=0 --numeric-owner \
    --mtime="@${SOURCE_DATE_EPOCH}" -C "$RELEASE_WORK" \
    -czf "$BUNDLE" "EiraOS-${VERSION}"
gpg --batch --yes --local-user "$GPG_KEY" --armor --detach-sign "$BUNDLE"
gpg --batch --verify "${BUNDLE}.asc" "$BUNDLE" >/dev/null 2>&1

python3 - "$BUNDLE" > "${BUNDLE}.sha3-256" <<'PY'
import hashlib
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
digest = hashlib.sha3_256(path.read_bytes()).hexdigest()
print(f"{digest}  {path.name}")
PY

echo "Release candidate created: $BUNDLE"
echo "Detached signature: ${BUNDLE}.asc"
