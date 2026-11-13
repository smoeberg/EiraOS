#!/usr/bin/env bash
# R-6.2 (EIRA-CONSENT-AGENT): a window of a client in <core><trustedGroup>
# lies above every other window, also a fullscreen one, and has focus; no
# other window can take focus from it.
#
# Runs labwc headless with two test clients: an "agent" (red, small, run
# with the trusted group as effective GID) and an "attacker" (green,
# fullscreen). A screenshot (grim; screencopy is allowed in the test
# config only) shows what is on top; the clients' xdg_toplevel "activated"
# state shows who has focus.
#
# Control runs prove the check can fail: without <trustedGroup>, and with a
# group labwc itself is in (fail closed), the attacker must cover the agent.
#
# Usage: verify-trusted.sh LABWC_BINARY   (as root: the agent needs a GID)
set -euo pipefail

LABWC=${1:?labwc binary}
HERE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
GROUP=${EIRA_TRUSTED_TEST_GROUP:-eira-labwc-test}

[ "$(id -u)" -eq 0 ] || { echo "verify-trusted: skal køre som root" >&2; exit 77; }
for tool in grim setpriv wayland-scanner cc pkg-config python3; do
    command -v "$tool" >/dev/null || { echo "verify-trusted: mangler $tool" >&2; exit 69; }
done
getent group "$GROUP" >/dev/null || groupadd --system "$GROUP"
GID=$(getent group "$GROUP" | cut -d: -f3)

WORK=$(mktemp -d -t eira-trusted.XXXXXXXX)
trap 'rm -rf -- "$WORK"' EXIT INT TERM

# --- test client ---------------------------------------------------------------
XDG_SHELL=$(pkg-config --variable=pkgdatadir wayland-protocols)/stable/xdg-shell/xdg-shell.xml
wayland-scanner client-header "$XDG_SHELL" "$WORK/xdg-shell-client-protocol.h"
wayland-scanner private-code "$XDG_SHELL" "$WORK/xdg-shell-protocol.c"
# shellcheck disable=SC2046
cc -O1 -Wall -Werror -I"$WORK" -o "$WORK/client" "$HERE/test/trusted-client.c" \
    "$WORK/xdg-shell-protocol.c" $(pkg-config --cflags --libs wayland-client)

config() {  # $1 dir, $2 <core> content
    mkdir -p "$1"
    cat > "$1/rc.xml" <<EOF
<?xml version="1.0"?>
<labwc_config>
  <core>$2</core>
  <privilegedInterfaces><allow>zwlr_screencopy_manager_v1</allow></privilegedInterfaces>
</labwc_config>
EOF
}
config "$WORK/cfg-trusted" "<trustedGroup>$GROUP</trustedGroup>"
config "$WORK/cfg-none" ""
config "$WORK/cfg-own-group" "<trustedGroup>$(id -gn)</trustedGroup>"

# The startup script labwc runs: one client, wait until mapped, the other,
# then a screenshot. $1 order: agent-first | attacker-first.
cat > "$WORK/scenario.sh" <<'EOF'
#!/bin/sh
set -u
dir=$1; order=$2; gid=$3; client=$4
agent()    { setpriv --regid="$gid" --clear-groups "$client" "$dir/agent" ff0000 300 200 normal 60 & }
attacker() { "$client" "$dir/attacker" 00ff00 640 480 fullscreen 60 & }
wait_mapped() {
    i=0
    until grep -q '^mapped' "$dir/$1" 2>/dev/null; do
        i=$((i + 1)); [ $i -gt 100 ] && { echo "timeout $1" >> "$dir/errors"; return; }
        sleep 0.1
    done
}
touch "$dir/agent" "$dir/attacker"
if [ "$order" = agent-first ]; then agent; wait_mapped agent; attacker; wait_mapped attacker
else attacker; wait_mapped attacker; agent; wait_mapped agent; fi
sleep 1
grim -t ppm "$dir/shot.ppm" 2>> "$dir/errors"
EOF
chmod +x "$WORK/scenario.sh"

# Pixels in the screenshot that are pure red (the agent).
red_pixels() {
    python3 - "$1" <<'EOF'
import sys
data = open(sys.argv[1], "rb").read()
parts, pos = [], 0
while len(parts) < 4:
    while data[pos:pos + 1].isspace():
        pos += 1
    end = pos
    while not data[end:end + 1].isspace():
        end += 1
    parts.append(data[pos:end]); pos = end
pos += 1
assert parts[0] == b"P6" and parts[3] == b"255", parts
pixels = data[pos:]
print(sum(1 for i in range(0, len(pixels), 3) if pixels[i:i + 3] == b"\xff\x00\x00"))
EOF
}

