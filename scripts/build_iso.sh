#!/usr/bin/env bash
# Builds the installable EiraOS ISO.
#
# The official Ubuntu Desktop 26.04 LTS ISO is remastered: eira-os-core, the
# post-install/first-boot scripts and an autoinstall file are added, and the
# original El Torito/GPT boot records are replayed unchanged. The result boots
# Ubuntu's own installer, which asks for language, keyboard, network, disk and
# user, installs Ubuntu Desktop and then EiraOS on top. No root is needed.
#
# --ci-unattended builds a TEST image instead: it installs without asking and
# WIPES THE FIRST DISK, then runs a boot acceptance check. CI/VM use only.
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd -- "${SCRIPT_DIR}/.." && pwd)
OUTPUT_DIR=${EIRA_ISO_OUTPUT_DIR:-${REPO_ROOT}/dist}
BASE_ISO=${EIRA_BASE_ISO:-}
WORK_DIR=
DEB_PATH=
LABWC_DEB_PATH=
KEEP_WORK=0
CI_UNATTENDED=0
OFFLINE_REPO=

usage() {
    cat >&2 <<'USAGE'
Usage: build_iso.sh --base-iso PATH [--deb PATH] [--labwc-deb PATH] [--output-dir DIR] [--work-dir DIR]
                    [--keep-work] [--ci-unattended [--offline-repo DIR]]

Builds an installable amd64 EiraOS ISO from the official Ubuntu Desktop
26.04 LTS ISO (fetch and verify it with scripts/fetch_ubuntu_iso.sh).
--ci-unattended: test image that wipes the first disk without asking (VM only).
--offline-repo: with --ci-unattended, a local apt repository (scripts/
  build_offline_repo.sh) put on the image as /eira/repo, so the VM installs
  without network.
If --deb is omitted, scripts/build_deb.sh creates the package first.
If --labwc-deb is omitted, packaging/eira-labwc/build.sh builds eira-labwc
(labwc >= 0.20.3, required by the session; EIRA-CONSENT-AGENT R-6.1).
EIRA_BASE_ISO may be used instead of --base-iso.
USAGE
}

