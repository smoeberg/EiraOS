#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd -- "${SCRIPT_DIR}/../.." && pwd)
OUTPUT_DIR=${EIRA_DEB_OUTPUT_DIR:-${REPO_ROOT}/dist}
OUTPUT_DIR=$(realpath -m -- "$OUTPUT_DIR")
DEB_PATH=${EIRA_DEB_PATH:-${OUTPUT_DIR}/eira-os-core.deb}
DEB_PATH=$(realpath -m -- "$DEB_PATH")

usage() {
    cat >&2 <<'EOF'
Usage: packaging/ubuntu/install.sh

As an unprivileged user, this script builds the supported eira-os-core .deb.
Then run it with sudo to install that package, or install the package directly
with apt. Set EIRA_DEB_PATH to select a previously built package.
EOF
}

if [[ ${EUID} -eq 0 ]]; then
    if [[ ! -f $DEB_PATH || -L $DEB_PATH ]]; then
        echo "No regular Debian package found at: $DEB_PATH" >&2
        echo "Build it first as an unprivileged user:" >&2
        echo "  ${REPO_ROOT}/scripts/build_deb.sh --output-dir ${OUTPUT_DIR}" >&2
        exit 66
    fi
    exec apt-get install -y "$DEB_PATH"
fi

"${REPO_ROOT}/scripts/build_deb.sh" --output-dir "$OUTPUT_DIR"
cat <<EOF
Package built: $DEB_PATH

Review the build-info file, then install the package with:
  sudo ${SCRIPT_DIR}/install.sh
EOF
