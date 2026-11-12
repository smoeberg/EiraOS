//! The agent's window (EIRA-CONSENT-AGENT §5.4, R-5.2, R-5.5, R-6.3).
//!
//! An ordinary xdg_toplevel drawn into shared memory: the gate's text and
//! two buttons. The font ships inside the binary (no fontconfig, locale or
//! theme from the environment). A decision counts only after the window has
//! been shown and activated (keyboard focus, as the compositor reports it)
//! without interruption for 750 ms.

use crate::agent::{Decision, Kind, Screen};
use fontdue::layout::{CoordinateSystem, Layout, LayoutSettings, TextStyle};
use fontdue::{Font, FontSettings};
use smithay_client_toolkit::{
    compositor::{CompositorHandler, CompositorState},
    delegate_registry,
    output::{OutputHandler, OutputState},
    registry::{ProvidesRegistryState, RegistryState},
    registry_handlers,
    seat::{
        Capability, SeatHandler, SeatState,
        pointer::{PointerEvent, PointerEventKind, PointerHandler},
    },
    shell::{
        WaylandSurface,
        xdg::{
            XdgShell,
            window::{Window, WindowConfigure, WindowDecorations, WindowHandler},
        },
    },
    shm::{Shm, ShmHandler, slot::SlotPool},
};
use std::os::fd::AsFd;
use std::time::{Duration, Instant};
use wayland_client::{
    Connection, QueueHandle,
    globals::registry_queue_init,
    protocol::{wl_output, wl_pointer, wl_seat, wl_shm, wl_surface},
};

pub const MIN_FOCUS: Duration = Duration::from_millis(750);
const FONT_BYTES: &[u8] = include_bytes!("../assets/DejaVuSans.ttf");
const WIDTH: u32 = 640;
const HEIGHT: u32 = 400;
const MARGIN: f32 = 28.0;
const BUTTON_W: f32 = 180.0;
const BUTTON_H: f32 = 48.0;

/// R-6.3, separate from Wayland so it can be tested.
#[derive(Default, Debug)]
pub struct FocusGate {
    since: Option<Instant>,
}

impl FocusGate {
    pub fn activated(&mut self, active: bool, now: Instant) {
        match (active, self.since) {
            (true, None) => self.since = Some(now),
            (false, _) => self.since = None,
            _ => {}
        }
    }

    pub fn may_decide(&self, now: Instant) -> bool {
        self.since
            .is_some_and(|since| now.duration_since(since) >= MIN_FOCUS)
    }
}

#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub enum Button {
    Decline,
    Approve,
}

pub fn button_at(x: f64, y: f64, width: u32, height: u32) -> Option<Button> {
    let top = height as f64 - MARGIN as f64 - BUTTON_H as f64;
    if !(top..top + BUTTON_H as f64).contains(&y) {
        return None;
    }
    let decline = MARGIN as f64;
    let approve = width as f64 - MARGIN as f64 - BUTTON_W as f64;
    if (decline..decline + BUTTON_W as f64).contains(&x) {
        Some(Button::Decline)
    } else if (approve..approve + BUTTON_W as f64).contains(&x) {
        Some(Button::Approve)
    } else {
        None
    }
}

pub struct WaylandScreen {
    conn: Connection,
    font: Font,
}

impl WaylandScreen {
    pub fn new(conn: Connection) -> Self {
        let font = Font::from_bytes(FONT_BYTES, FontSettings::default()).expect("bundled font");
        WaylandScreen { conn, font }
    }
}

impl Screen for WaylandScreen {
    fn ask(&mut self, text: &str, kind: Kind) -> Decision {
        match run_window(&self.conn, &self.font, text, kind) {
            Ok(decision) => decision,
            Err(error) => {
                eprintln!("eira-consent-agent: window: {error}");
                Decision::Closed
            }
        }
    }
}