while (($#)); do
    case "$1" in
        --base-iso)
            [[ $# -ge 2 ]] || { usage; exit 64; }
            BASE_ISO=$2
            shift 2
            ;;
        --deb)
            [[ $# -ge 2 ]] || { usage; exit 64; }
            DEB_PATH=$2
            shift 2
            ;;
        --labwc-deb)
            [[ $# -ge 2 ]] || { usage; exit 64; }
            LABWC_DEB_PATH=$2
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
        --ci-unattended)
            CI_UNATTENDED=1
            shift
            ;;
        --offline-repo)
            [[ $# -ge 2 ]] || { usage; exit 64; }
            OFFLINE_REPO=$2
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

for tool in xorriso python3; do
    command -v "$tool" >/dev/null 2>&1 || {
        echo "Missing required ISO tool: $tool (apt install xorriso python3)" >&2
        exit 69
    }
done

[[ -n $BASE_ISO ]] || {
    echo "No base ISO given. Run scripts/fetch_ubuntu_iso.sh and pass --base-iso." >&2
    usage
    exit 64
}
[[ -f $BASE_ISO && ! -L $BASE_ISO ]] || { echo "Base ISO not found: $BASE_ISO" >&2; exit 66; }
BASE_ISO=$(realpath -- "$BASE_ISO")

mkdir -p -- "$OUTPUT_DIR"
OUTPUT_DIR=$(realpath -- "$OUTPUT_DIR")
if [[ -z $DEB_PATH ]]; then
    "${SCRIPT_DIR}/build_deb.sh" --output-dir "$OUTPUT_DIR"
    DEB_PATH=${OUTPUT_DIR}/eira-os-core.deb
fi
[[ -f $DEB_PATH ]] || { echo "Package not found: $DEB_PATH" >&2; exit 66; }
DEB_PATH=$(realpath -- "$DEB_PATH")
if [[ -z $LABWC_DEB_PATH ]]; then
    "${REPO_ROOT}/packaging/eira-labwc/build.sh" --output-dir "$OUTPUT_DIR"
    LABWC_DEB_PATH=${OUTPUT_DIR}/eira-labwc.deb
fi
[[ -f $LABWC_DEB_PATH ]] || { echo "Package not found: $LABWC_DEB_PATH" >&2; exit 66; }
LABWC_DEB_PATH=$(realpath -- "$LABWC_DEB_PATH")

CREATED_WORK=0
if [[ -z $WORK_DIR ]]; then
    WORK_DIR=$(mktemp -d -t eira-iso.XXXXXXXX)
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
        echo "ISO work directory retained at $WORK_DIR" >&2
    fi
}
trap cleanup EXIT INT TERM

INSTALLER=${REPO_ROOT}/packaging/installer
STAGE=${WORK_DIR}/stage
install -d -m 0755 "$STAGE/eira"
install -m 0644 -- "$DEB_PATH" "$STAGE/eira/eira-os-core.deb"
install -m 0644 -- "$LABWC_DEB_PATH" "$STAGE/eira/eira-labwc.deb"
install -m 0755 -- "$INSTALLER/eira-postinstall.sh" "$STAGE/eira/eira-postinstall.sh"
install -m 0755 -- "$INSTALLER/eira-firstboot" "$STAGE/eira/eira-firstboot"
install -m 0644 -- "$INSTALLER/eira-firstboot.service" "$STAGE/eira/eira-firstboot.service"
if [[ $CI_UNATTENDED -eq 1 ]]; then
    install -d -m 0755 "$STAGE/eira/ci"
    install -m 0755 -- "$INSTALLER/ci/eira-ci-setup" "$STAGE/eira/ci/eira-ci-setup"
    install -m 0755 -- "$INSTALLER/ci/eira-ci-report" "$STAGE/eira/ci/eira-ci-report"
    install -m 0755 -- "$INSTALLER/ci/eira-ci-install-failed" "$STAGE/eira/ci/eira-ci-install-failed"
    install -m 0644 -- "$INSTALLER/ci/eira-ci-report.service" "$STAGE/eira/ci/eira-ci-report.service"
    install -m 0644 -- "$INSTALLER/ci/autoinstall-ci.yaml" "$STAGE/autoinstall.yaml"
    if [[ -n $OFFLINE_REPO ]]; then
        [[ -f $OFFLINE_REPO/Packages.gz ]] || { echo "Not an offline repo: $OFFLINE_REPO" >&2; exit 66; }
        cp -r -- "$OFFLINE_REPO" "$STAGE/eira/repo"
    fi
    ISO_NAME=EiraOS-1.0-RC1-amd64-ci-unattended.iso
else
    [[ -z $OFFLINE_REPO ]] || { echo "--offline-repo is for the CI image only" >&2; exit 64; }
    install -m 0644 -- "$INSTALLER/autoinstall.yaml" "$STAGE/autoinstall.yaml"
    ISO_NAME=EiraOS-1.0-RC1-amd64.iso
fi

# Rename the default boot entry. The CI image also boots it immediately and
# passes 'autoinstall', so the installer starts without asking for confirmation.
xorriso -osirrox on -indev "$BASE_ISO" \
    -extract /boot/grub/grub.cfg "$STAGE/grub.cfg" >/dev/null 2>&1 || {
    echo "Base ISO has no /boot/grub/grub.cfg; is it an Ubuntu installer ISO?" >&2
    exit 65
}
chmod u+w "$STAGE/grub.cfg"
if grep -qE 'menuentry "Try or Install Ubuntu[^"]*"' "$STAGE/grub.cfg"; then
    sed -i -E '0,/menuentry "Try or Install Ubuntu[^"]*"/s//menuentry "Installér EiraOS (Ubuntu 26.04 LTS)"/' "$STAGE/grub.cfg"
else
    echo "Warning: default GRUB entry not found; boot menu keeps Ubuntu's title" >&2
fi
if [[ $CI_UNATTENDED -eq 1 ]]; then
    sed -i -E 's/^set timeout=.*/set timeout=1/' "$STAGE/grub.cfg"
    sed -i -E '0,/^([[:space:]]*linux[[:space:]].*) ---/s//\1 autoinstall console=tty0 console=ttyS0,115200 ---/' "$STAGE/grub.cfg"
    grep -q ' autoinstall console=tty0 console=ttyS0,115200 ---' "$STAGE/grub.cfg" || {
        echo "Could not add 'autoinstall' to the kernel command line" >&2
        exit 65
    }
fi

ISO_OUTPUT=${OUTPUT_DIR}/${ISO_NAME}
rm -f -- "$ISO_OUTPUT"
xorriso -indev "$BASE_ISO" -outdev "$ISO_OUTPUT" \
    -map "$STAGE/eira" /eira \
    -map "$STAGE/autoinstall.yaml" /autoinstall.yaml \
    -map "$STAGE/grub.cfg" /boot/grub/grub.cfg \
    -boot_image any replay
chmod 0644 -- "$ISO_OUTPUT"

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
python3 - "$ISO_OUTPUT" "$DEB_PATH" "$SOURCE_COMMIT" "${ISO_OUTPUT}.build-info.json" "$BASE_ISO" <<'PY'
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
base_iso = pathlib.Path(sys.argv[5])


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


package_info_path = deb_path.with_name(deb_path.name + ".build-info.json")
try:
    package_info = json.loads(package_info_path.read_text(encoding="utf-8"))
except (OSError, json.JSONDecodeError):
    package_info = {}
package_commit = package_info.get("source_commit", "unknown")
commit_match = (
    None
    if source_commit == "unknown" or package_commit == "unknown"
    else source_commit == package_commit
)

manifest = {
    "format": "eira-iso-build-info-v2",
    "method": "remastered Ubuntu Desktop ISO + autoinstall",
    "variant": "ci-unattended" if "ci-unattended" in iso_path.name else "installer",
    "source_commit": source_commit,
    "source_commit_verified": source_commit != "unknown",
    "package_build_info_present": bool(package_info),
    "package_source_commit": package_commit,
    "package_commit_matches_iso_source": commit_match,
    "base_distribution": "Ubuntu Desktop 26.04 LTS",
    "architecture": "amd64",
    "built_at_utc": datetime.now(timezone.utc).isoformat(),
    "inputs": [
        {"name": base_iso.name, "sha3_256": sha3(base_iso), "size": base_iso.stat().st_size},
        {"name": deb_path.name, "sha3_256": sha3(deb_path), "size": deb_path.stat().st_size},
    ],
    "outputs": [{"name": iso_path.name, "sha3_256": sha3(iso_path), "size": iso_path.stat().st_size}],
    "tools": {"xorriso": tool_version(["xorriso", "-version"])},
}
manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY
echo "Built $ISO_OUTPUT"
echo "Build provenance: ${ISO_OUTPUT}.build-info.json"
