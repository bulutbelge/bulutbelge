import { getVersion } from "@tauri-apps/api/app";
import { openUrl } from "@tauri-apps/plugin-opener";
import { useEffect, useState } from "react";
import { engineCall, type EngineVersion } from "./engine";
import { useT } from "./i18n";

/**
 * "Sorun bildir" (26 Kasım 2026 ürün sahibi kararı). Uygulama kendisi hiçbir şey göndermez:
 * kullanıcının e-posta programında hazır bir taslak açılır ya da metin panoya kopyalanır; gönderen kullanıcıdır.
 * Masaüstü sunucuya bağlanmaz ilkesine uyar, otomatik hata raporlama (Sentry vb.) yoktur.
 *
 * Rapora yalnızca sürümler, işletim sistemi ve son motor hatası girer. Belge içeriği, dosya adı ve kural
 * takımı girmez; hata iletisindeki dosya yolları ve e-posta adresleri silinir. Son hata yalnızca bellekte
 * durur (diske yazılmaz), uygulama kapanınca gider.
 */
export const DESTEK_ADRESI = "info@bulutbelge.com";
const GITHUB_SORUNLAR = "https://github.com/bulutbelge/bulutbelge/issues";

interface SonHata {
  islem: string;
  ileti: string;
  zaman: string;
}

let sonHata: SonHata | null = null;

/**
 * Hata iletisinden dosya yollarını, belge adlarını ve e-posta adreslerini çıkarır. Dosya adında boşluk
 * olabileceği için yol satır sonuna kadar silinir (bağlamın bir kısmı gider, ad sızmaz).
 */
export function temizle(ileti: string): string {
  return ileti
    .replace(/(?:\\\\|[A-Za-z]:\\)[^\r\n"'<>|]*/g, "[yol]") // Windows yolu ve ağ paylaşımı
    .replace(/(?:~|\/(?:Users|home|Volumes|private|tmp|var|mnt|media|run))\/[^\r\n"'<>|]*/g, "[yol]") // macOS/Linux yolu
    .replace(/[^\s@"'<>]+@[^\s@"'<>]+\.[A-Za-z]{2,}/g, "[e-posta]")
    .replace(/[^\s"'<>|/\\:]+\.(?:pdf|docx?|xlsx?|pptx?|csv|tsv|txt|json|xml|zip|jpe?g|png|tiff?|bmp|webp|md|log|ini|ya?ml|bbvault)\b/gi, "[dosya]")
    .slice(0, 500);
}

/** engineCall hata verdiğinde çağrılır; yalnız son hata tutulur. */
export function hataKaydet(islem: string, err: unknown) {
  sonHata = { islem, ileti: temizle(String(err)), zaman: new Date().toISOString().slice(0, 19).replace("T", " ") };
}

function isletimSistemi(): string {
  const ua = navigator.userAgent;
  if (/Windows NT 10/.test(ua)) return "Windows 10/11";
  if (/Windows/.test(ua)) return "Windows";
  if (/Mac OS X/.test(ua)) return "macOS";
  if (/Linux/.test(ua)) return "Linux";
  return "bilinmiyor";
}

export function raporMetni(uygulama: string, motor: EngineVersion | null): string {
  const satirlar = [
    "Sorunu kısaca anlatın (ne yapıyordunuz, ne bekliyordunuz, ne oldu):",
    "",
    "",
    "--- Teknik bilgi (BulutBelge doldurdu) ---",
    `Uygulama: BulutBelge ${uygulama}`,
    `Motor: ${motor ? `${motor.engine} (çekirdek ${motor.core}, Python ${motor.python})` : "bilinmiyor"}`,
    `İşletim sistemi: ${isletimSistemi()}`,
    sonHata ? `Son hata: ${sonHata.islem} · ${sonHata.ileti} (${sonHata.zaman})` : "Son hata: bu oturumda yok",
    "",
    "Belgenizi eklemeyin. Örnek gerekiyorsa yalnızca maskeli kopyayı, içine bakıp emin olduktan sonra ekleyin.",
  ];
  return satirlar.join("\n");
}

/** Ayarlar'daki "Sorun bildir" bölümü: metni gösterir, e-posta taslağı açar ya da panoya kopyalar. */
export function SorunBildirBolumu() {
  const t = useT();
  const [uygulama, setUygulama] = useState("?");
  const [motor, setMotor] = useState<EngineVersion | null>(null);
  const [durum, setDurum] = useState("");
  useEffect(() => {
    getVersion().then(setUygulama, () => undefined);
    // Motor çalışmıyorsa sürüm "bilinmiyor" kalır; bu çağrının hatası son hatanın üstüne yazılmasın diye doğrudan yakalanır.
    engineCall<EngineVersion>("version", undefined, false).then(setMotor, () => undefined);
  }, []);
  const metin = raporMetni(uygulama, motor);
  const konu = `BulutBelge ${uygulama} sorun bildirimi`;

  const kopyala = () =>
    navigator.clipboard.writeText(metin).then(
      () => setDurum(t("Metin panoya kopyalandı.")),
      () => setDurum(t("Panoya kopyalanamadı; metni seçip kopyalayın.")),
    );

  return (
    <div className="settings-side-section">
      <h2>{t("Sorun bildir")}</h2>
      <p className="hint">
        {t("E-posta programınızda {adres} adresine hazır bir taslak açılır; gönderen sizsiniz. Uygulama kendisi bir şey göndermez. Aşağıdaki metin taslağa eklenir:", { adres: DESTEK_ADRESI })}
      </p>
      <pre className="sorun-metni" aria-label={t("Gönderilecek metin")}>
        {metin}
      </pre>
      <div className="sorun-eylemler">
        <button
          type="button"
          className="btn primary"
          onClick={() =>
            void openUrl(
              `mailto:${DESTEK_ADRESI}?subject=${encodeURIComponent(konu)}&body=${encodeURIComponent(metin)}`,
            ).catch(() => setDurum(t("E-posta programı açılamadı; metni kopyalayıp {adres} adresine gönderin.", { adres: DESTEK_ADRESI })))
          }
        >
          {t("E-posta ile bildir")}
        </button>
        <button type="button" className="btn" onClick={() => void kopyala()}>
          {t("Metni kopyala")}
        </button>
        <button type="button" className="link-btn" onClick={() => void openUrl(GITHUB_SORUNLAR).catch(() => undefined)}>
          {t("GitHub'da bildir")}
        </button>
      </div>
      {durum && (
        <p className="hint" role="status">
          {durum}
        </p>
      )}
    </div>
  );
}