struct Dialog {
    registry: RegistryState,
    seats: SeatState,
    outputs: OutputState,
    shm: Shm,
    pool: SlotPool,
    window: Window,
    pointer: Option<wl_pointer::WlPointer>,
    font: Font,
    heading: &'static str,
    text: String,
    width: u32,
    height: u32,
    configured: bool,
    focus: FocusGate,
    drawn_enabled: bool,
    decision: Option<Decision>,
    /// Pixels drawn that are not background (for the smoke test).
    ink: usize,
}

/// Smoke test against a real compositor (examples/window_smoke.rs): opens the
/// dialog for `wait`, then reports (configured, may_decide, drawn pixels that
/// are not background). Never decides anything.
#[cfg(feature = "smoke")]
pub fn smoke(conn: &Connection, text: &str, wait: Duration) -> Result<(bool, bool, usize), String> {
    let font = Font::from_bytes(FONT_BYTES, FontSettings::default()).map_err(|e| e.to_string())?;
    let deadline = Instant::now() + wait;
    let mut report = (false, false, 0);
    run_window_until(conn, &font, text, Kind::ModelAction, &mut |dialog| {
        report = (
            dialog.configured,
            dialog.focus.may_decide(Instant::now()),
            dialog.ink,
        );
        Instant::now() >= deadline
    })?;
    Ok(report)
}

fn run_window(conn: &Connection, font: &Font, text: &str, kind: Kind) -> Result<Decision, String> {
    run_window_until(conn, font, text, kind, &mut |_| false)
}

fn run_window_until(
    conn: &Connection,
    font: &Font,
    text: &str,
    kind: Kind,
    stop: &mut dyn FnMut(&Dialog) -> bool,
) -> Result<Decision, String> {
    let (globals, mut queue) = registry_queue_init::<Dialog>(conn).map_err(|e| e.to_string())?;
    let qh = queue.handle();
    let compositor = CompositorState::bind(&globals, &qh).map_err(|e| e.to_string())?;
    let xdg = XdgShell::bind(&globals, &qh).map_err(|e| e.to_string())?;
    let shm = Shm::bind(&globals, &qh).map_err(|e| e.to_string())?;
    let window = xdg.create_window(
        compositor.create_surface(&qh),
        WindowDecorations::RequestServer,
        &qh,
    );
    window.set_title("EiraOS – godkend");
    window.set_app_id("dk.eiraos.consent-agent");
    window.set_min_size(Some((WIDTH, HEIGHT)));
    window.commit();
    let pool = SlotPool::new((WIDTH * HEIGHT * 4) as usize, &shm).map_err(|e| e.to_string())?;
    let mut dialog = Dialog {
        registry: RegistryState::new(&globals),
        seats: SeatState::new(&globals, &qh),
        outputs: OutputState::new(&globals, &qh),
        shm,
        pool,
        window,
        pointer: None,
        font: font.clone(),
        heading: match kind {
            Kind::ModelAction => "Eira foreslår denne handling på dine vegne:",
            Kind::Action => "Godkend denne handling:",
            Kind::Delegation => "Giv Eira lov til at forberede på dine vegne:",
        },
        text: text.to_string(),
        width: WIDTH,
        height: HEIGHT,
        configured: false,
        focus: FocusGate::default(),
        drawn_enabled: false,
        decision: None,
        ink: 0,
    };
    loop {
        queue.flush().map_err(|e| e.to_string())?;
        queue
            .dispatch_pending(&mut dialog)
            .map_err(|e| e.to_string())?;
        if let Some(decision) = dialog.decision {
            return Ok(decision);
        }
        if stop(&dialog) {
            return Ok(Decision::Closed);
        }
        // Wake at least every 100 ms so the buttons enable once the 750 ms pass.
        if let Some(guard) = queue.prepare_read() {
            let fd = guard
                .connection_fd()
                .as_fd()
                .try_clone_to_owned()
                .map_err(|e| e.to_string())?;
            let mut poll = libc::pollfd {
                fd: std::os::fd::AsRawFd::as_raw_fd(&fd),
                events: libc::POLLIN,
                revents: 0,
            };
            // SAFETY: one valid pollfd.
            let ready = unsafe { libc::poll(&mut poll, 1, 100) };
            if ready > 0 {
                guard.read().map_err(|e| e.to_string())?;
            }
        }
        if dialog.configured && dialog.focus.may_decide(Instant::now()) != dialog.drawn_enabled {
            dialog.draw();
        }
    }
}

