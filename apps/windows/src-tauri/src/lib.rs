// SpektraFilm Windows edition.
// Licensed under the GNU General Public License v3.0 only.
// See the LICENSE file in the repository root.
// Derivative of spektrafilm by Andrea Volpato.

mod sidecar;

use serde_json::{json, Value};
use tauri::{AppHandle, Manager, RunEvent};

use sidecar::SidecarState;

#[tauri::command]
async fn sidecar_health(app: AppHandle) -> Result<Value, String> {
    sidecar::call(app, "health", json!({})).await
}

#[tauri::command]
async fn sidecar_version(app: AppHandle) -> Result<Value, String> {
    sidecar::call(app, "version", json!({})).await
}

#[tauri::command]
async fn list_film_profiles(app: AppHandle) -> Result<Value, String> {
    sidecar::call(app, "list_profiles", json!({ "kind": "film" })).await
}

#[tauri::command]
async fn list_print_profiles(app: AppHandle) -> Result<Value, String> {
    sidecar::call(app, "list_profiles", json!({ "kind": "print" })).await
}

#[tauri::command]
async fn run_preview(app: AppHandle, params: Value) -> Result<Value, String> {
    sidecar::call(app, "preview", params).await
}

#[tauri::command]
async fn stock_thumb(app: AppHandle, params: Value) -> Result<Value, String> {
    sidecar::call(app, "stock_thumb", params).await
}

#[tauri::command]
async fn preview_thumbnails(app: AppHandle, params: Value) -> Result<Value, String> {
    sidecar::call(app, "preview_thumbnails", params).await
}

#[tauri::command]
async fn import_raw(app: AppHandle, params: Value) -> Result<Value, String> {
    sidecar::call(app, "import_raw", params).await
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .setup(|app| {
            app.manage(SidecarState::new(sidecar::locate_script(app.handle())));
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            sidecar_health,
            sidecar_version,
            list_film_profiles,
            list_print_profiles,
            import_raw,
            run_preview,
            stock_thumb,
            preview_thumbnails,
        ])
        .build(tauri::generate_context!())
        .expect("failed to build SpektraFilm")
        .run(|app, event| {
            if matches!(event, RunEvent::Exit) {
                if let Some(state) = app.try_state::<SidecarState>() {
                    state.shutdown();
                }
            }
        });
}
