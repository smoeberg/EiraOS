#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd -- "${SCRIPT_DIR}/.." && pwd)
OUTPUT_DIR=${EIRA_ISO_OUTPUT_DIR:-${REPO_ROOT}/dist}
WORK_DIR=
DEB_PATH=
KEEP_WORK=0

usage() {
    cat >&2 <<'EOF'
Usage: build_iso.sh [--deb PATH] [--output-dir DIR] [--work-dir DIR] [--keep-work]

Builds an amd64 Ubuntu 24.04 LTS live ISO with eira-os-core installed.
If --deb is omitted, scripts/build_deb.sh creates the package first.
EOF
}

while (($#)); do
    case "$1" in
        --deb)
            [[ $# -ge 2 ]] || { usage; exit 64; }
            DEB_PATH=$2
            shift 2
            ;;
        --output-dir)
            [[ $# -ge 2 ]] || { usage; exit 64; }
            OUTPUT_DIR=$2
            shift 2
            ;;
        --work-dir)
            [[ $# -ge 2 ]] || { usage; exit 64; }
            WORK_DIR=$2
            shift 2
            ;;
        --keep-work)
            KEEP_WORK=1
            shift
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

for tool in lb python3; do
    command -v "$tool" >/dev/null 2>&1 || {
        echo "Missing required ISO tool: $tool" >&2
        echo "Install live-build, xorriso and squashfs-tools on Ubuntu 24.04." >&2
        exit 69
    }
done

mkdir -p -- "$OUTPUT_DIR"
if [[ -z $DEB_PATH ]]; then
    "${SCRIPT_DIR}/build_deb.sh" --output-dir "$OUTPUT_DIR"
    DEB_PATH=${OUTPUT_DIR}/eira-os-core.deb
fi
[[ -f $DEB_PATH ]] || { echo "Package not found: $DEB_PATH" >&2; exit 66; }
DEB_PATH=$(realpath -- "$DEB_PATH")

CREATED_WORK=0
if [[ -z $WORK_DIR ]]; then
    WORK_DIR=$(mktemp -d -t eira-live-build.XXXXXXXX)
    CREATED_WORK=1
else
    mkdir -p -- "$WORK_DIR"
    WORK_DIR=$(realpath -- "$WORK_DIR")
    if [[ -n $(find "$WORK_DIR" -mindepth 1 -maxdepth 1 -print -quit) ]]; then
        echo "Work directory must be empty: $WORK_DIR" >&2
        exit 73
    fi
fi

cleanup() {
    if [[ $CREATED_WORK -eq 1 && $KEEP_WORK -eq 0 ]]; then
        rm -rf -- "$WORK_DIR"
    else
        echo "Live-build work directory retained at $WORK_DIR" >&2
    fi
}
trap cleanup EXIT INT TERM

(
    cd -- "$WORK_DIR"
    lb config \
        --mode ubuntu \
        --distribution noble \
        --architectures amd64 \
        --binary-images iso-hybrid \
        --archive-areas "main universe" \
        --mirror-bootstrap http://archive.ubuntu.com/ubuntu \
        --mirror-chroot http://archive.ubuntu.com/ubuntu \
        --security true \
        --updates true \
        --iso-application "EiraOS 1.0 RC1" \
        --iso-publisher "EiraOS" \
        --bootappend-live "boot=live components quiet splash"

    mkdir -p config/package-lists config/packages.chroot config/hooks/live
    install -m 0644 -- "$DEB_PATH" config/packages.chroot/eira-os-core.deb

    cat > config/package-lists/eira-os.list.chroot <<'EOF'
ubuntu-desktop-minimal
gdm3
apparmor
apparmor-utils
ca-certificates
network-manager
sudo
EOF

    cat > config/hooks/live/050-eira-session.hook.chroot <<'EOF'
#!/bin/sh
set -eu
systemctl enable eira.target
if id ubuntu >/dev/null 2>&1; then
    adduser ubuntu eira
fi
EOF
    chmod 0755 config/hooks/live/050-eira-session.hook.chroot

    if [[ ${EUID} -eq 0 ]]; then
        lb build
    elif command -v sudo >/dev/null 2>&1; then
        sudo lb build
    else
        echo "live-build requires root; install sudo or run this script as root" >&2
        exit 77
    fi
)

ISO_SOURCE=$(find "$WORK_DIR" -maxdepth 1 -type f -name '*.hybrid.iso' -print -quit)
[[ -n $ISO_SOURCE ]] || ISO_SOURCE=$(find "$WORK_DIR" -maxdepth 1 -type f -name '*.iso' -print -quit)
[[ -n $ISO_SOURCE ]] || { echo "live-build produced no ISO" >&2; exit 70; }

ISO_OUTPUT=${OUTPUT_DIR}/EiraOS-1.0-RC1-amd64.iso
install -m 0644 -- "$ISO_SOURCE" "$ISO_OUTPUT"
python3 - "$ISO_OUTPUT" > "${ISO_OUTPUT}.sha3-256" <<'PY'
import hashlib
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
digest = hashlib.sha3_256()
with path.open("rb") as handle:
    for chunk in iter(lambda: handle.read(1024 * 1024), b""):
        digest.update(chunk)
print(f"{digest.hexdigest()}  {path.name}")
PY
echo "Built $ISO_OUTPUT"
