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

for tool in lb python3 xorriso mksquashfs; do
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
        --mirror-bootstrap https://archive.ubuntu.com/ubuntu \
        --mirror-chroot https://archive.ubuntu.com/ubuntu \
        --security true \
        --updates true \
        --iso-application "EiraOS 1.0 RC1" \
        --iso-publisher "EiraOS" \
        --bootappend-live "boot=live components quiet splash"

    mkdir -p \
        config/package-lists \
        config/packages.chroot \
        config/hooks/live \
        config/includes.chroot/etc/greetd \
        config/includes.chroot/etc/labwc
    install -m 0644 -- "$DEB_PATH" config/packages.chroot/eira-os-core.deb
    # live-build hooks execute inside the chroot, where repository source files
    # are not present. Stage session configuration as chroot includes instead.
    install -m 0644 -- \
        "${REPO_ROOT}/packaging/session/config/greetd/config.toml" \
        config/includes.chroot/etc/greetd/config.toml
    install -m 0644 -- \
        "${REPO_ROOT}/packaging/session/config/labwc/rc.xml" \
        config/includes.chroot/etc/labwc/rc.xml
    install -m 0755 -- \
        "${REPO_ROOT}/packaging/session/config/labwc/autostart" \
        config/includes.chroot/etc/labwc/autostart

    cat > config/package-lists/eira-os.list.chroot <<'EOF'
ubuntu-desktop-minimal
labwc
greetd
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
systemctl enable greetd.service
install -d -m 0755 /etc/greetd /etc/labwc
# The live user may be created by casper only at boot. Add it to the
# supplementary group even when the account does not yet exist in the build
# chroot, so it can access the group-restricted EiraOS IPC sockets.
python3 - <<'PYGROUP'
from pathlib import Path

group_file = Path("/etc/group")
lines = group_file.read_text(encoding="utf-8").splitlines()
for index, line in enumerate(lines):
    fields = line.split(":")
    if fields[0] != "eira":
        continue
    members = [member for member in fields[3].split(",") if member]
    if "ubuntu" not in members:
        members.append("ubuntu")
    fields[3] = ",".join(members)
    lines[index] = ":".join(fields)
    group_file.write_text("\\n".join(lines) + "\\n", encoding="utf-8")
    break
else:
    raise SystemExit("eira group missing after package installation")
PYGROUP
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

SOURCE_COMMIT=${EIRA_SOURCE_COMMIT:-}
if [[ -z $SOURCE_COMMIT ]] && command -v git >/dev/null 2>&1; then
    SOURCE_COMMIT=$(git -C "$REPO_ROOT" rev-parse HEAD 2>/dev/null || true)
fi
SOURCE_COMMIT=${SOURCE_COMMIT:-unknown}
python3 - "$ISO_OUTPUT" "$DEB_PATH" "$SOURCE_COMMIT" "${ISO_OUTPUT}.build-info.json" <<'PY'
import hashlib
import json
import pathlib
import subprocess
import sys
from datetime import datetime, timezone

iso_path = pathlib.Path(sys.argv[1])
deb_path = pathlib.Path(sys.argv[2])
source_commit = sys.argv[3]
manifest_path = pathlib.Path(sys.argv[4])


def sha3(path):
    digest = hashlib.sha3_256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def tool_version(command):
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, check=False, timeout=10
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"unavailable: {exc}"
    output = (result.stdout + result.stderr).strip().splitlines()
    return output[0] if output else f"exit={result.returncode}"


manifest = {
    "format": "eira-iso-build-info-v1",
    "source_commit": source_commit,
    "source_commit_verified": source_commit != "unknown",
    "base_distribution": "Ubuntu 24.04 LTS (noble)",
    "architecture": "amd64",
    "built_at_utc": datetime.now(timezone.utc).isoformat(),
    "inputs": [{"name": deb_path.name, "sha3_256": sha3(deb_path), "size": deb_path.stat().st_size}],
    "outputs": [{"name": iso_path.name, "sha3_256": sha3(iso_path), "size": iso_path.stat().st_size}],
    "tools": {
        "live_build": tool_version(["lb", "--version"]),
        "xorriso": tool_version(["xorriso", "-version"]),
        "mksquashfs": tool_version(["mksquashfs", "-version"]),
    },
}
manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY
echo "Built $ISO_OUTPUT"
echo "Build provenance: ${ISO_OUTPUT}.build-info.json"
