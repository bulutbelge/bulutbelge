import { useEffect, useMemo, useState } from "react";
import { engineCall, PdfFinding } from "./engine";
import { byUnit, marked, MarkOptions } from "./Marked";
import { Icon } from "./ui";
import { t, useT } from "./i18n";

type Mode = "orijinal" | "maskeli" | "kaydedilen";

interface Cell {
  text: string;
  unit: string | null;
}
interface Sheet {
  name: string;
  cols: number;
  rows: { row: number; cells: Cell[] }[];
}

/** Elle seçilen satır ya da sütun (satır 1'den, sütun 0'dan). */
export interface SheetLine {
  id: string;
  sheet: string;
  axis: "row" | "col";
  index: number;
  method: string;
}

/** Satır/sütunda seçilebilen yöntemler (hücredeki bilginin türü bilinmediği için genel olanlar). */
const LINE_METHODS: { key: string; label: string }[] = [
  { key: "karartma", label: "Karartma" },
  { key: "etiket", label: "Etiket [GIZLI]" },
  { key: "son4", label: "Son 4 hane açık" },
  { key: "bas_harf", label: "Baş harfler" },
  { key: "takma_ad", label: "Takma ad (Değer-1)" },
];

/** Maskeli önizlemede hücrede görünecek metin (motorun yazacağıyla aynı kural). */
function lineText(text: string, method: string): string {
  if (method === "etiket") return "[GIZLI]";
  if (method === "son4") {
    const d = text.replace(/\D/g, "");
    return d.length > 4 ? `**** ${d.slice(-4)}` : "****";
  }
  if (method === "bas_harf") {
    const words = text.trim().split(/\s+/).filter(Boolean);
    return words.length ? words.map((w) => `${w[0].toLocaleUpperCase("tr")}.`).join(" ") : "█████";
  }
  if (method === "takma_ad") return "Değer-…";
  return "█████";
}

const STRICT = ["karartma", "etiket", "takma_ad", "bas_harf", "son4"];

function lineLabel(l: SheetLine): string {
  return l.axis === "col" ? t("{col} sütunu", { col: colName(l.index) }) : t("{n}. satır", { n: l.index });
}

const MODE_LABEL: Record<Mode, string> = { orijinal: "Bulgular", maskeli: "Maskeli önizleme", kaydedilen: "Kaydedilen dosya" };

function colName(i: number): string {
  let s = "";
  for (let n = i + 1; n > 0; n = Math.floor((n - 1) / 26)) s = String.fromCharCode(65 + ((n - 1) % 26)) + s;
  return s;
}

/**
 * Excel önizlemesi: sayfa sekmeleri, sütun harfleri ve satır numaralarıyla tablo.
 * Bulgular hücrenin içinde işaretlenir. Aynı metin birden çok hücrede geçiyorsa
 * (Excel'in paylaşılan metni) hepsi birlikte işaretlenir ve birlikte maskelenir.
 */
