// SpektraFilm Windows edition.
// Licensed under the GNU General Public License v3.0 only.

use std::io::{BufRead, BufReader, Write};
use std::path::{Path, PathBuf};
use std::process::{Child, ChildStdin, Command, Stdio};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::mpsc::{self, Receiver};
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::Duration;

use serde_json::Value;
use tauri::AppHandle;
use tauri::Manager;

const REQUEST_TIMEOUT: Duration = Duration::from_secs(300);

pub struct SidecarState {
    connection: Mutex<Option<Sidecar>>,
    script: Result<PathBuf, String>,
    process: Mutex<Option<Arc<Mutex<Child>>>>,
    shutting_down: AtomicBool,
}

impl SidecarState {
    pub fn new(script: Result<PathBuf, String>) -> Self {
        Self {
            connection: Mutex::new(None),
            script,
            process: Mutex::new(None),
            shutting_down: AtomicBool::new(false),
        }
    }

    pub fn call(&self, method: &str, params: Value) -> Result<Value, String> {
        let mut guard = self
            .connection
            .lock()
            .map_err(|err| format!("sidecar lock poisoned: {err}"))?;
        if self.shutting_down.load(Ordering::SeqCst) {
            return Err("Application is closing".into());
        }
        if guard.is_none() {
            let script = self.script.as_ref().map_err(Clone::clone)?;
            let sidecar = Sidecar::spawn(script)?;
            let mut process = self.process.lock().map_err(|err| err.to_string())?;
            if self.shutting_down.load(Ordering::SeqCst) {
                return Err("Application is closing".into());
            }
            *process = Some(Arc::clone(&sidecar.child));
            *guard = Some(sidecar);
        }
        let sidecar = guard.as_mut().expect("sidecar was started");
        let result = sidecar.call(method, params);
        if sidecar.stopped {
            // A fresh process on the next request cannot consume a late response
            // from a request that timed out or lost its protocol framing.
            *guard = None;
        }
        result
    }

    pub fn shutdown(&self) {
        self.shutting_down.store(true, Ordering::SeqCst);
        // Do not take the connection lock: an in-flight preview may hold it.
        if let Ok(process) = self.process.lock() {
            if let Some(child) = process.as_ref() {
                if let Ok(mut child) = child.lock() {
                    let _ = child.kill();
                    let _ = child.wait();
                }
            }
        }
    }
}

pub async fn call(app: AppHandle, method: &'static str, params: Value) -> Result<Value, String> {
    tauri::async_runtime::spawn_blocking(move || app.state::<SidecarState>().call(method, params))
        .await
        .map_err(|err| format!("sidecar task failed: {err}"))?
}

