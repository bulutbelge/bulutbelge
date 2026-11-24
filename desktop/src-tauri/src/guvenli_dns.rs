//! WebView2'nin kendi şifreli DNS (DoH) bağlantılarını kapatır (Windows; TAKIP W.1, CISO AKS-104).
//!
//! Chromium'da güvenli DNS'in varsayılan modu koşulsuz olarak "automatic"tir: sistem DNS sunucusu bilinen bir
//! sağlayıcıysa (1.1.1.1, 8.8.8.8 gibi) sorgular o sağlayıcının DoH adresine (chrome.cloudflare-dns.com,
//! dns.google) taşınır. Windows denemesi 6'da uygulama boştayken WebView2'nin ağ sürecinin bu adreslere :443
//! bağlantısı görüldü. `--disable-features=DnsOverHttps` bayrağı bu varsayılanı artık etkilemiyor (Chromium
//! `default_dns_over_https_config_source.cc`). Kapatmanın kurum ilkesi dışındaki tek yolu tarayıcının
//! `Local State` dosyasındaki `dns_over_https.mode` tercihidir. Bu dosya uygulamanın kendi WebView2 veri
//! klasöründedir; kullanıcının Edge tarayıcısı ve sistemin DNS ayarı etkilenmez. DNS sorguları sistemin
//! çözücüsüyle (şifrelemesiz ya da Windows'ta tanımlıysa Windows'un DoH'siyle) yapılmaya devam eder.

use serde_json::{Map, Value};

/// `Local State` içeriğinde `dns_over_https.mode` değerini "off" yapar. Değişiklik gerekmiyorsa `None` döner.
/// İçerik bir JSON nesnesi değilse dokunulmaz (`None`): Chromium'un bozuk saydığı dosyayı biz silmeyiz.
#[cfg_attr(not(windows), allow(dead_code))]
pub fn guvenli_dns_kapali(icerik: Option<&[u8]>) -> Option<Vec<u8>> {
    let mut kok = match icerik {
        None => Value::Object(Map::new()),
        Some(b) => match serde_json::from_slice::<Value>(b) {
            Ok(v @ Value::Object(_)) => v,
            _ => return None,
        },
    };
    if kok.pointer("/dns_over_https/mode").and_then(Value::as_str) == Some("off") {
        return None;
    }
    let nesne = kok.as_object_mut()?;
    let dns = nesne.entry("dns_over_https").or_insert_with(|| Value::Object(Map::new()));
    if !dns.is_object() {
        *dns = Value::Object(Map::new());
    }
    dns.as_object_mut()?.insert("mode".into(), Value::String("off".into()));
    serde_json::to_vec(&kok).ok()
}

/// Uygulamanın WebView2 veri klasöründeki `Local State` dosyasına güvenli DNS'in kapalı olduğunu yazar.
/// WebView2 başlamadan (pencere oluşturulmadan) çağrılmalıdır; hata uygulamayı durdurmaz.
#[cfg(windows)]
pub fn webview_guvenli_dns_kapat(kimlik: &str) {
    use std::fs;
    use std::path::PathBuf;

    // Tauri 2 WebView2 veri klasörü: app_local_data_dir (%LOCALAPPDATA%\<kimlik>) ve altında EBWebView.
    let Some(yerel) = std::env::var_os("LOCALAPPDATA") else { return };
    let klasor = PathBuf::from(yerel).join(kimlik).join("EBWebView");
    let yol = klasor.join("Local State");
    let mevcut = fs::read(&yol).ok();
    let Some(yeni) = guvenli_dns_kapali(mevcut.as_deref()) else { return };
    if fs::create_dir_all(&klasor).is_err() {
        return;
    }
    let gecici = klasor.join("Local State.bulutbelge-tmp");
    if fs::write(&gecici, &yeni).is_ok() && fs::rename(&gecici, &yol).is_err() {
        let _ = fs::remove_file(&gecici);
    }
}

#[cfg(test)]
mod tests {
    use super::guvenli_dns_kapali;
    use serde_json::{json, Value};

    fn oku(b: Vec<u8>) -> Value {
        serde_json::from_slice(&b).unwrap()
    }

    #[test]
    fn dosya_yoksa_yalnizca_dns_ayari_yazilir() {
        assert_eq!(oku(guvenli_dns_kapali(None).unwrap()), json!({"dns_over_https": {"mode": "off"}}));
    }

    #[test]
    fn diger_ayarlar_korunur_mod_kapatilir() {
        let eski = json!({"browser": {"x": 1}, "dns_over_https": {"mode": "automatic", "templates": ""}});
        let yeni = oku(guvenli_dns_kapali(Some(&serde_json::to_vec(&eski).unwrap())).unwrap());
        assert_eq!(yeni, json!({"browser": {"x": 1}, "dns_over_https": {"mode": "off", "templates": ""}}));
    }

    #[test]
    fn zaten_kapaliysa_ya_da_dosya_bozuksa_dokunulmaz() {
        assert!(guvenli_dns_kapali(Some(br#"{"dns_over_https":{"mode":"off"}}"#)).is_none());
        assert!(guvenli_dns_kapali(Some(b"{bozuk")).is_none());
        assert!(guvenli_dns_kapali(Some(b"[1,2]")).is_none());
    }

    #[test]
    fn dns_alani_nesne_degilse_duzeltilir() {
        let yeni = oku(guvenli_dns_kapali(Some(br#"{"dns_over_https":"x"}"#)).unwrap());
        assert_eq!(yeni, json!({"dns_over_https": {"mode": "off"}}));
    }
}
