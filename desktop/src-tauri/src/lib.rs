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

/// Pencere yalnızca uygulamanın kendi kaynağında gezinebilir (güvenlik taraması F16/F25). Belgeden gelen bir
/// bağlantı ya da yönlendirme uygulama penceresini dış bir sayfaya götüremez; dış adresler `openUrl` ile
/// sistem tarayıcısında açılır (izin listesi: capabilities/default.json).
fn uygulama_adresi_mi(url: &tauri::Url) -> bool {
    match url.scheme() {
        // macOS/Linux: tauri://localhost; Windows: http(s)://tauri.localhost
        "tauri" => url.host_str() == Some("localhost"),
        "http" | "https" => {
            url.host_str() == Some("tauri.localhost")
                // Geliştirme sunucusu (tauri.conf.json devUrl), yalnızca hata ayıklama derlemesinde.
                || (cfg!(debug_assertions) && url.host_str() == Some("localhost") && url.port() == Some(1420))
        }
        // Kum havuzlu gömülü HTML çerçevesi (Word altChunk) ve boş sayfa.
        "about" => matches!(url.path(), "blank" | "srcdoc"),
        _ => false,
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let gezinme = tauri::plugin::Builder::<tauri::Wry>::new("gezinme")
        .on_navigation(|_webview, url| uygulama_adresi_mi(url))
        .build();
    tauri::Builder::default()
        .plugin(gezinme)
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
