import { CSSProperties, useEffect, useMemo, useState } from "react";
import { engineCall, PdfFinding } from "./engine";
import { byUnit, marked, MarkOptions } from "./Marked";
import { Icon } from "./ui";
import { useT } from "./i18n";

type Mode = "orijinal" | "maskeli" | "kaydedilen";

interface Run {
  text: string;
  size: number;
  bold: boolean;
  italic: boolean;
  color: string | null;
}
interface Para {
  unit: string | null;
  align: string;
  level: number;
  runs: Run[];
}
interface Geo {
  x: number;
  y: number;
  w: number;
  h: number;
}
type Item =
  | (Geo & { kind: "text"; fill: string | null; anchor: string; paragraphs: Para[] })
  | (Geo & { kind: "image"; src: string })
  | (Geo & { kind: "table"; rows: Para[][][] });
interface Slide {
  part: string;
  bg: string;
  items: Item[];
  notes: Para[];
}
interface Deck {
  width_pt: number;
  height_pt: number;
  slides: Slide[];
}

const MODE_LABEL: Record<Mode, string> = { orijinal: "Bulgular", maskeli: "Maskeli önizleme", kaydedilen: "Kaydedilen dosya" };
const ALIGN: Record<string, CSSProperties["textAlign"]> = { l: "left", ctr: "center", r: "right", just: "justify" };
const ANCHOR: Record<string, CSSProperties["justifyContent"]> = { t: "flex-start", ctr: "center", b: "flex-end" };

/**
 * PowerPoint önizlemesi: slaytı motordan gelen tarifle (kutu konumu, metin, görsel,
 * tablo) çizer. Yazı boyutları slayt genişliğine göre ölçeklenir (cqw). Bulgular
 * paragraf metninin içinde işaretlenir; konuşmacı notları slaytın altında gösterilir.
 */
