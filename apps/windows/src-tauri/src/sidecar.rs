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
        for invocation in python_invocations() {
            match try_spawn(&invocation, &script) {
                Ok(sidecar) => return Ok(sidecar),
                Err(err) => errors.push(format!("{}: {err}", invocation.join(" "))),
            }
        }
        Err(format!(
            "Could not start the Python sidecar. Install Python 3.13, install this repo with `pip install -e .`, and retry. Set SPEKTRAFILM_PYTHON to the interpreter if it is not on PATH.\n{}",
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

fn try_spawn(invocation: &[String], script: &Path) -> Result<Sidecar, String> {
    if invocation.is_empty() {
        return Err("empty Python command".into());
    }
    let mut command = Command::new(&invocation[0]);
    command
        .args(&invocation[1..])
        .arg("-u")
        .arg(script)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .env("PYTHONUNBUFFERED", "1");
    if let Some(root) = infer_repo_root(script) {
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