impl Dialog {
    fn draw(&mut self) {
        let (w, h) = (self.width, self.height);
        let enabled = self.focus.may_decide(Instant::now());
        self.drawn_enabled = enabled;
        let (buffer, canvas) = match self.pool.create_buffer(
            w as i32,
            h as i32,
            w as i32 * 4,
            wl_shm::Format::Argb8888,
        ) {
            Ok(created) => created,
            Err(error) => {
                eprintln!("eira-consent-agent: buffer: {error}");
                return;
            }
        };
        let mut px = Canvas {
            data: canvas,
            width: w,
            height: h,
        };
        px.fill(0, 0, w, h, 0xFFF7F5F2);
        let max = w as f32 - 2.0 * MARGIN;
        let after_heading = px.text(
            &self.font,
            self.heading,
            MARGIN,
            MARGIN,
            max,
            17.0,
            0xFF5A5550,
        );
        px.text(
            &self.font,
            &self.text,
            MARGIN,
            after_heading + 14.0,
            max,
            20.0,
            0xFF1D1B19,
        );
        let top = h as f32 - MARGIN - BUTTON_H;
        let (fg, approve_bg) = if enabled {
            (0xFFFFFFFF, 0xFF2F6F4E)
        } else {
            (0xFFF0F0F0, 0xFFB8C4BD)
        };
        px.button(&self.font, "Afvis", MARGIN, top, 0xFFE4E0DB, 0xFF1D1B19);
        px.button(
            &self.font,
            "Godkend",
            w as f32 - MARGIN - BUTTON_W,
            top,
            approve_bg,
            fg,
        );
        let background = 0xFFF7F5F2u32.to_le_bytes();
        self.ink = px.data.chunks_exact(4).filter(|p| *p != background).count();
        let surface = self.window.wl_surface();
        surface.damage_buffer(0, 0, w as i32, h as i32);
        if buffer.attach_to(surface).is_ok() {
            self.window.commit();
        }
    }
}

struct Canvas<'a> {
    data: &'a mut [u8],
    width: u32,
    height: u32,
}

impl Canvas<'_> {
    fn put(&mut self, x: i64, y: i64, color: u32, alpha: f32) {
        if x < 0 || y < 0 || x >= self.width as i64 || y >= self.height as i64 {
            return;
        }
        let i = ((y as u32 * self.width + x as u32) * 4) as usize;
        let old = u32::from_le_bytes([
            self.data[i],
            self.data[i + 1],
            self.data[i + 2],
            self.data[i + 3],
        ]);
        let mix = |shift: u32| {
            let (a, b) = (
                ((color >> shift) & 0xFF) as f32,
                ((old >> shift) & 0xFF) as f32,
            );
            ((a * alpha + b * (1.0 - alpha)).round() as u32) << shift
        };
        let blended = 0xFF00_0000 | mix(16) | mix(8) | mix(0);
        self.data[i..i + 4].copy_from_slice(&blended.to_le_bytes());
    }

    fn fill(&mut self, x: u32, y: u32, w: u32, h: u32, color: u32) {
        for yy in y..(y + h).min(self.height) {
            for xx in x..(x + w).min(self.width) {
                self.put(xx as i64, yy as i64, color, 1.0);
            }
        }
    }

    /// Draws wrapped text; returns the y below it.
    #[allow(clippy::too_many_arguments)]
    fn text(
        &mut self,
        font: &Font,
        text: &str,
        x: f32,
        y: f32,
        max_width: f32,
        size: f32,
        color: u32,
    ) -> f32 {
        let mut layout = Layout::new(CoordinateSystem::PositiveYDown);
        layout.reset(&LayoutSettings {
            x,
            y,
            max_width: Some(max_width),
            ..LayoutSettings::default()
        });
        layout.append(&[font], &TextStyle::new(text, size, 0));
        for glyph in layout.glyphs() {
            if glyph.width == 0 {
                continue;
            }
            let (metrics, bitmap) = font.rasterize_config(glyph.key);
            for row in 0..metrics.height {
                for col in 0..metrics.width {
                    let coverage = bitmap[row * metrics.width + col] as f32 / 255.0;
                    if coverage > 0.0 {
                        self.put(
                            glyph.x as i64 + col as i64,
                            glyph.y as i64 + row as i64,
                            color,
                            coverage,
                        );
                    }
                }
            }
        }
        y + layout.height()
    }

    fn button(&mut self, font: &Font, label: &str, x: f32, y: f32, bg: u32, fg: u32) {
        self.fill(x as u32, y as u32, BUTTON_W as u32, BUTTON_H as u32, bg);
        let size = 18.0;
        let width: f32 = label
            .chars()
            .map(|c| font.metrics(c, size).advance_width)
            .sum();
        self.text(
            font,
            label,
            x + (BUTTON_W - width) / 2.0,
            y + 13.0,
            BUTTON_W,
            size,
            fg,
        );
    }
}