pub struct Sidecar {
    child: Arc<Mutex<Child>>,
    stdin: ChildStdin,
    responses: Receiver<Result<String, String>>,
    next_id: u64,
    stopped: bool,
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
        for invocation in python_invocations(&script) {
            // Launching `py -3.13` can succeed even when that interpreter is
            // missing. Verify the protocol before choosing an invocation.
            match try_spawn(&invocation, &script).and_then(|mut sidecar| {
                sidecar.call_with_timeout(
                    "health",
                    serde_json::json!({}),
                    Duration::from_secs(10),
                )?;
                Ok(sidecar)
            }) {
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
        self.call_with_timeout(method, params, REQUEST_TIMEOUT)
    }

    fn call_with_timeout(
        &mut self,
        method: &str,
        params: Value,
        timeout: Duration,
    ) -> Result<Value, String> {
        let result = self.exchange(method, params, timeout);
        if result.is_err() {
            self.shutdown();
        }
        let response = result?;
        if response.get("ok").and_then(Value::as_bool) == Some(true) {
            return Ok(response.get("result").cloned().unwrap_or(Value::Null));
        }
        // A well-framed runtime error does not damage the connection/cache.
        Err(response
            .pointer("/error/message")
            .and_then(Value::as_str)
            .unwrap_or("sidecar request failed")
            .to_string())
    }

    fn exchange(
        &mut self,
        method: &str,
        params: Value,
        timeout: Duration,
    ) -> Result<Value, String> {
        if self.stopped {
            return Err("Python sidecar is stopped".into());
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

        let line = self.responses.recv_timeout(timeout)
            .map_err(|err| match err {
                mpsc::RecvTimeoutError::Timeout => format!(
                    "Python request '{method}' timed out after {} seconds. Retry to start a fresh sidecar.",
                    timeout.as_secs()
                ),
                mpsc::RecvTimeoutError::Disconnected => "Python sidecar closed stdout. Retry to restart it.".into(),
            })??;
        let response: Value = serde_json::from_str(&line)
            .map_err(|err| format!("sidecar returned invalid JSON ({err}): {line}"))?;
        if response.get("id").and_then(Value::as_u64) != Some(id)
            || response.get("ok").and_then(Value::as_bool).is_none()
        {
            return Err("Python sidecar returned an invalid or out-of-order response".into());
        }
        Ok(response)
    }

    pub fn shutdown(&mut self) {
        self.stopped = true;
        if let Ok(mut child) = self.child.lock() {
            let _ = child.kill();
            let _ = child.wait();
        }
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

fn python_invocations(script: &Path) -> Vec<Vec<String>> {
    if let Ok(explicit) = std::env::var("SPEKTRAFILM_PYTHON") {
        let explicit = explicit.trim();
        if !explicit.is_empty() {
            return vec![split_command(explicit)];
        }
    }
    let mut invocations = Vec::new();
    if let Some(root) = infer_repo_root(script) {
        let python = if cfg!(windows) {
            root.join(".venv/Scripts/python.exe")
        } else {
            root.join(".venv/bin/python")
        };
        if python.is_file() {
            invocations.push(vec![python.to_string_lossy().into_owned()]);
        }
    }
    if cfg!(windows) {
        invocations.extend([
            vec!["py".into(), "-3.13".into()],
            vec!["python".into()],
            vec!["python3".into()],
        ]);
    } else {
        invocations.extend([
            vec!["python3.13".into()],
            vec!["python3".into()],
            vec!["python".into()],
        ]);
    }
    invocations
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

    let (sender, responses) = mpsc::channel();
    thread::spawn(move || {
        let mut skipped = 0;
        for line in BufReader::new(stdout).lines() {
            match line {
                Ok(line) if line.trim_start().starts_with('{') => {
                    skipped = 0;
                    if sender.send(Ok(line)).is_err() {
                        return;
                    }
                }
                Ok(line) => {
                    if !line.is_empty() {
                        eprintln!("[sidecar:stdout] {line}");
                    }
                    skipped += 1;
                    if skipped >= 64 {
                        let _ = sender
                            .send(Err("Python sidecar did not return a JSON response".into()));
                        return;
                    }
                }
                Err(err) => {
                    let _ = sender.send(Err(format!("sidecar stdout: {err}")));
                    return;
                }
            }
        }
    });

    Ok(Sidecar {
        child: Arc::new(Mutex::new(child)),
        stdin,
        responses,
        next_id: 0,
        stopped: false,
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

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;
    use std::time::{Instant, SystemTime, UNIX_EPOCH};

    struct Fixture(PathBuf);

    impl Fixture {
        fn new() -> Self {
            let stamp = SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap()
                .as_nanos();
            let path = std::env::temp_dir().join(format!(
                "spektrafilm-sidecar-{}-{stamp}.py",
                std::process::id()
            ));
            std::fs::write(
                &path,
                r#"
import json, os, sys, time
for line in sys.stdin:
    request = json.loads(line)
    method = request['method']
    if method == 'hang':
        time.sleep(60)
    if method == 'crash':
        os._exit(7)
    response = {'id': request['id'], 'ok': True, 'result': {'status': 'ok'}}
    if method == 'wrong_id':
        response['id'] += 1
    if method == 'runtime_error':
        response = {'id': request['id'], 'ok': False, 'error': {'message': 'invalid image'}}
    print(json.dumps(response), flush=True)
"#,
            )
            .unwrap();
            Self(path)
        }
    }

    impl Drop for Fixture {
        fn drop(&mut self) {
            let _ = std::fs::remove_file(&self.0);
        }
    }

    #[test]
    fn timeout_kills_the_process_instead_of_consuming_a_late_reply() {
        let fixture = Fixture::new();
        let mut sidecar = Sidecar::spawn(&fixture.0).unwrap();
        let started = Instant::now();
        let error = sidecar
            .call_with_timeout("hang", json!({}), Duration::from_millis(100))
            .unwrap_err();
        assert!(error.contains("timed out"), "{error}");
        assert!(started.elapsed() < Duration::from_secs(5));
        assert!(sidecar.child.lock().unwrap().try_wait().unwrap().is_some());
        assert!(sidecar
            .call("health", json!({}))
            .unwrap_err()
            .contains("stopped"));
    }

    #[test]
    fn runtime_errors_preserve_the_connection_but_wrong_ids_terminate_it() {
        let fixture = Fixture::new();
        let mut sidecar = Sidecar::spawn(&fixture.0).unwrap();
        assert_eq!(
            sidecar.call("runtime_error", json!({})).unwrap_err(),
            "invalid image"
        );
        assert!(!sidecar.stopped);
        assert_eq!(sidecar.call("health", json!({})).unwrap()["status"], "ok");
        assert!(sidecar.call("wrong_id", json!({})).is_err());
        assert!(sidecar.stopped);
    }

    #[test]
    fn next_request_restarts_a_crashed_sidecar() {
        let fixture = Fixture::new();
        let state = SidecarState::new(Ok(fixture.0.clone()));
        assert!(state.call("crash", json!({})).is_err());
        assert!(state.connection.lock().unwrap().is_none());
        assert_eq!(state.call("health", json!({})).unwrap()["status"], "ok");
        state.shutdown();
    }

    #[test]
    fn shutdown_does_not_wait_for_an_in_flight_preview() {
        let fixture = Fixture::new();
        let state = Arc::new(SidecarState::new(Ok(fixture.0.clone())));
        state.call("health", json!({})).unwrap();
        let worker_state = Arc::clone(&state);
        let worker = thread::spawn(move || worker_state.call("hang", json!({})));
        let started = Instant::now();
        while state.connection.try_lock().is_ok() {
            assert!(started.elapsed() < Duration::from_secs(5));
            thread::yield_now();
        }
        state.shutdown();
        assert!(worker.join().unwrap().is_err());
        assert!(started.elapsed() < Duration::from_secs(5));
        assert!(state
            .call("health", json!({}))
            .unwrap_err()
            .contains("closing"));
    }
}
