"""eira-labwc: EiraOS' own labwc, so rc.xml can withhold privileged protocols.

EIRA-CONSENT-AGENT R-6.1 / §6.1. The behaviour itself (which globals a
client sees) is checked by packaging/eira-labwc/verify-globals.sh against a
real headless labwc in CI; these tests pin the contract around it.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PKG = REPO / "packaging" / "eira-labwc"


def _sources() -> dict[str, str]:
    out = {}
    for line in (PKG / "SOURCES").read_text().splitlines():
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            out[key] = value
    return out


def _version(text: str) -> tuple[int, ...]:
    return tuple(int(x) for x in text.split("."))


def test_labwc_is_at_least_0_20_3_and_pinned_by_commit() -> None:
    src = _sources()
    assert _version(src["LABWC_VERSION"]) >= (0, 20, 3)
    assert re.fullmatch(r"[0-9a-f]{40}", src["LABWC_COMMIT"])
    assert src["LABWC_GIT"].startswith("https://")


def test_wlroots_tarball_is_pinned_by_hash() -> None:
    src = _sources()
    assert _version(src["WLROOTS_VERSION"])[:2] == (0, 20)
    assert re.fullmatch(r"[0-9a-f]{64}", src["WLROOTS_SHA256"])
    assert re.fullmatch(r"[0-9a-f]{128}", src["WLROOTS_SHA512"])


def test_build_verifies_what_it_downloads() -> None:
    build = (PKG / "build.sh").read_text()
    assert "sha256sum -c" in build and "sha512sum -c" in build
    assert '"$actual" != "$LABWC_COMMIT"' in build
    assert "--wrap-mode=nodownload" in build
    # No session entry of its own: the only session is eira-session.
    assert "wayland-sessions" not in build
    assert "Conflicts: labwc" in build and "Replaces: labwc" in build


def test_rc_xml_withholds_every_privileged_interface() -> None:
    root = ET.parse(REPO / "packaging/session/config/labwc/rc.xml").getroot()
    blocks = root.findall("privilegedInterfaces")
    assert len(blocks) == 1
    assert list(blocks[0]) == [], "no <allow> may be added (R-6.1)"
    # Not a labwc option; removed so the config says only what labwc reads.
    assert root.find("core/shell") is None


def test_session_requires_eira_labwc_version() -> None:
    session = (REPO / "packaging/session/eira-session").read_text()
    assert "LABWC_MIN=0.20.3" in session
    assert _version(_sources()["LABWC_VERSION"]) >= (0, 20, 3)


def test_iso_ships_and_installs_eira_labwc() -> None:
    iso = (REPO / "scripts/build_iso.sh").read_text()
    assert "packaging/eira-labwc/build.sh" in iso
    assert '"$STAGE/eira/eira-labwc.deb"' in iso
    post = (REPO / "packaging/installer/eira-postinstall.sh").read_text()
    assert '"$SRC/eira-labwc.deb"' in post


def test_verify_globals_covers_the_contract_list() -> None:
    script = (PKG / "verify-globals.sh").read_text()
    for iface in (
        "zwlr_virtual_pointer_manager_v1",
        "zwp_virtual_keyboard_manager_v1",
        "zwp_input_method_manager_v2",
        "zwlr_layer_shell_v1",
        "zwlr_screencopy_manager_v1",
        "ext_image_copy_capture_manager_v1",
        "zwlr_export_dmabuf_manager_v1",
        "ext_data_control_manager_v1",
        "zwlr_data_control_manager_v1",
        "zwlr_foreign_toplevel_manager_v1",
        "ext_foreign_toplevel_list_v1",
    ):
        assert iface in script, iface


# --- R-6.2: the consent agent's window on top, with focus ---------------------

PATCH = "0001-trusted-group-stacking-and-focus.patch"


def test_rc_xml_trusts_only_the_consent_group() -> None:
    root = ET.parse(REPO / "packaging/session/config/labwc/rc.xml").getroot()
    groups = [g.text for g in root.findall("core/trustedGroup")]
    assert groups == ["eira-consent"]


def test_trusted_group_patch_is_applied_and_targets_the_pinned_labwc() -> None:
    series = [
        line for line in (PKG / "patches/series").read_text().splitlines()
        if line and not line.startswith("#")
    ]
    assert series == [PATCH]
    patch = (PKG / "patches" / PATCH).read_text()
    assert _sources()["LABWC_COMMIT"] in patch
    # Each part of R-6.2 has its hook (EIRA-CONSENT-AGENT §6.1).
    for hook in (
        "+++ b/src/trusted.c",        # stacking, grabs, cursor
        "trusted_view_parent(view,",  # trusted windows in their own tree
        "trusted_blocks_view(view)",  # no focus/raise/activation past it
        "surface = trusted_view->surface;",  # keyboard focus stays on it
        "trusted_blocks_cursor(",     # no client cursor image above it
        "drag refused while a trusted window is shown",
        "not minimizing trusted window",
        "is a group labwc runs in",   # fail closed
    ):
        assert hook in patch, hook


def test_package_and_session_require_the_patch() -> None:
    assert "/usr/share/eira-labwc/patches" in (PKG / "build.sh").read_text()
    session = (REPO / "packaging/session/eira-session").read_text()
    assert "LABWC_PATCHES=/usr/share/eira-labwc/patches\n" in session
    assert f"grep -qx '{PATCH}' \"$LABWC_PATCHES\"" in session


def test_ci_runs_the_behaviour_test_with_controls() -> None:
    ci = (REPO / ".github/workflows/packaging-acceptance.yml").read_text()
    assert "packaging/eira-labwc/verify-trusted.sh /tmp/x/usr/bin/labwc" in ci
    script = (PKG / "verify-trusted.sh").read_text()
    for control in ("cfg-none", "cfg-own-group", "agent-first", "attacker-first"):
        assert control in script, control
