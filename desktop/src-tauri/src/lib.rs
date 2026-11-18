mod engine;
mod guncelleme;

use engine::Engine;
use serde_json::Value;
use tauri::{Manager, State};

/// Arayüzün motora istek göndermesi. Hangi komutların var olduğuna motor karar verir.
#[tauri::command]
async fn engine_call(engine: State<'_, Engine>, method: String, params: Option<Value>) -> Result<Value, String> {
    engine.call(&method, params.unwrap_or(Value::Null))
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_opener::init())
        .manage(Engine::default())
        .setup(|app| {
            let dir = app.path().app_data_dir()?;
            app.state::<Engine>().set_data_dir(dir);
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![engine_call, guncelleme::guncelleme_denetle])
        .run(tauri::generate_context!())
        .expect("uygulama başlatılamadı");
}
