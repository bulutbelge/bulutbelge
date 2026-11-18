import { invoke } from "@tauri-apps/api/core";
import { openUrl } from "@tauri-apps/plugin-opener";
import { useEffect, useState } from "react";
import { t, useT } from "./i18n";
import { Icon } from "./ui";

/**
 * Açılışta yeni sürüm denetimi. Ayrıntı ve gizlilik notu: `src-tauri/src/guncelleme.rs`.
 * Yalnızca haber verir; indirmeyi kullanıcı yapar. Ayarlar'dan kapatılabilir.
 */
export interface YeniSurum {
  surum: string;
  indirme: string;
}

const KEY_ACIK = "bulutbelge.guncelleme.denetle";
const KEY_GORMEZDEN = "bulutbelge.guncelleme.gormezden";

function oku(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function yaz(key: string, value: string) {
  try {
    localStorage.setItem(key, value);
  } catch {
    // yok say
  }
}

export function denetimAcik(): boolean {
  return oku(KEY_ACIK) !== "kapali";
}

export function denetimiAyarla(acik: boolean) {
  yaz(KEY_ACIK, acik ? "acik" : "kapali");
}

/** Uygulama açılırken bir kez çalışır; yeni sürüm varsa (ve kullanıcı bu sürümü kapatmadıysa) döner. */
export function useGuncelleme(): [YeniSurum | null, () => void] {
  const [yeni, setYeni] = useState<YeniSurum | null>(null);

  useEffect(() => {
    if (!denetimAcik()) return;
    let iptal = false;
    invoke<YeniSurum | null>("guncelleme_denetle")
      .then((s) => {
        if (!iptal && s && oku(KEY_GORMEZDEN) !== s.surum) setYeni(s);
      })
      .catch(() => {
        // ağ yok ya da tarayıcıda çalışıyor: sessizce geç
      });
    return () => {
      iptal = true;
    };
  }, []);

  function gormezdenGel() {
    if (yeni) yaz(KEY_GORMEZDEN, yeni.surum);
    setYeni(null);
  }

  return [yeni, gormezdenGel];
}

/** Üstte ince bilgi şeridi: yeni sürüm var. */
export function GuncellemeSeridi({ yeni, onKapat }: { yeni: YeniSurum; onKapat: () => void }) {
  const tt = useT();
  return (
    <div className="update-banner" role="status">
      <span>{tt("Yeni sürüm var: BulutBelge {surum}. Güncellemek için indirme sayfasını açın.", { surum: yeni.surum })}</span>
      <button type="button" className="update-banner-btn" onClick={() => void openUrl(yeni.indirme).catch(() => {})}>
        {tt("İndirme sayfasını aç")}
      </button>
      <button type="button" className="update-banner-close" onClick={onKapat} aria-label={t("Kapat")} title={t("Bu sürüm için bir daha gösterme")}>
        <Icon name="x" />
      </button>
    </div>
  );
}
