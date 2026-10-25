// SpektraFilm Windows edition.
// Licensed under the GNU General Public License v3.0 only.
// See the LICENSE file in the repository root.
// Derivative of spektrafilm by Andrea Volpato.

mod sidecar;

use serde_json::{json, Value};
use tauri::{Manager, RunEvent, State};

use sidecar::SidecarState;

#[tauri::command]
fn sidecar_health(state: State<SidecarState>) -> Result<Value, String> {
    state.call("health", json!({}))
}

#[tauri::command]
fn sidecar_version(state: State<SidecarState>) -> Result<Value, String> {
    state.call("version", json!({}))
}

#[tauri::command]
fn list_film_profiles(state: State<SidecarState>) -> Result<Value, String> {
    state.call("list_profiles", json!({ "kind": "film" }))
}

#[tauri::command]
fn list_print_profiles(state: State<SidecarState>) -> Result<Value, String> {
    state.call("list_profiles", json!({ "kind": "print" }))
}

#[tauri::command]
fn run_preview(state: State<SidecarState>, params: Value) -> Result<Value, String> {
    state.call("preview", params)
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .setup(|app| {
            let started = sidecar::locate_script(app.handle())
                .and_then(|script| sidecar::Sidecar::spawn(&script));
            if let Err(err) = &started {
                eprintln!("[sidecar] {err}");
            }
            app.manage(SidecarState(std::sync::Mutex::new(started)));
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            sidecar_health,
            sidecar_version,
            list_film_profiles,
            list_print_profiles,
            run_preview,
        ])
        .build(tauri::generate_context!())
        .expect("failed to build SpektraFilm")
        .run(|app, event| {
            if matches!(event, RunEvent::Exit) {
                if let Some(state) = app.try_state::<SidecarState>() {
                    if let Ok(mut guard) = state.0.lock() {
                        if let Ok(sidecar) = guard.as_mut() {
                            sidecar.shutdown();
                        }
                    }
                }
            }
        });
}
