// SpektraFilm Windows edition.
// Licensed under the GNU General Public License v3.0 only.

use std::io::{BufRead, BufReader, Write};
use std::path::{Path, PathBuf};
use std::process::{Child, ChildStdin, Command, Stdio};
use std::sync::Mutex;
use std::thread;

use serde_json::Value;
use tauri::AppHandle;
use tauri::Manager;

pub struct SidecarState(pub Mutex<Result<Sidecar, String>>);

impl SidecarState {
    pub fn call(&self, method: &str, params: Value) -> Result<Value, String> {
        let mut guard = self
            .0
            .lock()
            .map_err(|err| format!("sidecar lock poisoned: {err}"))?;
        match guard.as_mut() {
            Ok(sidecar) => sidecar.call(method, params),
            Err(err) => Err(err.clone()),
        }
    }
}

pub struct Sidecar {
    child: Child,
    stdin: ChildStdin,
    stdout: BufReader<std::process::ChildStdout>,
    next_id: u64,
}

impl Sidecar {
    pub fn spawn(script: &Path) -> Result<Self, String> {
        let script = script
            .canonicalize()
            .map_err(|err| format!("sidecar script: {err}"))?;
        if !script.is_file() {
            return Err(format!("sidecar script not found: {}", script.display()));
        }

        let mut errors = Vec::new();
        let caches = CacheDirs {
            numba: None,
            matplotlib: None,
        };
        for invocation in python_invocations() {
            match try_spawn(&invocation, &script, false, &caches) {
                Ok(sidecar) => return Ok(sidecar),
                Err(err) => errors.push(format!("{}: {err}", invocation.join(" "))),
            }
        }
        Err(format!(
            "Could not start the Python sidecar. For development, install Python 3.13, install this repo with `pip install -e .`, and retry. Set SPEKTRAFILM_PYTHON to that interpreter if it is not on PATH. A standalone installer carries its own interpreter and does not use this search.\n{}",
            errors.join("\n")
        ))
    }

    pub fn call(&mut self, method: &str, params: Value) -> Result<Value, String> {
        if let Some(status) = self
            .child
            .try_wait()
            .map_err(|err| format!("sidecar status: {err}"))?
        {
            return Err(format!("Python sidecar exited ({status})"));
        }

        self.next_id += 1;
        let id = self.next_id;
        let request = serde_json::json!({
            "id": id,
            "method": method,
            "params": params,
        });
        writeln!(self.stdin, "{request}").map_err(|err| format!("sidecar stdin: {err}"))?;
        self.stdin
            .flush()
            .map_err(|err| format!("sidecar stdin: {err}"))?;

        let line = self.read_response_line()?;
        let response: Value = serde_json::from_str(&line)
            .map_err(|err| format!("sidecar returned invalid JSON ({err}): {line}"))?;
        if response.get("ok").and_then(Value::as_bool) == Some(true) {
            return Ok(response.get("result").cloned().unwrap_or(Value::Null));
        }
        let message = response
            .pointer("/error/message")
            .and_then(Value::as_str)
            .unwrap_or("sidecar request failed");
        Err(message.to_string())
    }

    pub fn shutdown(&mut self) {
        let _ = self.child.kill();
        let _ = self.child.wait();
    }

    fn read_response_line(&mut self) -> Result<String, String> {
        for _ in 0..64 {
            let mut line = String::new();
            let read = self
                .stdout
                .read_line(&mut line)
                .map_err(|err| format!("sidecar stdout: {err}"))?;
            if read == 0 {
                return Err("Python sidecar closed stdout".into());
            }
            let trimmed = line.trim();
            if trimmed.starts_with('{') {
                return Ok(trimmed.to_string());
            }
            if !trimmed.is_empty() {
                eprintln!("[sidecar:stdout] {trimmed}");
            }
        }
        Err("Python sidecar did not return a JSON response".into())
    }
}

impl Drop for Sidecar {
    fn drop(&mut self) {
        self.shutdown();
    }
}

