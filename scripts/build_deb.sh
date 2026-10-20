#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd -- "${SCRIPT_DIR}/.." && pwd)
OUTPUT_DIR=${EIRA_DEB_OUTPUT_DIR:-${REPO_ROOT}/dist}

usage() {
    echo "Usage: $0 [--output-dir DIR]" >&2
}

while (($#)); do
    case "$1" in
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

for tool in dpkg-buildpackage dpkg-deb python3; do
    command -v "$tool" >/dev/null 2>&1 || {
        echo "Missing required build tool: $tool" >&2
        exit 69
    }
done

BUILD_ROOT=$(mktemp -d -t eira-deb-build.XXXXXXXX)
SOURCE_ROOT=${BUILD_ROOT}/eira-os-core-1.0~rc1
cleanup() {
    rm -rf -- "$BUILD_ROOT"
}
trap cleanup EXIT INT TERM

mkdir -p -- "$SOURCE_ROOT" "$OUTPUT_DIR"
cp -a -- "${REPO_ROOT}/." "$SOURCE_ROOT/"
rm -rf -- \
    "${SOURCE_ROOT}/.pytest_cache" \
    "${SOURCE_ROOT}/.ruff_cache" \
    "${SOURCE_ROOT}/dist" \
    "${SOURCE_ROOT}/ui/dist" \
    "${SOURCE_ROOT}/ui/node_modules"
find "$SOURCE_ROOT" -type d -name __pycache__ -prune -exec rm -rf -- {} +
cp -a -- "${SOURCE_ROOT}/packaging/debian" "${SOURCE_ROOT}/debian"

(
    cd -- "$SOURCE_ROOT"
    dpkg-buildpackage --build=binary --no-sign
)

shopt -s nullglob
packages=("${BUILD_ROOT}"/eira-os-core_*.deb)
if ((${#packages[@]} != 1)); then
    echo "Expected exactly one eira-os-core package, found ${#packages[@]}" >&2
    exit 70
fi
install -m 0644 -- "${packages[0]}" "$OUTPUT_DIR/"
install -m 0644 -- "${packages[0]}" "$OUTPUT_DIR/eira-os-core.deb"

SOURCE_COMMIT=${EIRA_SOURCE_COMMIT:-}
if [[ -z $SOURCE_COMMIT ]] && command -v git >/dev/null 2>&1; then
    SOURCE_COMMIT=$(git -C "$REPO_ROOT" rev-parse HEAD 2>/dev/null || true)
fi
SOURCE_COMMIT=${SOURCE_COMMIT:-unknown}
python3 - "$OUTPUT_DIR/eira-os-core.deb" "$SOURCE_COMMIT" \
    "$OUTPUT_DIR/eira-os-core.deb.build-info.json" <<'PY'
import hashlib
import json
import pathlib
import subprocess
import sys
from datetime import datetime, timezone

package = pathlib.Path(sys.argv[1])
source_commit = sys.argv[2]
manifest_path = pathlib.Path(sys.argv[3])


def sha3(path):
    digest = hashlib.sha3_256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def output(command):
    result = subprocess.run(command, capture_output=True, text=True, check=False, timeout=10)
    text = (result.stdout + result.stderr).strip().splitlines()
    return text[0] if text else f"exit={result.returncode}"


manifest = {
    "format": "eira-deb-build-info-v1",
    "source_commit": source_commit,
    "source_commit_verified": source_commit != "unknown",
    "package": {
        "name": output(["dpkg-deb", "-f", str(package), "Package"]),
        "version": output(["dpkg-deb", "-f", str(package), "Version"]),
        "architecture": output(["dpkg-deb", "-f", str(package), "Architecture"]),
        "file": package.name,
        "sha3_256": sha3(package),
        "size": package.stat().st_size,
    },
    "built_at_utc": datetime.now(timezone.utc).isoformat(),
    "tools": {
        "dpkg_buildpackage": output(["dpkg-buildpackage", "--version"]),
        "python": output([sys.executable, "--version"]),
    },
}
manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\\n", encoding="utf-8")
PY
echo "Built $OUTPUT_DIR/eira-os-core.deb"
echo "Build provenance: $OUTPUT_DIR/eira-os-core.deb.build-info.json"
