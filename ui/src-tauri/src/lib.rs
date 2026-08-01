mod ipc;

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![ipc::send_ipc_request])
        .run(tauri::generate_context!())
        .expect("failed to run EiraOS desktop application");
}
