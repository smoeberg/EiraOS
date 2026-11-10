#!/usr/bin/env bash
# Builds a local apt repository with everything the CI install would
# otherwise download: eira-os-core's dependencies and the session packages
# (labwc, xwayland), with their full dependency closure.
#
# CI only (scripts/build_iso.sh --offline-repo). The unattended VM then
# installs without network, so a slow day at the Ubuntu archive or on the
# GitHub runners cannot block a pull request.
#
# Runs inside an ubuntu:26.04 container (docker), so the packages match the
# target release. Usage: build_offline_repo.sh --deb PATH [--deb PATH ...] --output DIR
# Each --deb is a local package (eira-os-core, eira-labwc): its dependencies
# are fetched, and the package itself is added to the repository.
set -euo pipefail

USAGE="usage: build_offline_repo.sh --deb PATH [--deb PATH ...] --output DIR"
DEBS=()
OUT=
while (($#)); do
    case "$1" in
        --deb) DEBS+=("$(realpath -- "$2")"); shift 2 ;;
        --output) OUT=$2; shift 2 ;;
        *) echo "$USAGE" >&2; exit 64 ;;
    esac
done
((${#DEBS[@]})) && [[ -n $OUT ]] || { echo "$USAGE" >&2; exit 64; }
for deb in "${DEBS[@]}"; do [[ -f $deb ]] || { echo "not found: $deb" >&2; exit 66; }; done

# Archive packages the installer adds on top of Ubuntu Desktop besides the
# local ones (eira-postinstall.sh).
SESSION_PACKAGES=${EIRA_OFFLINE_PACKAGES:-"xwayland"}
MIRROR=${EIRA_APT_MIRROR:-}
IMAGE=${EIRA_OFFLINE_IMAGE:-ubuntu:26.04}

mkdir -p -- "$OUT"
OUT=$(realpath -- "$OUT")
MOUNTS=()
for deb in "${DEBS[@]}"; do MOUNTS+=(-v "$deb:/in/$(basename -- "$deb"):ro"); done

docker run --rm \
    -e SESSION_PACKAGES="$SESSION_PACKAGES" -e MIRROR="$MIRROR" -e HOST_UID="$(id -u)" \
    "${MOUNTS[@]}" -v "$OUT:/out" \
    "$IMAGE" bash -euo pipefail -c '
export DEBIAN_FRONTEND=noninteractive
APT="apt-get -o Acquire::Retries=5 -o Acquire::http::Timeout=60 -o Acquire::https::Timeout=60"
if [ -n "$MIRROR" ]; then
    sed -i -E "s#https?://(archive|security)\.ubuntu\.com/ubuntu/?#$MIRROR#g" /etc/apt/sources.list.d/ubuntu.sources
fi
$APT update
$APT install -y --no-install-recommends dpkg-dev

# Names from the local packages'"'"' Depends (every alternative, no versions).
# Names that are themselves local packages are not in the archive; they are
# skipped below and added from /in.
deps=$(for deb in /in/*.deb; do dpkg-deb -f "$deb" Depends; echo; done \
    | tr "," "\n" | tr "|" "\n" | sed -E "s/\(.*\)//; s/:any//; s/^ +//; s/ +$//" | grep -v "^$" | sort -u)
deps=$(for d in $deps; do apt-cache show "$d" >/dev/null 2>&1 && echo "$d"; done)

# Full closure, not just what this container lacks: the target starts from
# the Ubuntu Desktop ISO, whose versions may be older than the archive.
closure=$(apt-cache depends --recurse --no-recommends --no-suggests --no-conflicts \
    --no-breaks --no-replaces --no-enhances $deps $SESSION_PACKAGES \
    | grep "^[a-zA-Z0-9]" | sort -u)

mkdir -p /out/pool
cd /out/pool
# Virtual or unavailable names are skipped; apt-get download fails on them.
for pkg in $closure; do
    apt-cache show "$pkg" >/dev/null 2>&1 && echo "$pkg"
done | xargs -r $APT download >/dev/null

cp /in/*.deb /out/pool/
cd /out
dpkg-scanpackages --multiversion pool /dev/null > Packages
gzip -9kf Packages
echo "offline repo: $(ls pool | wc -l) packages, $(du -sh pool | cut -f1)"
chown -R "$HOST_UID" /out
'
