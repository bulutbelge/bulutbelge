import { useState } from "react";
import { openUrl } from "@tauri-apps/plugin-opener";
import { useT } from "./i18n";
import { Icon } from "./ui";

/**
 * Sorumluluk reddi (TAKIP 1.94). Metnin aslı bulutbelge.com/kosullar.html'dedir (son güncelleme 10 Kasım 2026);
 * burada özeti gösterilir. İlk açılışta bir kez kabul istenir, Ayarlar'da her zaman okunabilir.
 */
const KOSUL_ADRESI = "https://bulutbelge.com/kosullar.html";
/** Kullanım kılavuzu (TAKIP D.6): React ürün belgesindeki masaüstü sayfası (dokuman/apps/urun-dokuman). Tarayıcıda açılır; uygulama veri göndermez. */
const KILAVUZ_ADRESI = "https://bulutbelge.com/belgeler/#/masaustu-kurulum";
/** Koşullar değişirse bu sürüm yükseltilir ve kabul yeniden istenir. */
const KOSUL_SURUMU = "2026-11-10";
const KABUL_ANAHTARI = "bb.kosulKabul";

function kabulEdilmis(): boolean {
  try {
    return localStorage.getItem(KABUL_ANAHTARI) === KOSUL_SURUMU;
  } catch {
    return false;
  }
}

function KosulMaddeleri() {
  const t = useT();
  return (
    <ul className="terms-list">
      <li>{t("BulutBelge yardımcı bir araçtır. Kişisel bilgileri %100 doğrulukla bulamayabilir ya da maskeleyemeyebilir.")}</li>
      <li>
        {t("“Bulunamadı”, “maskelendi” ya da “iz kalmadı” bildirimleri kesin sonuç değildir. Kopyayı paylaşmadan önce kendiniz gözden geçirin.")}
      </li>
      <li>{t("Çıktının nerede, kime ve hangi amaçla kullanılacağına siz karar verirsiniz. Sorumluluk sınırı Kullanım Koşulları’nda yazılıdır.")}</li>
      <li>{t("Uygulamayı kullanmak bu koşulları kabul etmek anlamına gelir.")}</li>
    </ul>
  );
}

function KosulBaglantisi() {
  const t = useT();
  return (
    <button type="button" className="link-btn" onClick={() => void openUrl(KOSUL_ADRESI).catch(() => undefined)}>
      {t("Koşulların tamamı")}
    </button>
  );
}

/** Ayarlar'daki "Hakkında ve koşullar" bölümü. */
export function HakkindaBolumu() {
  const t = useT();
  return (
    <div className="settings-side-section">
      <h2>{t("Hakkında ve koşullar")}</h2>
      <KosulMaddeleri />
      <p className="hint">
        <KosulBaglantisi /> · {t("Koşulların sürümü")}: {KOSUL_SURUMU}
      </p>
      <p className="hint">
        <button type="button" className="link-btn" onClick={() => void openUrl(KILAVUZ_ADRESI).catch(() => undefined)}>
          {t("Kullanım kılavuzu")}
        </button>{" "}
        · {t("tarayıcıda açılır")}
      </p>
    </div>
  );
}

/** İlk açılışta bir kez gösterilen kabul penceresi (koşullar sürümü değişince yeniden). */
export function IlkAcilisKabul() {
  const t = useT();
  const [goster, setGoster] = useState(() => !kabulEdilmis());
  if (!goster) return null;
  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="kosul-baslik">
      <div className="modal">
        <div className="modal-head">
          <Icon name="shield" size={22} />
          <div>
            <h2 id="kosul-baslik">{t("Başlamadan önce")}</h2>
          </div>
        </div>
        <KosulMaddeleri />
        <div className="modal-actions">
          <KosulBaglantisi />
          <button
            type="button"
            className="btn primary"
            autoFocus
            onClick={() => {
              try {
                localStorage.setItem(KABUL_ANAHTARI, KOSUL_SURUMU);
              } catch {
                // Kayıt yoksa bu oturumda bir daha sorulmaz.
              }
              setGoster(false);
            }}
          >
            {t("Okudum, kabul ediyorum")}
          </button>
        </div>
      </div>
    </div>
  );
}

/** Sonuç ekranlarında "iz kalmadı" gibi cümlelerin kesin sonuç sanılmaması için kısa not. */
export function SonucNotu() {
  const t = useT();
  return <p className="result-caveat">{t("Otomatik bir araçtır; kopyayı paylaşmadan önce kendiniz de gözden geçirin.")}</p>;
}
