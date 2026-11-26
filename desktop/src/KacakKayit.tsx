import { useState } from "react";
import type { MaskResult } from "./engine";
import { useT } from "./i18n";
import { Icon } from "./ui";

/**
 * Kaçağa rağmen kaydetme (26 Kasım 2026 ürün sahibi kararı). Kaçak denetimi kopyada maskelenmesi
 * gereken bir değer bulursa varsayılan olarak dosya yazılmaz. Kullanıcı isterse, kalan türleri görüp açıkça
 * onayladıktan sonra yine de kaydedebilir; motor kaydı işlem günlüğüne "Kaçağa rağmen" sonucuyla yazar.
 * Yalnızca tek belge için; toplu kaydetmede reddedilen belgeler tek tek açılıp kaydedilir.
 */

/** Motorun kaçak iletisi mi (ör. "Kaçak tespiti: … (Tutar ve fiyat). Dosya yazılmadı."). */
export function kacakHatasi(ileti: string | null): boolean {
  return Boolean(ileti && ileti.includes("Kaçak tespiti"));
}

type T = ReturnType<typeof useT>;

/** Sonuç ekranı başlığı: kaçakla kaydedilen kopya "güvenli" diye anılmaz. */
export function sonucBasligi(t: T, done: MaskResult): string {
  return done.leaked?.length ? t("Kopya kaydedildi, ama açık kalan bilgi var") : t("Güvenli kopya hazır");
}

/** Sonuç ekranı açıklaması: kaçak, imza izi ya da temiz. */
export function sonucAciklamasi(t: T, done: MaskResult): string {
  if (done.leaked?.length) {
    return t("{n} kişisel bilgi silindi, ama {m} türde değer kopyada hâlâ okunuyor; kaçağa rağmen kaydetmeyi siz seçtiniz. Paylaşmadan önce kopyayı açıp kontrol edin.", {
      n: done.masked,
      m: done.leaked.length,
    });
  }
  if (done.warnings.some((w) => w.includes("imza izleri"))) {
    return t("{n} kişisel bilgi belgeden silindi, ama imza bölgesinde izler kalmış olabilir. Kopyayı açıp imzayı gözle kontrol edin.", { n: done.masked });
  }
  return t("{n} kişisel bilgi belgeden gerçekten silindi. Dosya yeniden okunarak kontrol edildi; iz kalmadı.", { n: done.masked });
}

/**
 * Kaydet düğmesinin altındaki hata kutusu. Kaçak hatasında ve `onAccept` verildiyse "Yine de kaydet" çıkar;
 * tıklanınca aynı yerde onay istenir, onaydan sonra `onAccept` çağrılır.
 */
export function KaydetmeHatasi({ ileti, onAccept, busy }: { ileti: string; onAccept?: () => void; busy?: boolean }) {
  const t = useT();
  const [onay, setOnay] = useState(false);
  const kabulEdilebilir = Boolean(onAccept) && kacakHatasi(ileti);
  return (
    <div className="save-error" role="alert">
      <Icon name="alert" size={16} />
      <div className="save-error-body">
        <span>{t(ileti)}</span>
        {kabulEdilebilir && !onay && (
          <div className="save-error-actions">
            <button type="button" className="btn small" disabled={busy} onClick={() => setOnay(true)}>
              {t("Yine de kaydet")}
            </button>
          </div>
        )}
        {kabulEdilebilir && onay && (
          <div className="save-error-confirm">
            <p>
              {t("Kopyada yukarıdaki türlerden değerler açık kalacak. Bu kopyayı paylaşırsanız o bilgiler de paylaşılmış olur. Kayıt işlem günlüğüne “kaçağa rağmen” diye yazılır.")}
            </p>
            <div className="save-error-actions">
              <button
                type="button"
                className="btn small danger"
                disabled={busy}
                onClick={() => {
                  setOnay(false);
                  onAccept?.();
                }}
              >
                {t("Evet, kaçağa rağmen kaydet")}
              </button>
              <button type="button" className="btn small" disabled={busy} onClick={() => setOnay(false)}>
                {t("Vazgeç")}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
