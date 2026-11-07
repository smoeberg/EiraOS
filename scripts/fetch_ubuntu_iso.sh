#!/usr/bin/env bash
# Downloads the current Ubuntu 26.04 LTS desktop ISO and verifies it.
#
# EIRA_UBUNTU_VERSION (default 26.04) and EIRA_UBUNTU_FLAVOR (default desktop)
# select another release or the live-server image.
#
# SHA256SUMS is checked against Canonical's CD image signing key (pinned by
# fingerprint), then the ISO is checked against SHA256SUMS. Prints the path of
# the verified ISO on stdout. An already downloaded, verified ISO is reused.
set -euo pipefail

VERSION=${EIRA_UBUNTU_VERSION:-26.04}
FLAVOR=${EIRA_UBUNTU_FLAVOR:-desktop}
RELEASE_URL=${EIRA_UBUNTU_RELEASE_URL:-https://releases.ubuntu.com/${VERSION}}
# Ubuntu CD Image Automatic Signing Key (2012) <cdimage@ubuntu.com>
CDIMAGE_KEY=843938DF228D22F7B3742BC0D94AA3F0EFE21092
DEST=${1:-${EIRA_ISO_CACHE_DIR:-$(pwd)/.cache/ubuntu-iso}}

# Only the final ISO path goes to stdout (callers capture it); everything else to stderr.
exec 3>&1 1>&2

for tool in curl gpg sha256sum; do
    command -v "$tool" >/dev/null 2>&1 || { echo "Missing tool: $tool" >&2; exit 69; }
done

mkdir -p -- "$DEST"
DEST=$(realpath -- "$DEST")
cd -- "$DEST"

curl -fsSL --retry 3 -o SHA256SUMS "$RELEASE_URL/SHA256SUMS"
curl -fsSL --retry 3 -o SHA256SUMS.gpg "$RELEASE_URL/SHA256SUMS.gpg"

GNUPGHOME=$(mktemp -d)
export GNUPGHOME
trap 'rm -rf -- "$GNUPGHOME"' EXIT
gpg --batch --quiet --keyserver hkps://keyserver.ubuntu.com --recv-keys "$CDIMAGE_KEY" >&2
gpg --batch --status-fd 1 --verify SHA256SUMS.gpg SHA256SUMS 2>/dev/null \
    | grep -q "^\[GNUPG:\] VALIDSIG ${CDIMAGE_KEY} " || {
    echo "SHA256SUMS is not signed by the Ubuntu CD image key" >&2
    exit 65
}

VERSION_RE=${VERSION//./\\.}
ISO_NAME=$(grep -oE "ubuntu-${VERSION_RE}(\.[0-9]+)?-${FLAVOR}-amd64\.iso" SHA256SUMS | sort -V | tail -n 1)
[[ -n $ISO_NAME ]] || { echo "No ${FLAVOR} ISO for ${VERSION} listed in SHA256SUMS" >&2; exit 65; }

if ! grep -E " \*?${ISO_NAME//./\\.}\$" SHA256SUMS | sha256sum --check --status 2>/dev/null; then
    echo "Downloading $ISO_NAME" >&2
    curl -fL --retry 3 -o "$ISO_NAME" "$RELEASE_URL/$ISO_NAME"
    grep -E " \*?${ISO_NAME//./\\.}\$" SHA256SUMS | sha256sum --check --strict >&2
fi

echo "$DEST/$ISO_NAME" >&3
