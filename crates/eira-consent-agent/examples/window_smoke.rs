//! Opens the consent dialog on the compositor in WAYLAND_DISPLAY for two
//! seconds and checks that it was configured and drawn. Decides nothing.
//! cargo run -p eira-consent-agent --features smoke --example window_smoke

use std::time::Duration;

fn main() {
    let conn = wayland_client::Connection::connect_to_env().expect("compositor");
    let (configured, may_decide, ink) = eira_consent_agent::ui::smoke(
        &conn,
        "Send en besked til did:eira:bo i obj:sag:42: «Kan du se på budgettet?» æøå",
        Duration::from_secs(2),
    )
    .expect("window");
    println!("configured={configured} may_decide={may_decide} ink={ink}");
    assert!(configured, "the compositor never configured the window");
    assert!(ink > 2000, "nothing was drawn");
}