run() {  # $1 name, $2 config, $3 order -> sets RED, AGENT, ATTACKER
    local dir="$WORK/$1" runtime="$WORK/run-$1"
    mkdir -p "$dir"; mkdir -m 0700 "$runtime"
    env -i PATH="$PATH" HOME="$WORK" XDG_RUNTIME_DIR="$runtime" \
        WLR_BACKENDS=headless WLR_RENDERER=pixman WLR_LIBINPUT_NO_DEVICES=1 \
        timeout 90 "$LABWC" -C "$2" \
        -s "sh -c '\"$WORK/scenario.sh\" \"$dir\" $3 $GID \"$WORK/client\"; \"$LABWC\" --exit'" \
        > "$dir/labwc.log" 2>&1 || true
    if [ -s "$dir/errors" ] || [ ! -s "$dir/shot.ppm" ]; then
        echo "verify-trusted: $1 kunne ikke køres" >&2
        cat "$dir/errors" "$dir/labwc.log" >&2 2>/dev/null | tail -n 40 >&2
        exit 1
    fi
    RED=$(red_pixels "$dir/shot.ppm")
    AGENT=$(grep '^activated' "$dir/agent" | tr '\n' ' ')
    ATTACKER=$(grep '^activated' "$dir/attacker" | tr '\n' ' ')
    echo "$1: røde pixels=$RED agent=[$AGENT] angriber=[$ATTACKER]"
}

AREA=$((300 * 200))
fail=0
expect_protected() {  # agent fully visible, has focus, attacker never focused after
    local name=$1 last_agent last_attacker
    last_agent=$(grep '^activated' "$WORK/$name/agent" | tail -n 1)
    last_attacker=$(grep '^activated' "$WORK/$name/attacker" | tail -n 1)
    if [ "$RED" -lt "$AREA" ]; then
        echo "FEJL $name: agentens vindue er dækket ($RED af $AREA pixels synlige)"; fail=1
    fi
    if [ "$last_agent" != "activated 1" ]; then
        echo "FEJL $name: agenten har ikke fokus ($last_agent)"; fail=1
    fi
    if [ "$last_attacker" = "activated 1" ]; then
        echo "FEJL $name: angriberen har fokus"; fail=1
    fi
}

# 1. Agent first; a fullscreen window maps afterwards and must not cover it
#    or take focus.
run agent-first "$WORK/cfg-trusted" agent-first
expect_protected agent-first
if grep -q '^activated 1' "$WORK/agent-first/attacker"; then
    echo "FEJL agent-first: angriberen fik fokus, mens agenten blev vist"; fail=1
fi
if [ "$(grep '^activated' "$WORK/agent-first/agent" | sed -n '/activated 1/,$p' | grep -c 'activated 0')" -ne 0 ]; then
    echo "FEJL agent-first: agenten mistede fokus undervejs"; fail=1
fi

# 2. A fullscreen window first; the agent maps over it and takes focus.
run attacker-first "$WORK/cfg-trusted" attacker-first
expect_protected attacker-first

# 3. Control: without <trustedGroup> the attacker covers the agent. If it
#    does not, the test above cannot fail and proves nothing.
run control "$WORK/cfg-none" agent-first
if [ "$RED" -ne 0 ] || ! grep -q '^activated 1' "$WORK/control/attacker"; then
    echo "FEJL kontrol: uden <trustedGroup> burde angriberen dække agenten og få fokus"; fail=1
fi

# 4. Fail closed: a group labwc itself runs in trusts nobody.
run own-group "$WORK/cfg-own-group" agent-first
if [ "$RED" -ne 0 ]; then
    echo "FEJL egen gruppe: en gruppe, labwc selv er i, må ikke give tillid"; fail=1
fi
grep -q "is a group labwc runs in" "$WORK/own-group/labwc.log" || {
    echo "FEJL egen gruppe: labwc logger ikke afvisningen"; fail=1; }

if [ "$fail" -ne 0 ]; then
    echo "verify-trusted: R-6.2 holder ikke" >&2
    exit 1
fi
echo "verify-trusted: R-6.2 holder (agent over fuldskærm, fokus, kontrol og fail-closed)"
