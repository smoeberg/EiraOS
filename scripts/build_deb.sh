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

for tool in dpkg-buildpackage python3; do
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
echo "Built ${OUTPUT_DIR}/eira-os-core.deb"
