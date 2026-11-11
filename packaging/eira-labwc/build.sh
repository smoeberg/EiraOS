#!/usr/bin/env bash
# Build eira-labwc.deb: labwc >= 0.20.3 with wlroots 0.20 linked statically,
# from the sources pinned in SOURCES, plus the patches in patches/series.
#
# Why EiraOS ships its own labwc (EIRA-CONSENT-AGENT §6.1): Ubuntu 26.04 has
# labwc 0.9.3, which cannot withhold privileged Wayland protocols (virtual
# pointer/keyboard, layer-shell, screencopy, ...) from clients. labwc 0.20.3
# can, with <privilegedInterfaces/> in rc.xml (R-6.1).
#
# The package installs /usr/bin/labwc and replaces Ubuntu's labwc. It installs
# no session entry of its own: the only session is eira-session.
#
# Usage: build.sh [--output-dir DIR]   (run on Ubuntu 26.04; see build-deps)
set -euo pipefail

HERE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
OUTPUT_DIR=${EIRA_DEB_OUTPUT_DIR:-$(cd -- "$HERE/../.." && pwd)/dist}

while (($#)); do
    case "$1" in
        --output-dir) OUTPUT_DIR=$2; shift 2 ;;
        -h|--help) echo "Usage: $0 [--output-dir DIR]"; exit 0 ;;
        *) echo "Usage: $0 [--output-dir DIR]" >&2; exit 64 ;;
    esac
done

# shellcheck source=SOURCES
. "$HERE/SOURCES"

for tool in curl git meson ninja dpkg-deb dpkg-shlibdeps sha256sum sha512sum patch; do
    command -v "$tool" >/dev/null 2>&1 || { echo "eira-labwc: mangler $tool" >&2; exit 69; }
done

WORK=$(mktemp -d -t eira-labwc.XXXXXXXX)
trap 'rm -rf -- "$WORK"' EXIT INT TERM

# --- sources -----------------------------------------------------------------
curl -sSfL -o "$WORK/wlroots.tar.bz2" "$WLROOTS_URL"
echo "$WLROOTS_SHA256  $WORK/wlroots.tar.bz2" | sha256sum -c --quiet -
echo "$WLROOTS_SHA512  $WORK/wlroots.tar.bz2" | sha512sum -c --quiet -

git -c advice.detachedHead=false clone -q --depth 1 --branch "$LABWC_VERSION" "$LABWC_GIT" "$WORK/labwc"
actual=$(git -C "$WORK/labwc" rev-parse HEAD)
if [ "$actual" != "$LABWC_COMMIT" ]; then
    echo "eira-labwc: tag $LABWC_VERSION peger på $actual, forventet $LABWC_COMMIT" >&2
    exit 65
fi
rm -rf "$WORK/labwc/.git"

mkdir -p "$WORK/labwc/subprojects"
tar -xjf "$WORK/wlroots.tar.bz2" -C "$WORK/labwc/subprojects"
mv "$WORK/labwc/subprojects/wlroots-$WLROOTS_VERSION" "$WORK/labwc/subprojects/wlroots"
# Upstream's wrap clones wlroots from git. Ours points at the verified
# tarball already unpacked above, so meson never downloads anything.
cat > "$WORK/labwc/subprojects/wlroots.wrap" <<'WRAP'
[wrap-file]
directory = wlroots

[provide]
dependency_names = wlroots-0.20
WRAP

# --- patches -----------------------------------------------------------------
if [ -f "$HERE/patches/series" ]; then
    while read -r p; do
        case "$p" in ''|'#'*) continue ;; esac
        patch -d "$WORK/labwc" -p1 --forward --batch < "$HERE/patches/$p"
    done < "$HERE/patches/series"
fi

# --- build -------------------------------------------------------------------
# wlroots is linked statically so the package does not depend on (or clash
# with) Ubuntu's libwlroots-0.19. Only the backends a desktop session needs.
meson setup "$WORK/build" "$WORK/labwc" \
    --prefix=/usr --buildtype=release --wrap-mode=nodownload \
    -Dxwayland=enabled -Dman-pages=disabled -Dnls=disabled -Dlabnag=disabled \
    -Dsystemd-session=disabled -Dtest=disabled \
    -Dwlroots:default_library=static -Dwlroots:examples=false \
    -Dwlroots:backends=drm,libinput -Dwlroots:renderers=gles2 \
    -Dwlroots:xwayland=enabled -Dwlroots:session=enabled
ninja -C "$WORK/build"

PKG="$WORK/pkg"
install -D -m 0755 "$WORK/build/labwc" "$PKG/usr/bin/labwc"
strip --strip-unneeded "$PKG/usr/bin/labwc"
install -D -m 0644 "$WORK/labwc/LICENSE" "$PKG/usr/share/doc/eira-labwc/copyright"
install -m 0644 "$HERE/SOURCES" "$PKG/usr/share/doc/eira-labwc/SOURCES"
if [ -f "$HERE/patches/series" ]; then
    install -m 0644 "$HERE/patches/series" "$PKG/usr/share/doc/eira-labwc/patches.series"
fi

# The built binary must report the pinned version (the session checks it).
"$PKG/usr/bin/labwc" --version | grep -q "^labwc $LABWC_VERSION" || {
    echo "eira-labwc: bygget binær rapporterer ikke $LABWC_VERSION" >&2
    exit 70
}

# --- package -----------------------------------------------------------------
mkdir -p "$WORK/shlibs/debian" "$PKG/DEBIAN"
cat > "$WORK/shlibs/debian/control" <<'EOF'
Source: eira-labwc

Package: eira-labwc
Architecture: any
EOF
depends=$(cd "$WORK/shlibs" && dpkg-shlibdeps -O "$PKG/usr/bin/labwc" 2>/dev/null | sed -n 's/^shlibs:Depends=//p')
arch=$(dpkg --print-architecture)
version="$LABWC_VERSION-$EIRA_REVISION"
cat > "$PKG/DEBIAN/control" <<EOF
Package: eira-labwc
Version: $version
Architecture: $arch
Maintainer: EiraOS Maintainers <maintainers@eira-os.invalid>
Section: x11
Priority: optional
Depends: $depends, xwayland
Provides: labwc (= $LABWC_VERSION)
Conflicts: labwc
Replaces: labwc
Homepage: https://github.com/smoeberg/EiraOS
Description: labwc Wayland compositor for EiraOS (wlroots $WLROOTS_VERSION, static)
 labwc $LABWC_VERSION built for EiraOS with wlroots $WLROOTS_VERSION linked
 statically. Required because EiraOS withholds privileged Wayland protocols
 from all clients with <privilegedInterfaces/> (EIRA-CONSENT-AGENT R-6.1),
 which Ubuntu's labwc 0.9 cannot do. Installs no session entry of its own.
EOF

mkdir -p "$OUTPUT_DIR"
dpkg-deb --root-owner-group --build "$PKG" "$OUTPUT_DIR/eira-labwc_${version}_${arch}.deb" >/dev/null
cp "$OUTPUT_DIR/eira-labwc_${version}_${arch}.deb" "$OUTPUT_DIR/eira-labwc.deb"
echo "$OUTPUT_DIR/eira-labwc.deb"