/// How the shell chooses an interpreter.
///
/// A release build that finds the private runtime uses that interpreter and
/// does not search PATH. Debug builds (`tauri dev`) keep the system interpreter
/// unless `SPEKTRAFILM_USE_BUNDLED=1`.
#[derive(Debug, PartialEq, Eq)]
enum LaunchMode {
    Bundled,
    System,
}

fn launch_mode(debug_build: bool, bundle_present: bool, use_bundled_flag: bool) -> LaunchMode {
    if bundle_present && (!debug_build || use_bundled_flag) {
        LaunchMode::Bundled
    } else {
        LaunchMode::System
    }
}

fn env_flag(name: &str) -> bool {
    match std::env::var(name) {
        Ok(value) => flag_value(&value),
        Err(_) => false,
    }
}

fn flag_value(value: &str) -> bool {
    matches!(
        value.trim().to_ascii_lowercase().as_str(),
        "1" | "true" | "yes" | "on"
    )
}

pub fn start(app: &AppHandle) -> Result<Sidecar, String> {
    let debug = cfg!(debug_assertions);
    let use_bundled = env_flag("SPEKTRAFILM_USE_BUNDLED");
    let bundled = locate_bundled_python(app, debug, use_bundled);
    match launch_mode(debug, bundled.is_some(), use_bundled) {
        LaunchMode::Bundled => {
            let python = bundled.expect("private runtime was located");
            if std::env::var("SPEKTRAFILM_PYTHON").is_ok() {
                eprintln!(
                    "[sidecar] ignoring SPEKTRAFILM_PYTHON; using the private runtime at {}",
                    python.display()
                );
            }
            let script = resolve_bundled_script(app, &python)?;
            let caches = prepare_cache_dirs(app);
            Sidecar::spawn_bundled(&python, &script, &caches)
        }
        LaunchMode::System => {
            let script = locate_script(app)?;
            Sidecar::spawn(&script)
        }
    }
}

fn resolve_bundled_script(app: &AppHandle, python: &Path) -> Result<PathBuf, String> {
    if let Some(script) = script_beside_bundle(python) {
        return Ok(script);
    }
    locate_script(app)
}

pub fn locate_script(app: &AppHandle) -> Result<PathBuf, String> {
    if let Ok(explicit) = std::env::var("SPEKTRAFILM_SIDECAR") {
        let path = PathBuf::from(explicit.trim());
        if path.is_file() {
            return Ok(path);
        }
        return Err(format!(
            "SPEKTRAFILM_SIDECAR is not a file: {}",
            path.display()
        ));
    }

    let dev = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../sidecar/server.py");
    if dev.is_file() {
        return Ok(dev);
    }

    let resource = app
        .path()
        .resource_dir()
        .map_err(|err| err.to_string())?
        .join("sidecar")
        .join("server.py");
    if resource.is_file() {
        return Ok(resource);
    }

    Err(
        "Could not find apps/windows/sidecar/server.py. Set SPEKTRAFILM_SIDECAR to the script."
            .into(),
    )
}

struct CacheDirs {
    numba: Option<PathBuf>,
    matplotlib: Option<PathBuf>,
}

fn prepare_cache_dirs(app: &AppHandle) -> CacheDirs {
    let Ok(base) = app.path().app_local_data_dir() else {
        return CacheDirs {
            numba: None,
            matplotlib: None,
        };
    };
    CacheDirs {
        numba: writable_dir(base.join("numba-cache")),
        matplotlib: writable_dir(base.join("matplotlib")),
    }
}

fn writable_dir(path: PathBuf) -> Option<PathBuf> {
    std::fs::create_dir_all(&path).ok()?;
    Some(path)
}

fn locate_bundled_python(app: &AppHandle, debug: bool, use_bundled: bool) -> Option<PathBuf> {
    let mut candidates = Vec::new();
    if !debug || use_bundled {
        if let Ok(dir) = app.path().resource_dir() {
            push_python_candidates(&mut candidates, &dir);
        }
    }
    if debug && use_bundled {
        let manifest = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("resources");
        push_python_candidates(&mut candidates, &manifest);
    }
    first_bundled_python(&candidates)
}

fn push_python_candidates(out: &mut Vec<PathBuf>, root: &Path) {
    for name in ["python.exe", "python"] {
        out.push(root.join("python").join(name));
        out.push(root.join("resources").join("python").join(name));
    }
}

