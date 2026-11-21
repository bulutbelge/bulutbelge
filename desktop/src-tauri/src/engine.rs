//! Python motoru (yan süreç) ile konuşma.
//!
//! Motor ilk istekte başlatılır; stdin/stdout üzerinden satır başına bir JSON
//! mesaj gönderilir. Geliştirmede `engine/` altındaki Python doğrudan
//! çalıştırılır, kurulu sürümde paketlenmiş `bulutbelge-engine` kullanılır.

use std::io::{BufRead, BufReader, Write};
use std::path::PathBuf;
use std::process::{Child, ChildStdin, ChildStdout, Command, Stdio};
use std::sync::Mutex;

use serde_json::{json, Value};

struct Process {
    child: Child,
    stdin: ChildStdin,
    stdout: BufReader<ChildStdout>,
}

impl Drop for Process {
    fn drop(&mut self) {
        let _ = self.child.kill();
        let _ = self.child.wait();
    }
}

#[derive(Default)]
pub struct Engine {
    inner: Mutex<Option<Process>>,
    next_id: Mutex<u64>,
    data_dir: Mutex<Option<PathBuf>>,
}

impl Engine {
    /// Ayarların ve şifreli kasanın tutulacağı klasör (motora ortam değişkeniyle geçer).
    pub fn set_data_dir(&self, dir: PathBuf) {
        if let Ok(mut d) = self.data_dir.lock() {
            *d = Some(dir);
        }
    }

    pub fn call(&self, method: &str, params: Value) -> Result<Value, String> {
        let id = {
            let mut n = self.next_id.lock().map_err(|_| "kilit hatası")?;
            *n += 1;
            *n
        };
        let mut guard = self.inner.lock().map_err(|_| "kilit hatası")?;
        if guard.is_none() {
            let data_dir = self.data_dir.lock().map_err(|_| "kilit hatası")?.clone();
            *guard = Some(spawn(data_dir)?);
        }
        let result = exchange(guard.as_mut().unwrap(), id, method, params.clone());
        if result.is_err() {
            // Süreç bozulduysa ya da yeniden başlatıldıysa anında yeni süreç açıp tekrar dene.
            let data_dir = self.data_dir.lock().map_err(|_| "kilit hatası")?.clone();
            *guard = Some(spawn(data_dir)?);
            let retry = exchange(guard.as_mut().unwrap(), id, method, params);
            if retry.is_err() {
                *guard = None;
            }
            return retry?;
        }
        result?
    }
}

/// Bir istek gönderir, yanıtı okur. Dış `Err` süreç hatası, iç `Err` motorun döndürdüğü hatadır.
fn exchange(p: &mut Process, id: u64, method: &str, params: Value) -> Result<Result<Value, String>, String> {
    let request = json!({ "id": id, "method": method, "params": params });
    writeln!(p.stdin, "{request}").map_err(|e| format!("motora yazılamadı: {e}"))?;
    p.stdin.flush().map_err(|e| format!("motora yazılamadı: {e}"))?;

    let mut line = String::new();
    let n = p.stdout.read_line(&mut line).map_err(|e| format!("motordan okunamadı: {e}"))?;
    if n == 0 {
        return Err("motor beklenmedik şekilde kapandı".into());
    }
    let response: Value = serde_json::from_str(&line).map_err(|_| "motordan geçersiz yanıt".to_string())?;
    if response.get("id").and_then(Value::as_u64) != Some(id) {
        return Err("motor yanıtı istekle eşleşmiyor".into());
    }
    if let Some(err) = response.get("error") {
        let msg = err.get("message").and_then(Value::as_str).unwrap_or("bilinmeyen hata");
        return Ok(Err(msg.to_string()));
    }
    Ok(Ok(response.get("result").cloned().unwrap_or(Value::Null)))
}

fn spawn(data_dir: Option<PathBuf>) -> Result<Process, String> {
    let mut cmd = engine_command()?;
    cmd.stdin(Stdio::piped()).stdout(Stdio::piped()).stderr(Stdio::inherit());
    if let Some(dir) = data_dir {
        cmd.env("BULUTBELGE_DATA_DIR", dir);
    }

    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x0800_0000;
        cmd.creation_flags(CREATE_NO_WINDOW);
    }

    let mut child = cmd.spawn().map_err(|e| format!("motor başlatılamadı: {e}"))?;
    let stdin = child.stdin.take().ok_or("motor stdin alınamadı")?;
    let stdout = BufReader::new(child.stdout.take().ok_or("motor stdout alınamadı")?);
    Ok(Process { child, stdin, stdout })
}

#[cfg(debug_assertions)]
fn engine_command() -> Result<Command, String> {
    let engine_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("..").join("engine");
    let python = std::env::var_os("BULUTBELGE_PYTHON").map(PathBuf::from).unwrap_or_else(|| {
        if cfg!(windows) {
            engine_dir.join(".venv").join("Scripts").join("python.exe")
        } else {
            engine_dir.join(".venv").join("bin").join("python")
        }
    });
    let mut cmd = Command::new(python);
    cmd.args(["-m", "bulutbelge_engine"]).current_dir(engine_dir);
    Ok(cmd)
}

#[cfg(not(debug_assertions))]
fn engine_command() -> Result<Command, String> {
    // Motor klasör olarak (`engine/`) kaynaklarla gelir. Konum işletim sistemine göre değişir:
    // Windows: uygulamanın yanında; macOS: Contents/Resources; Linux (.deb): /usr/lib/<ürün>.
    let exe = std::env::current_exe().map_err(|e| format!("uygulama yolu bulunamadı: {e}"))?;
    let dir = exe.parent().ok_or("uygulama dizini bulunamadı")?;
    let name = if cfg!(windows) { "bulutbelge-engine.exe" } else { "bulutbelge-engine" };
    let adaylar = [
        dir.join("engine").join(name),
        dir.join("..").join("Resources").join("engine").join(name),
        dir.join("..").join("lib").join("BulutBelge").join("engine").join(name),
    ];
    for aday in &adaylar {
        if aday.is_file() {
            return Ok(Command::new(aday));
        }
    }
    Err(format!("motor bulunamadı: {}", adaylar[0].display()))
}
