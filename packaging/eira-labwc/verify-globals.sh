#!/usr/bin/env bash
# R-6.1 (EIRA-CONSENT-AGENT): with EiraOS' rc.xml, no client is offered any
# privileged Wayland protocol. Runs labwc headless, lists the globals an
# ordinary client sees with wayland-info, and checks the list.
#
# A control run with the same labwc and no <privilegedInterfaces> must show
# the privileged globals, so a broken check cannot pass by seeing nothing.
#
# Usage: verify-globals.sh LABWC_BINARY EIRA_LABWC_CONFIG_DIR
set -euo pipefail

LABWC=${1:?labwc binary}
CONFIG=${2:?config dir}

command -v wayland-info >/dev/null || { echo "verify-globals: mangler wayland-info (wayland-utils)" >&2; exit 69; }

FORBIDDEN=(
    zwlr_virtual_pointer_manager_v1
    zwp_virtual_keyboard_manager_v1
    zwp_input_method_manager_v2
    zwlr_layer_shell_v1
    zwlr_screencopy_manager_v1
    ext_image_copy_capture_manager_v1
    ext_output_image_capture_source_manager_v1
    zwlr_export_dmabuf_manager_v1
    ext_data_control_manager_v1
    zwlr_data_control_manager_v1
    zwlr_foreign_toplevel_manager_v1
    ext_foreign_toplevel_list_v1
    zwlr_gamma_control_manager_v1
    zwlr_output_manager_v1
    zwlr_output_power_manager_v1
    wp_drm_lease_device_v1
    ext_idle_notifier_v1
    ext_workspace_manager_v1
    wp_security_context_manager_v1
)
# Must still be there, or the session cannot work at all.
REQUIRED=(wl_compositor wl_seat xdg_wm_base wl_shm)

WORK=$(mktemp -d -t eira-globals.XXXXXXXX)
trap 'rm -rf -- "$WORK"' EXIT INT TERM

globals() {  # $1 config dir, $2 output file
    local runtime="$WORK/run.$RANDOM"
    mkdir -m 0700 "$runtime"
    env -i PATH="$PATH" HOME="$WORK" XDG_RUNTIME_DIR="$runtime" \
        WLR_BACKENDS=headless WLR_RENDERER=pixman WLR_LIBINPUT_NO_DEVICES=1 \
        timeout 60 "$LABWC" -C "$1" \
        -s "sh -c 'wayland-info > \"$2\" 2>&1; \"$LABWC\" --exit'" >"$WORK/labwc.log" 2>&1 || {
            echo "verify-globals: labwc fejlede" >&2; cat "$WORK/labwc.log" >&2; return 1; }
    sed -n "s/.*interface: '\([^']*\)'.*/\1/p" "$2" | sort -u
}

# Control: no <privilegedInterfaces> -> privileged globals are offered.
mkdir "$WORK/control"
printf '<?xml version="1.0"?>\n<labwc_config/>\n' > "$WORK/control/rc.xml"
globals "$WORK/control" "$WORK/control.txt" > "$WORK/control.list"
for iface in zwlr_virtual_pointer_manager_v1 zwlr_layer_shell_v1; do
    grep -qx "$iface" "$WORK/control.list" || {
        echo "verify-globals: kontrolkørslen viser ikke $iface; tjekket kan ikke stoles på" >&2
        exit 1
    }
done

# EiraOS config: none of the privileged globals.
globals "$CONFIG" "$WORK/eira.txt" > "$WORK/eira.list"
fail=0
for iface in "${FORBIDDEN[@]}"; do
    if grep -qx "$iface" "$WORK/eira.list"; then
        echo "FEJL: $iface udbydes til almindelige klienter" >&2
        fail=1
    fi
done
for iface in "${REQUIRED[@]}"; do
    if ! grep -qx "$iface" "$WORK/eira.list"; then
        echo "FEJL: $iface mangler" >&2
        fail=1
    fi
done
# Any privileged global labwc knows about, not just our list.
if [ "$fail" = 0 ]; then
    echo "OK: $(wc -l < "$WORK/eira.list") globals, ingen privilegerede (kontrol: $(wc -l < "$WORK/control.list"))"
fi
exit "$fail"
