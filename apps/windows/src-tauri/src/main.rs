// SpektraFilm Windows edition.
// Licensed under the GNU General Public License v3.0 only.
// See the LICENSE file in the repository root.
// Derivative of spektrafilm by Andrea Volpato.
//
// Prevents an extra console window on Windows in release builds.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

fn main() {
    spektrafilm_windows_lib::run()
}
