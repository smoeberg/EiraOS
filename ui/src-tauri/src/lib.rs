mod ipc;
#[cfg(unix)]
mod terminal;

#[cfg(unix)]
mod terminal_commands {
    //! Tauri commands and events for the Eira Terminal. Every command is bound
    //! to the calling window's label; output is emitted only to that window.

    use crate::terminal::{
        AllowedSignal, SessionInfo, ShellProfile, TerminalManager, TerminalSink,
    };
    use serde::Serialize;
    use std::sync::{Arc, OnceLock};
    use tauri::{AppHandle, Emitter, State, WebviewWindow};

    pub const OUTPUT_EVENT: &str = "eira://terminal/output";
    pub const EXIT_EVENT: &str = "eira://terminal/exit";

    #[derive(Default)]
    pub struct TerminalState(pub OnceLock<TerminalManager>);

    impl TerminalState {
        fn manager(&self) -> Result<&TerminalManager, String> {
            self.0
                .get()
                .ok_or_else(|| "unavailable: terminal is not initialised".to_owned())
        }
    }

    #[derive(Clone, Serialize)]
    struct OutputPayload {
        session_id: u32,
        data: String,
    }

    #[derive(Clone, Serialize)]
    struct ExitPayload {
        session_id: u32,
        code: Option<i32>,
    }

    pub struct WindowSink(pub AppHandle);

    impl TerminalSink for WindowSink {
        fn output(&self, owner: &str, session_id: u32, data: String) {
            let _ = self
                .0
                .emit_to(owner, OUTPUT_EVENT, OutputPayload { session_id, data });
        }
        fn exit(&self, owner: &str, session_id: u32, code: Option<i32>) {
            let _ = self
                .0
                .emit_to(owner, EXIT_EVENT, ExitPayload { session_id, code });
        }
    }

    pub fn init(app: &AppHandle, state: &TerminalState) {
        let _ = state
            .0
            .set(TerminalManager::new(Arc::new(WindowSink(app.clone()))));
    }

    #[tauri::command]
    pub async fn terminal_create(
        window: WebviewWindow,
        state: State<'_, TerminalState>,
        cols: u16,
        rows: u16,
    ) -> Result<SessionInfo, String> {
        let profile = ShellProfile::for_current_user().map_err(|error| error.to_string())?;
        state
            .manager()?
            .create(window.label(), &profile, cols, rows)
            .map_err(|error| error.to_string())
    }

    #[tauri::command]
    pub async fn terminal_write(
        window: WebviewWindow,
        state: State<'_, TerminalState>,
        session_id: u32,
        data: String,
    ) -> Result<(), String> {
        state
            .manager()?
            .write(window.label(), session_id, &data)
            .map_err(|error| error.to_string())
    }

    #[tauri::command]
    pub async fn terminal_resize(
        window: WebviewWindow,
        state: State<'_, TerminalState>,
        session_id: u32,
        cols: u16,
        rows: u16,
    ) -> Result<(), String> {
        state
            .manager()?
            .resize(window.label(), session_id, cols, rows)
            .map_err(|error| error.to_string())
    }

    #[tauri::command]
    pub async fn terminal_signal(
        window: WebviewWindow,
        state: State<'_, TerminalState>,
        session_id: u32,
        signal: String,
    ) -> Result<(), String> {
        let signal = AllowedSignal::parse(&signal).map_err(|error| error.to_string())?;
        state
            .manager()?
            .signal(window.label(), session_id, signal)
            .map_err(|error| error.to_string())
    }

    #[tauri::command]
    pub async fn terminal_close(
        window: WebviewWindow,
        state: State<'_, TerminalState>,
        session_id: u32,
    ) -> Result<(), String> {
        state
            .manager()?
            .close(window.label(), session_id)
            .map_err(|error| error.to_string())
    }

    pub fn close_window_sessions(state: &TerminalState, label: &str) {
        if let Some(manager) = state.0.get() {
            manager.close_owner(label);
        }
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let builder = tauri::Builder::default();

    #[cfg(unix)]
    let builder = {
        use tauri::Manager;
        builder
            .manage(terminal_commands::TerminalState::default())
            .setup(|app| {
                let state = app.state::<terminal_commands::TerminalState>();
                terminal_commands::init(app.handle(), &state);
                Ok(())
            })
            .on_window_event(|window, event| {
                if let tauri::WindowEvent::Destroyed = event {
                    let state = window.state::<terminal_commands::TerminalState>();
                    terminal_commands::close_window_sessions(&state, window.label());
                }
            })
            .invoke_handler(tauri::generate_handler![
                ipc::send_ipc_request,
                terminal_commands::terminal_create,
                terminal_commands::terminal_write,
                terminal_commands::terminal_resize,
                terminal_commands::terminal_signal,
                terminal_commands::terminal_close,
            ])
    };

    #[cfg(not(unix))]
    let builder = builder.invoke_handler(tauri::generate_handler![ipc::send_ipc_request]);

    builder
        .run(tauri::generate_context!())
        .expect("failed to run EiraOS desktop application");
}
