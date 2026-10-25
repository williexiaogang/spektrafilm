// SpektraFilm Windows edition.
// Licensed under the GNU General Public License v3.0 only.

fn main() {
    tauri_build::try_build(tauri_build::Attributes::new().app_manifest(
        tauri_build::AppManifest::new().commands(&[
            "sidecar_health",
            "sidecar_version",
            "list_film_profiles",
            "list_print_profiles",
            "import_raw",
            "run_preview",
            "stock_thumb",
            "preview_thumbnails",
        ]),
    ))
    .expect("failed to run tauri-build");
}
