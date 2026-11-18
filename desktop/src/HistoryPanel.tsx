import { save } from "@tauri-apps/plugin-dialog";
import { useEffect, useState } from "react";
import { engineCall } from "./engine";
import { localeCode, useT } from "./i18n";
import { Icon } from "./ui";

/** İşlem günlüğünün bir kaydı (motor: bulutbelge_core.audit). Değer ve içerik taşımaz. */
export interface LogRecord {
  seq: number;
  at: string;
  op: "okuma" | "maskeleme" | "disa_aktarma" | "onizleme" | "maske_kaldirma";
  source: string | null;
  target: string | null;
  source_sha256: string | null;
  target_sha256: string | null;
  counts: Record<string, number>;
  profile: string | null;
  caller: "kullanici" | "ajan";
  agent: string | null;
  result: "basarili" | "hata" | "reddedildi";
  error: string | null;
  hash: string;
}

interface Filters {
  date_from: string;
  date_to: string;
  file: string;
  op: string;
  caller: string;
}

interface VerifyInfo {
  ok: boolean;
  count: number;
  broken_at: number | null;
  reason: string;
}

const OPS: Record<string, string> = {
  onizleme: "Önizleme",
  okuma: "Okuma",
  maskeleme: "Maskeleme",
  maske_kaldirma: "Maske kaldırma",
  disa_aktarma: "Dışa aktarma",
};
const RESULTS: Record<string, string> = { basarili: "Başarılı", hata: "Hata", reddedildi: "Reddedildi" };
const EMPTY: Filters = { date_from: "", date_to: "", file: "", op: "", caller: "" };

function fileName(path: string | null): string {
  if (!path) return "";
  return path.slice(Math.max(path.lastIndexOf("\\"), path.lastIndexOf("/")) + 1);
}

/**
 * İşlem günlüğü (TAKIP 1.38): okunan, maskelenen ve dışa aktarılan her belge. Kayıtlar hash zinciriyle
 * birbirine bağlıdır; "Zinciri denetle" sonradan değiştirilen ya da silinen kaydı bulur. Günlükte bulunan
 * değerler ve belge içeriği yoktur; yalnızca tür bazında sayılar.
 */
