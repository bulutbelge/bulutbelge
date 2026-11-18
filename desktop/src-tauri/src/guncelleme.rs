//! Açılışta yeni sürüm denetimi.
//!
//! Yalnızca bulutbelge.com'daki küçük `surum.json` dosyası okunur (GET). Belge, kural, kasa ya da
//! kullanıcıya ait hiçbir veri gönderilmez; sunucu yalnızca isteğin geldiği IP'yi ve User-Agent
//! içindeki sürüm numarasını görür. Ağ yoksa ya da sunucu yanıt vermezse sessizce "güncelleme yok" döner.
//! Güncelleme kendiliğinden indirilmez; kullanıcıya haber verilir, indirmeyi kullanıcı yapar.

use serde::{Deserialize, Serialize};
use std::time::Duration;

const SURUM_ADRESI: &str = "https://bulutbelge.com/surum.json";

#[derive(Deserialize)]
struct Uzak {
    surum: String,
    indirme: Option<String>,
}

#[derive(Serialize)]
pub struct YeniSurum {
    pub surum: String,
    pub indirme: String,
}

/// "1.2.3" → (1, 2, 3). Çözülemeyen sürüm karşılaştırmada yok sayılır.
fn ayristir(s: &str) -> Option<(u64, u64, u64)> {
    let temiz = s.trim().trim_start_matches('v');
    let sayilar = temiz.split(['-', '+']).next()?;
    let mut parcalar = sayilar.split('.');
    let a = parcalar.next()?.parse().ok()?;
    let b = parcalar.next().unwrap_or("0").parse().ok()?;
    let c = parcalar.next().unwrap_or("0").parse().ok()?;
    Some((a, b, c))
}

fn daha_yeni(uzak: &str, yerel: &str) -> bool {
    match (ayristir(uzak), ayristir(yerel)) {
        (Some(u), Some(y)) => u > y,
        _ => false,
    }
}

/// Yalnızca bulutbelge.com altındaki https adresleri açılır (surum.json'a güvenilmese de).
fn guvenli_indirme(adres: Option<String>) -> String {
    const VARSAYILAN: &str = "https://bulutbelge.com/#indir";
    match adres {
        Some(a) if a.starts_with("https://bulutbelge.com/") => a,
        _ => VARSAYILAN.to_string(),
    }
}

fn denetle_engelleyen() -> Option<YeniSurum> {
    let yerel = env!("CARGO_PKG_VERSION");
    // Sistemin kendi TLS yığını (Windows'ta Schannel): kurum sertifika deposuna uyar.
    let tls = native_tls::TlsConnector::new().ok()?;
    let ajan = ureq::AgentBuilder::new()
        .tls_connector(std::sync::Arc::new(tls))
        .timeout(Duration::from_secs(5))
        .redirects(0)
        .user_agent(&format!("BulutBelge/{yerel}"))
        .build();
    let uzak: Uzak = ajan.get(SURUM_ADRESI).call().ok()?.into_json().ok()?;
    if daha_yeni(&uzak.surum, yerel) {
        Some(YeniSurum { indirme: guvenli_indirme(uzak.indirme), surum: uzak.surum })
    } else {
        None
    }
}

/// Arayüz açılışta çağırır. Hata ve "güncel" durumları aynı: `None`.
#[tauri::command]
pub async fn guncelleme_denetle() -> Option<YeniSurum> {
    tauri::async_runtime::spawn_blocking(denetle_engelleyen).await.ok().flatten()
}

#[cfg(test)]
mod testler {
    use super::*;

    #[test]
    fn surum_karsilastirma() {
        assert!(daha_yeni("0.2.0", "0.1.0"));
        assert!(daha_yeni("v1.0.0", "0.9.9"));
        assert!(daha_yeni("0.1.10", "0.1.9"));
        assert!(!daha_yeni("0.1.0", "0.1.0"));
        assert!(!daha_yeni("0.0.9", "0.1.0"));
        assert!(!daha_yeni("bozuk", "0.1.0"));
        assert!(!daha_yeni("1.0.0-beta", "1.0.0"));
    }

    #[test]
    fn indirme_adresi_yalniz_kendi_alan_adimiz() {
        assert_eq!(guvenli_indirme(Some("https://bulutbelge.com/indir".into())), "https://bulutbelge.com/indir");
        assert_eq!(guvenli_indirme(Some("https://kotu.example/x".into())), "https://bulutbelge.com/#indir");
        assert_eq!(guvenli_indirme(Some("https://bulutbelge.com.kotu.example/".into())), "https://bulutbelge.com/#indir");
        assert_eq!(guvenli_indirme(None), "https://bulutbelge.com/#indir");
    }
}