export function SheetPreview({
  source,
  target,
  findings,
  excluded,
  methodOf,
  hovered,
  onHover,
  onToggle,
  plain = false,
  view,
  expanded = false,
  onExpand,
  lines = [],
  onToggleLine,
  onLineMethod,
}: {
  source: string;
  target: string | null;
  findings: PdfFinding[];
  excluded: Set<string>;
  methodOf: (type: string) => string;
  hovered: string | null;
  onHover: (id: string | null) => void;
  onToggle: (id: string) => void;
  plain?: boolean;
  /** Görünüm dışarıdan yönetiliyorsa: sekmeler gösterilmez. */
  view?: "orijinal" | "maskeli" | "kaydedilen";
  expanded?: boolean;
  onExpand?: () => void;
  /** Tamamı maskelenecek satır ve sütunlar. */
  lines?: SheetLine[];
  /** Verilirse sütun harfi ve satır numarası tıklanabilir olur. */
  onToggleLine?: (sheet: string, axis: "row" | "col", index: number) => void;
  /** Seçilen satır/sütunun yöntemini değiştirir. */
  onLineMethod?: (id: string, method: string) => void;
}) {
  const [modeState, setMode] = useState<Mode>("orijinal");
  const t = useT();
  // Görünüm dışarıdan verilirse (Önce/Sonra düğmesi ekranın kendisinde) sekmeler maskelenir.
  const mode = view ?? modeState;
  const [sheets, setSheets] = useState<Sheet[] | null>(null);
  const [active, setActive] = useState(0);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => setMode(target ? "kaydedilen" : "orijinal"), [target]);
  const path = mode === "kaydedilen" && target ? target : source;

  useEffect(() => {
    let alive = true;
    setSheets(null);
    setError(null);
    engineCall<{ sheets: Sheet[] }>("doc.sheets", { path })
      .then((r) => alive && setSheets(r.sheets))
      .catch((e) => alive && setError(String(e)));
    return () => {
      alive = false;
    };
  }, [path]);

  const units = useMemo(() => byUnit(mode === "kaydedilen" ? [] : findings), [findings, mode]);
  const opts: MarkOptions = { excluded, masked: mode === "maskeli", methodOf, hovered, onHover, onToggle };
  const counts = useMemo(
    () => sheets?.map((s) => s.rows.reduce((n, r) => n + r.cells.filter((c) => c.unit && units.has(c.unit)).length, 0)) ?? [],
    [sheets, units],
  );

  // Tablodan bir bulgunun üzerine gelince o bulgunun sayfasına geç.
  useEffect(() => {
    if (!hovered || !sheets) return;
    const f = findings.find((x) => x.id === hovered);
    if (!f?.unit) return;
    const idx = sheets.findIndex((s) => s.rows.some((r) => r.cells.some((c) => c.unit === f.unit)));
    if (idx >= 0) setActive(idx);
  }, [hovered, sheets, findings]);

  const sheet = sheets?.[Math.min(active, (sheets?.length ?? 1) - 1)];
  const showLines = mode !== "kaydedilen";
  const sheetLines = showLines && sheet ? lines.filter((l) => l.sheet === sheet.name) : [];
  const colMethod = new Map(sheetLines.filter((l) => l.axis === "col").map((l) => [l.index, l.method]));
  const rowMethod = new Map(sheetLines.filter((l) => l.axis === "row").map((l) => [l.index, l.method]));
  const selCols = new Set(colMethod.keys());
  const selRows = new Set(rowMethod.keys());
  const canPick = !!onToggleLine && showLines && !plain;
  // Hücre hem satır hem sütun seçimindeyse motordaki gibi daha sıkı yöntem.
  const cellMethod = (row: number, col: number) =>
    [rowMethod.get(row), colMethod.get(col)].filter((m): m is string => !!m).sort((x, y) => STRICT.indexOf(x) - STRICT.indexOf(y))[0];
  const modes: Mode[] = target ? ["orijinal", "maskeli", "kaydedilen"] : ["orijinal", "maskeli"];

  return (
    <div className="preview">
      <div className="preview-bar">
        {view ? null : plain ? (
          <span className="preview-title">{t("Tablo önizlemesi")}</span>
        ) : (
          <div className="segmented" role="tablist">
            {modes.map((m) => (
              <button key={m} role="tab" aria-selected={mode === m} className={mode === m ? "on" : undefined} onClick={() => setMode(m)}>
                {t(MODE_LABEL[m])}
              </button>
            ))}
          </div>
        )}
        {onExpand && (
          <button className="icon-btn" aria-label={expanded ? t("Küçült") : t("Büyüt")} title={expanded ? t("Küçült") : t("Büyüt")} onClick={onExpand}>
            <Icon name={expanded ? "shrink" : "expand"} size={15} />
          </button>
        )}
      </div>

      {error ? (
        <p className="field-error">{error}</p>
      ) : !sheets || !sheet ? (
        <div className="sheet loading" style={{ aspectRatio: "16 / 9" }} />
      ) : (
        <>
          {sheetLines.length > 0 && (
            <div className="xl-lines" aria-label={t("Tamamı maskelenecek satır ve sütunlar")}>
              {sheetLines.map((l) => (
                <span key={l.id} className="xl-line">
                  <b>{lineLabel(l)}</b>
                  {onLineMethod ? (
                    <select value={l.method} aria-label={t("{label} için yöntem", { label: lineLabel(l) })} onChange={(e) => onLineMethod(l.id, e.target.value)}>
                      {LINE_METHODS.map((m) => (
                        <option key={m.key} value={m.key}>
                          {t(m.label)}
                        </option>
                      ))}
                    </select>
                  ) : (
                    <small>{t(LINE_METHODS.find((m) => m.key === l.method)?.label ?? "")}</small>
                  )}
                  {onToggleLine && (
                    <button type="button" className="icon-btn" aria-label={t("{label} seçimini kaldır", { label: lineLabel(l) })} onClick={() => onToggleLine(l.sheet, l.axis, l.index)}>
                      <Icon name="x" size={13} />
                    </button>
                  )}
                </span>
              ))}
            </div>
          )}
          <div className={expanded ? "xl-wrap tall" : "xl-wrap"}>
            <table className="xl">
              <thead>
                <tr>
                  <th className="xl-corner" />
                  {Array.from({ length: Math.max(sheet.cols, 1) }, (_, i) =>
                    canPick ? (
                      <th key={i} className={selCols.has(i) ? "xl-pick on" : "xl-pick"}>
                        <button
                          type="button"
                          title={selCols.has(i) ? t("{col} sütununu maskelemekten vazgeç", { col: colName(i) }) : t("{col} sütununun tamamını maskele", { col: colName(i) })}
                          onClick={() => onToggleLine!(sheet.name, "col", i)}
                        >
                          {colName(i)}
                        </button>
                      </th>
                    ) : (
                      <th key={i} className={selCols.has(i) ? "on" : undefined}>
                        {colName(i)}
                      </th>
                    ),
                  )}
                </tr>
              </thead>
              <tbody>
                {sheet.rows.map((r) => (
                  <tr key={r.row}>
                    {canPick ? (
                      <th className={selRows.has(r.row) ? "xl-pick on" : "xl-pick"}>
                        <button
                          type="button"
                          title={selRows.has(r.row) ? t("{n}. satırı maskelemekten vazgeç", { n: r.row }) : t("{n}. satırın tamamını maskele", { n: r.row })}
                          onClick={() => onToggleLine!(sheet.name, "row", r.row)}
                        >
                          {r.row}
                        </button>
                      </th>
                    ) : (
                      <th className={selRows.has(r.row) ? "on" : undefined}>{r.row}</th>
                    )}
                    {r.cells.map((c, i) => {
                      const lineMethod = cellMethod(r.row, i);
                      const picked = !!lineMethod;
                      const num = /^-?[\d.,E+]+$/.test(c.text) && !(c.unit && units.has(c.unit));
                      const cls = [num ? "num" : "", picked ? "xl-picked" : ""].filter(Boolean).join(" ");
                      return (
                        <td key={i} className={cls || undefined}>
                          {picked && c.text && mode === "maskeli" ? (
                            <span className="xl-line-mask">{lineText(c.text, lineMethod)}</span>
                          ) : (
                            marked(c.text, 0, c.unit ? units.get(c.unit) : undefined, opts)
                          )}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="xl-tabs" role="tablist" aria-label={t("Sayfalar")}>
            {sheets.map((s, i) => (
              <button key={s.name + i} role="tab" aria-selected={i === active} className={i === active ? "on" : undefined} onClick={() => setActive(i)}>
                {s.name}
                {counts[i] > 0 && <b>{counts[i]}</b>}
              </button>
            ))}
          </div>
        </>
      )}

      <p className="hint preview-hint">
        {plain
          ? t("Sayfalar Excel'deki gibi gösteriliyor (ilk 300 satır, 40 sütun). Tara'ya basınca bulgular işaretlenir.")
          : mode === "kaydedilen"
            ? t("Diske yazılan maskeli Excel dosyasının kendisi.")
            : mode === "maskeli"
              ? t("Kaydetmeden önce sonucun nasıl görüneceği. Maskelenen sayı hücreleri metin hücresine çevrilir.")
              : canPick
                ? t("Hücredeki işarete tıklayarak bulguyu dahil edin ya da çıkarın. Bir satırın ya da sütunun tamamını maskelemek için numarasına ya da harfine tıklayın; önizlemede görünmeyen satırlar da maskelenir.")
                : t("Hücredeki işarete tıklayarak bulguyu dahil edin ya da çıkarın. Yorumlar da taranır.")}
      </p>
    </div>
  );
}