export function HistoryPanel({ typeLabels }: { typeLabels: Record<string, string> }) {
  const t = useT();
  const [filters, setFilters] = useState<Filters>(EMPTY);
  const [items, setItems] = useState<LogRecord[] | null>(null);
  const [total, setTotal] = useState(0);
  const [verify, setVerify] = useState<VerifyInfo | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [flash, setFlash] = useState<string | null>(null);

  function params(f: Filters) {
    return Object.fromEntries(Object.entries(f).filter(([, v]) => v));
  }

  function load(f: Filters) {
    engineCall<{ total: number; items: LogRecord[] }>("log.list", { ...params(f), limit: 300 })
      .then((r) => {
        setItems(r.items);
        setTotal(r.total);
        setError(null);
      })
      .catch((e) => setError(String(e)));
  }

  useEffect(() => {
    const timer = setTimeout(() => load(filters), 200);
    return () => clearTimeout(timer);
  }, [filters]);

  function set(patch: Partial<Filters>) {
    setFilters({ ...filters, ...patch });
  }

  async function exportCsv() {
    const today = new Date().toISOString().slice(0, 10);
    const path = await save({ filters: [{ name: "CSV", extensions: ["csv"] }], defaultPath: `islem-gunlugu-${today}.csv` });
    if (!path) return;
    try {
      const r = await engineCall<{ target: string; count: number }>("log.export", { ...params(filters), target: path });
      setFlash(t("{n} kayıt dışa aktarıldı: {name}", { n: r.count, name: fileName(r.target) }));
      setTimeout(() => setFlash(null), 4000);
      load(filters);
    } catch (e) {
      setError(String(e));
    }
  }

  async function runVerify() {
    try {
      setVerify(await engineCall<VerifyInfo>("log.verify"));
    } catch (e) {
      setError(String(e));
    }
  }

  return (
    <div className="history">
      <div className="history-filters">
        <label>
          <span>{t("Başlangıç")}</span>
          <input type="date" value={filters.date_from} onChange={(e) => set({ date_from: e.target.value })} />
        </label>
        <label>
          <span>{t("Bitiş")}</span>
          <input type="date" value={filters.date_to} onChange={(e) => set({ date_to: e.target.value })} />
        </label>
        <label className="grow">
          <span>{t("Dosya")}</span>
          <input
            type="search"
            placeholder={t("Dosya adı ya da klasör")}
            value={filters.file}
            onChange={(e) => set({ file: e.target.value })}
          />
        </label>
        <label>
          <span>{t("İşlem")}</span>
          <select value={filters.op} onChange={(e) => set({ op: e.target.value })}>
            <option value="">{t("Hepsi")}</option>
            {Object.entries(OPS).map(([k, v]) => (
              <option key={k} value={k}>
                {t(v)}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>{t("Çağıran")}</span>
          <select value={filters.caller} onChange={(e) => set({ caller: e.target.value })}>
            <option value="">{t("Hepsi")}</option>
            <option value="kullanici">{t("Kullanıcı")}</option>
            <option value="ajan">{t("Ajan")}</option>
          </select>
        </label>
      </div>

      {error && <p className="field-error">{t(error)}</p>}

      {items && items.length === 0 && <p className="hint">{t("Bu süzgece uyan kayıt yok.")}</p>}
      {items && items.length > 0 && (
        <div className="history-table-wrap">
          <table className="history-table">
            <thead>
              <tr>
                <th>{t("Zaman")}</th>
                <th>{t("İşlem")}</th>
                <th>{t("Dosya")}</th>
                <th>{t("Bulgular")}</th>
                <th>{t("Kural takımı")}</th>
                <th>{t("Çağıran")}</th>
                <th>{t("Sonuç")}</th>
              </tr>
            </thead>
            <tbody>
              {items.map((r) => (
                <tr key={r.seq}>
                  <td className="nowrap">{new Date(r.at).toLocaleString(localeCode())}</td>
                  <td>{t(OPS[r.op] ?? r.op)}</td>
                  <td title={[r.source, r.target && `→ ${r.target}`, r.source_sha256 && `SHA-256: ${r.source_sha256}`].filter(Boolean).join("\n")}>
                    {r.source === "(yapıştırılan metin)" ? t(r.source) : fileName(r.source) || r.source || "—"}
                    {r.target && <small> → {fileName(r.target)}</small>}
                  </td>
                  <td>
                    {Object.entries(r.counts)
                      .map(([type, n]) => `${t(typeLabels[type] ?? type)}: ${n}`)
                      .join(", ") || "—"}
                  </td>
                  <td>{r.profile ? t(r.profile) : "—"}</td>
                  <td>{r.caller === "ajan" ? (r.agent ? t("Ajan ({name})", { name: r.agent }) : t("Ajan")) : t("Kullanıcı")}</td>
                  <td className={`res-${r.result}`} title={r.error ? t(r.error) : undefined}>
                    {t(RESULTS[r.result] ?? r.result)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {items && total > items.length && (
        <p className="hint">
          {t("Son {n} kayıt gösteriliyor (toplam {total}). Tamamı için CSV olarak dışa aktarın.", { n: items.length, total })}
        </p>
      )}

      <div className="history-actions">
        <button className="btn small" onClick={exportCsv} disabled={!items || items.length === 0}>
          <Icon name="download" size={14} /> {t("CSV olarak dışa aktar")}
        </button>
        <button className="btn small" onClick={runVerify}>
          <Icon name="shield" size={14} /> {t("Zinciri denetle")}
        </button>
        {verify &&
          (verify.ok ? (
            <span className="pill conf-yuksek">
              <Icon name="check" size={12} /> {t("{n} kayıt, zincir sağlam", { n: verify.count })}
            </span>
          ) : (
            <span className="warn-text">
              {t("{line}. satırda bozulma: {reason}", { line: verify.broken_at ?? "", reason: t(verify.reason) })}
            </span>
          ))}
        {flash && <span className="hint">{flash}</span>}
      </div>
    </div>
  );
}