impl CompositorHandler for Dialog {
    fn scale_factor_changed(
        &mut self,
        _: &Connection,
        _: &QueueHandle<Self>,
        _: &wl_surface::WlSurface,
        _: i32,
    ) {
    }
    fn transform_changed(
        &mut self,
        _: &Connection,
        _: &QueueHandle<Self>,
        _: &wl_surface::WlSurface,
        _: wl_output::Transform,
    ) {
    }
    fn frame(&mut self, _: &Connection, _: &QueueHandle<Self>, _: &wl_surface::WlSurface, _: u32) {}
    fn surface_enter(
        &mut self,
        _: &Connection,
        _: &QueueHandle<Self>,
        _: &wl_surface::WlSurface,
        _: &wl_output::WlOutput,
    ) {
    }
    fn surface_leave(
        &mut self,
        _: &Connection,
        _: &QueueHandle<Self>,
        _: &wl_surface::WlSurface,
        _: &wl_output::WlOutput,
    ) {
    }
}

impl OutputHandler for Dialog {
    fn output_state(&mut self) -> &mut OutputState {
        &mut self.outputs
    }
    fn new_output(&mut self, _: &Connection, _: &QueueHandle<Self>, _: wl_output::WlOutput) {}
    fn update_output(&mut self, _: &Connection, _: &QueueHandle<Self>, _: wl_output::WlOutput) {}
    fn output_destroyed(&mut self, _: &Connection, _: &QueueHandle<Self>, _: wl_output::WlOutput) {}
}

impl WindowHandler for Dialog {
    fn request_close(&mut self, _: &Connection, _: &QueueHandle<Self>, _: &Window) {
        self.decision = Some(Decision::Closed);
    }

    fn configure(
        &mut self,
        _: &Connection,
        _: &QueueHandle<Self>,
        _: &Window,
        configure: WindowConfigure,
        _: u32,
    ) {
        self.width = configure.new_size.0.map_or(WIDTH, |v| v.get().max(WIDTH));
        self.height = configure.new_size.1.map_or(HEIGHT, |v| v.get().max(HEIGHT));
        self.configured = true;
        // Activation is the compositor's statement that the window has focus.
        self.focus
            .activated(configure.is_activated(), Instant::now());
        self.draw();
    }
}