fn first_bundled_python(candidates: &[PathBuf]) -> Option<PathBuf> {
    candidates
        .iter()
        .find(|path| is_spektrafilm_python(path))
        .cloned()
}

fn is_spektrafilm_python(python: &Path) -> bool {
    if !python.is_file() {
        return false;
    }
    let Some(marker) = python.parent().map(|dir| dir.join("BUNDLE.json")) else {
        return false;
    };
    let Ok(text) = std::fs::read_to_string(marker) else {
        return false;
    };
    let Ok(value) = serde_json::from_str::<Value>(&text) else {
        return false;
    };
    value.get("kind").and_then(Value::as_str) == Some("spektrafilm-python-bundle")
}

fn script_beside_bundle(python: &Path) -> Option<PathBuf> {
    let script = python.parent()?.parent()?.join("sidecar").join("server.py");
    if script.is_file() {
        Some(script)
    } else {
        None
    }
}

fn python_invocations() -> Vec<Vec<String>> {
    if let Ok(explicit) = std::env::var("SPEKTRAFILM_PYTHON") {
        let explicit = explicit.trim();
        if !explicit.is_empty() {
            return vec![split_command(explicit)];
        }
    }
    if cfg!(windows) {
        vec![
            vec!["py".into(), "-3.13".into()],
            vec!["python".into()],
            vec!["python3".into()],
        ]
    } else {
        vec![
            vec!["python3.13".into()],
            vec!["python3".into()],
            vec!["python".into()],
        ]
    }
}

fn split_command(command: &str) -> Vec<String> {
    // A path (possibly quoted) plus optional arguments, enough for
    // `SPEKTRAFILM_PYTHON="py -3.13"` and `C:\Path With Spaces\python.exe`.
    let mut parts = Vec::new();
    let mut current = String::new();
    let mut quote: Option<char> = None;
    for ch in command.chars() {
        match (quote, ch) {
            (None, '"' | '\'') => quote = Some(ch),
            (Some(open), ch) if ch == open => quote = None,
            (None, ch) if ch.is_whitespace() => {
                if !current.is_empty() {
                    parts.push(std::mem::take(&mut current));
                }
            }
            (_, ch) => current.push(ch),
        }
    }
    if !current.is_empty() {
        parts.push(current);
    }
    if parts.is_empty() {
        parts.push(command.to_string());
    }
    parts
}

impl Sidecar {
    fn spawn_bundled(python: &Path, script: &Path, caches: &CacheDirs) -> Result<Self, String> {
        let script = script
            .canonicalize()
            .map_err(|err| format!("sidecar script: {err}"))?;
        if !script.is_file() {
            return Err(format!("sidecar script not found: {}", script.display()));
        }
        // -I ignores PYTHONPATH, user site-packages, and a script directory on sys.path.
        let invocation = vec![python.to_string_lossy().into_owned(), "-I".into()];
        try_spawn(&invocation, &script, true, caches).map_err(|err| {
            format!(
                "The private Python runtime failed to start ({}). Reinstall SpektraFilm. This build does not fall back to a Python on PATH.\n{err}",
                python.display()
            )
        })
    }
}