export function SlidePreview({
  source,
  target,
  findings,
  excluded,
  methodOf,
  hovered,
  onHover,
  onToggle,
  page,
  onPage,
  plain = false,
  view,
  expanded = false,
  onExpand,
}: {
  source: string;
  target: string | null;
  findings: PdfFinding[];
  excluded: Set<string>;
  methodOf: (type: string) => string;
  hovered: string | null;
  onHover: (id: string | null) => void;
  onToggle: (id: string) => void;
  page: number;
  onPage: (page: number) => void;
  plain?: boolean;
  /** Görünüm dışarıdan yönetiliyorsa: sekmeler gösterilmez. */
  view?: "orijinal" | "maskeli" | "kaydedilen";
  expanded?: boolean;
  onExpand?: () => void;
}) {
  const [modeState, setMode] = useState<Mode>("orijinal");
  const t = useT();
  // Görünüm dışarıdan verilirse (Önce/Sonra düğmesi ekranın kendisinde) sekmeler maskelenir.
  const mode = view ?? modeState;
  const [deck, setDeck] = useState<Deck | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => setMode(target ? "kaydedilen" : "orijinal"), [target]);
  const path = mode === "kaydedilen" && target ? target : source;

  useEffect(() => {
    let alive = true;
    setDeck(null);
    setError(null);
    engineCall<Deck>("doc.slides", { path })
      .then((d) => alive && setDeck(d))
      .catch((e) => alive && setError(String(e)));
    return () => {
      alive = false;
    };
  }, [path]);

  const units = useMemo(() => byUnit(mode === "kaydedilen" ? [] : findings), [findings, mode]);
  const opts: MarkOptions = { excluded, masked: mode === "maskeli", methodOf, hovered, onHover, onToggle };
  const count = deck?.slides.length ?? 1;
  const current = Math.min(Math.max(page, 1), count);
  const slide = deck?.slides[current - 1];
  const modes: Mode[] = target ? ["orijinal", "maskeli", "kaydedilen"] : ["orijinal", "maskeli"];

  const paragraph = (p: Para, key: number, widthPt: number) => {
    let offset = 0;
    const list = p.unit ? units.get(p.unit) : undefined;
    return (
      <p key={key} style={{ textAlign: ALIGN[p.align] ?? "left", marginLeft: `${p.level * 4}%` }}>
        {p.runs.length === 0 && "​"}
        {p.runs.map((r, i) => {
          const start = offset;
          offset += r.text.length;
          if (r.text === "\n") return <br key={i} />;
          return (
            <span
              key={i}
              style={{
                fontSize: `calc(${r.size} / ${widthPt} * 100cqw)`,
                fontWeight: r.bold ? 700 : undefined,
                fontStyle: r.italic ? "italic" : undefined,
                color: r.color ?? undefined,
              }}
            >
              {marked(r.text, start, list, opts)}
            </span>
          );
        })}
      </p>
    );
  };

  return (
    <div className="preview">
      <div className="preview-bar">
        {view ? null : plain ? (
          <span className="preview-title">{t("Sunum önizlemesi")}</span>
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
        <div className="pager">
          <button className="icon-btn prev" aria-label={t("Önceki slayt")} disabled={current <= 1} onClick={() => onPage(current - 1)}>
            <Icon name="chevron" size={14} />
          </button>
          <span>{t("Slayt {current} / {count}", { current, count })}</span>
          <button className="icon-btn" aria-label={t("Sonraki slayt")} disabled={current >= count} onClick={() => onPage(current + 1)}>
            <Icon name="chevron" size={14} />
          </button>
        </div>
      </div>

      <div className={expanded ? "sheet-wrap tall" : "sheet-wrap"}>
        {error ? (
          <p className="field-error">{error}</p>
        ) : !deck || !slide ? (
          <div className="sheet loading" style={{ aspectRatio: "16 / 9" }} />
        ) : (
          <>
            <div className="slide" style={{ aspectRatio: `${deck.width_pt} / ${deck.height_pt}`, background: slide.bg }}>
              {slide.items.map((it, i) => {
                const geo: CSSProperties = { left: `${it.x}%`, top: `${it.y}%`, width: `${it.w}%`, height: `${it.h}%` };
                if (it.kind === "image") return <img key={i} className="slide-img" style={geo} src={it.src} alt="" draggable={false} />;
                if (it.kind === "table")
                  return (
                    <table key={i} className="slide-table" style={geo}>
                      <tbody>
                        {it.rows.map((row, r) => (
                          <tr key={r}>
                            {row.map((cell, c) => (
                              <td key={c}>{cell.map((p, k) => paragraph(p, k, deck.width_pt))}</td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  );
                return (
                  <div
                    key={i}
                    className="slide-text"
                    style={{ ...geo, background: it.fill ?? undefined, justifyContent: ANCHOR[it.anchor] ?? "flex-start" }}
                  >
                    {it.paragraphs.map((p, k) => paragraph(p, k, deck.width_pt))}
                  </div>
                );
              })}
            </div>
            {slide.notes.some((p) => p.runs.some((r) => r.text.trim())) && (
              <div className="slide-notes">
                <b>{t("Konuşmacı notları")}</b>
                {slide.notes.map((p, k) => (
                  <p key={k}>{p.runs.map((r, i) => <span key={i}>{marked(r.text, p.runs.slice(0, i).reduce((n, x) => n + x.text.length, 0), p.unit ? units.get(p.unit) : undefined, opts)}</span>)}</p>
                ))}
              </div>
            )}
          </>
        )}
      </div>

      <p className="hint preview-hint">
        {plain
          ? t("Slaytlar sunumdaki yerleşimiyle gösteriliyor (tema efektleri ve grafikler sadeleştirilir). Tara'ya basınca bulgular işaretlenir.")
          : mode === "kaydedilen"
            ? t("Diske yazılan maskeli sunumun kendisi.")
            : mode === "maskeli"
              ? t("Kaydetmeden önce sonucun nasıl görüneceği; slayt düzeni korunur.")
              : t("İşarete tıklayarak bulguyu dahil edin ya da çıkarın. Konuşmacı notları da taranır.")}
      </p>
    </div>
  );
}