impl SeatHandler for Dialog {
    fn seat_state(&mut self) -> &mut SeatState {
        &mut self.seats
    }
    fn new_seat(&mut self, _: &Connection, _: &QueueHandle<Self>, _: wl_seat::WlSeat) {}
    fn new_capability(
        &mut self,
        _: &Connection,
        qh: &QueueHandle<Self>,
        seat: wl_seat::WlSeat,
        cap: Capability,
    ) {
        if cap == Capability::Pointer && self.pointer.is_none() {
            self.pointer = self.seats.get_pointer(qh, &seat).ok();
        }
    }
    fn remove_capability(
        &mut self,
        _: &Connection,
        _: &QueueHandle<Self>,
        _: wl_seat::WlSeat,
        cap: Capability,
    ) {
        if cap == Capability::Pointer {
            if let Some(pointer) = self.pointer.take() {
                pointer.release();
            }
        }
    }
    fn remove_seat(&mut self, _: &Connection, _: &QueueHandle<Self>, _: wl_seat::WlSeat) {}
}

impl PointerHandler for Dialog {
    fn pointer_frame(
        &mut self,
        _: &Connection,
        _: &QueueHandle<Self>,
        _: &wl_pointer::WlPointer,
        events: &[PointerEvent],
    ) {
        for event in events {
            if &event.surface != self.window.wl_surface() {
                continue;
            }
            if let PointerEventKind::Release { button: 0x110, .. } = event.kind {
                // BTN_LEFT. Before 750 ms of uninterrupted focus, no click counts.
                if !self.focus.may_decide(Instant::now()) {
                    continue;
                }
                match button_at(event.position.0, event.position.1, self.width, self.height) {
                    Some(Button::Approve) => self.decision = Some(Decision::Approve),
                    Some(Button::Decline) => self.decision = Some(Decision::Decline),
                    None => {}
                }
            }
        }
    }
}

impl ShmHandler for Dialog {
    fn shm_state(&mut self) -> &mut Shm {
        &mut self.shm
    }
}

delegate_registry!(Dialog);

impl ProvidesRegistryState for Dialog {
    fn registry(&mut self) -> &mut RegistryState {
        &mut self.registry
    }
    registry_handlers![OutputState, SeatState];
}

smithay_client_toolkit::delegate_dispatch2!(Dialog);

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn no_decision_before_750_ms_of_uninterrupted_focus() {
        let t0 = Instant::now();
        let mut gate = FocusGate::default();
        assert!(!gate.may_decide(t0 + Duration::from_secs(5))); // never focused
        gate.activated(true, t0);
        assert!(!gate.may_decide(t0 + Duration::from_millis(749)));
        assert!(gate.may_decide(t0 + Duration::from_millis(750)));
        // Losing focus restarts the clock: moving the window under a click does not help.
        gate.activated(false, t0 + Duration::from_millis(800));
        gate.activated(true, t0 + Duration::from_millis(900));
        assert!(!gate.may_decide(t0 + Duration::from_millis(1600)));
        assert!(gate.may_decide(t0 + Duration::from_millis(1650)));
        // A repeated "activated" does not reset it.
        gate.activated(true, t0 + Duration::from_millis(1700));
        assert!(gate.may_decide(t0 + Duration::from_millis(1700)));
    }

    #[test]
    fn buttons_are_where_they_are_drawn() {
        let top = HEIGHT as f64 - MARGIN as f64 - BUTTON_H as f64 + 1.0;
        assert_eq!(
            button_at(MARGIN as f64 + 1.0, top, WIDTH, HEIGHT),
            Some(Button::Decline)
        );
        assert_eq!(
            button_at(WIDTH as f64 - MARGIN as f64 - 1.0, top, WIDTH, HEIGHT),
            Some(Button::Approve)
        );
        assert_eq!(button_at(WIDTH as f64 / 2.0, top, WIDTH, HEIGHT), None);
        assert_eq!(button_at(MARGIN as f64 + 1.0, 10.0, WIDTH, HEIGHT), None);
    }

    #[test]
    fn the_bundled_font_has_danish_letters() {
        let font = Font::from_bytes(FONT_BYTES, FontSettings::default()).unwrap();
        for c in "æøåÆØÅ«»".chars() {
            assert_ne!(font.lookup_glyph_index(c), 0, "{c}");
        }
    }
}