fn try_spawn(
    invocation: &[String],
    script: &Path,
    bundled: bool,
    caches: &CacheDirs,
) -> Result<Sidecar, String> {
    if invocation.is_empty() {
        return Err("empty Python command".into());
    }
    let mut command = Command::new(&invocation[0]);
    command.args(&invocation[1..]).arg("-u").arg(script);
    command
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .env("PYTHONUNBUFFERED", "1");
    if std::env::var_os("MPLBACKEND").is_none() {
        // The sidecar never shows a plot. Agg avoids a Tk dependency.
        command.env("MPLBACKEND", "Agg");
    }
    if bundled {
        command.env("SPEKTRAFILM_BUNDLED", "1");
        command.env("PYTHONNOUSERSITE", "1");
        if let Some(dir) = &caches.numba {
            command.env("NUMBA_CACHE_DIR", dir);
        }
        if let Some(dir) = &caches.matplotlib {
            command.env("MPLCONFIGDIR", dir);
        }
        if let Some(prefix) = Path::new(&invocation[0]).parent() {
            prepend_path(&mut command, prefix);
        }
    } else if let Some(root) = infer_repo_root(script) {
        command.current_dir(root);
    }
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        // CREATE_NO_WINDOW: the GUI should not flash a Python console.
        const CREATE_NO_WINDOW: u32 = 0x08000000;
        command.creation_flags(CREATE_NO_WINDOW);
    }

    let mut child = command.spawn().map_err(|err| {
        if err.kind() == std::io::ErrorKind::NotFound {
            format!("interpreter not found ({err})")
        } else {
            err.to_string()
        }
    })?;
    let stdin = child
        .stdin
        .take()
        .ok_or_else(|| "sidecar stdin was not piped".to_string())?;
    let stdout = child
        .stdout
        .take()
        .ok_or_else(|| "sidecar stdout was not piped".to_string())?;
    let stderr = child
        .stderr
        .take()
        .ok_or_else(|| "sidecar stderr was not piped".to_string())?;
    thread::spawn(move || {
        for line in BufReader::new(stderr).lines() {
            match line {
                Ok(line) if !line.is_empty() => eprintln!("[sidecar] {line}"),
                _ => {}
            }
        }
    });

    Ok(Sidecar {
        child,
        stdin,
        stdout: BufReader::new(stdout),
        next_id: 0,
    })
}

fn prepend_path(command: &mut Command, prefix: &Path) {
    let mut parts = vec![prefix.to_path_buf()];
    if let Some(existing) = std::env::var_os("PATH") {
        parts.extend(std::env::split_paths(&existing));
    }
    if let Ok(joined) = std::env::join_paths(parts) {
        command.env("PATH", joined);
    }
}

fn infer_repo_root(script: &Path) -> Option<PathBuf> {
    let mut current = script.parent()?;
    loop {
        if current.join("pyproject.toml").is_file()
            && current.join("src").join("spektrafilm").is_dir()
        {
            return Some(current.to_path_buf());
        }
        current = current.parent()?;
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn release_with_a_bundle_does_not_use_system_python() {
        assert_eq!(launch_mode(false, true, false), LaunchMode::Bundled);
        assert_eq!(launch_mode(false, true, true), LaunchMode::Bundled);
    }

    #[test]
    fn debug_keeps_system_python_unless_asked() {
        assert_eq!(launch_mode(true, true, false), LaunchMode::System);
        assert_eq!(launch_mode(true, false, true), LaunchMode::System);
        assert_eq!(launch_mode(true, true, true), LaunchMode::Bundled);
    }

    #[test]
    fn missing_bundle_stays_on_system_python() {
        assert_eq!(launch_mode(false, false, false), LaunchMode::System);
    }

    #[test]
    fn flag_values() {
        assert!(flag_value("1"));
        assert!(flag_value(" YES "));
        assert!(!flag_value("0"));
        assert!(!flag_value(""));
    }

    #[test]
    fn split_command_keeps_a_quoted_path() {
        assert_eq!(
            split_command(r#""C:\Path With Spaces\python.exe" -3.13"#),
            vec![
                r"C:\Path With Spaces\python.exe".to_string(),
                "-3.13".to_string()
            ]
        );
    }

    #[test]
    fn bundle_marker_selects_the_private_runtime() {
        let root =
            std::env::temp_dir().join(format!("spektrafilm-bundle-test-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&root);
        let python_dir = root.join("python");
        std::fs::create_dir_all(&python_dir).unwrap();
        let python = python_dir.join("python.exe");
        std::fs::write(&python, b"").unwrap();
        assert!(first_bundled_python(&[python.clone()]).is_none());
        std::fs::write(
            python_dir.join("BUNDLE.json"),
            r#"{"kind":"spektrafilm-python-bundle","python":"3.13.17"}"#,
        )
        .unwrap();
        assert_eq!(
            first_bundled_python(&[root.join("missing.exe"), python.clone()]),
            Some(python)
        );
        let _ = std::fs::remove_dir_all(&root);
    }
}
