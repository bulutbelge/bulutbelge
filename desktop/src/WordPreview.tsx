import { renderAsync } from "docx-preview";
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { engineCall, PdfFinding } from "./engine";
import { Icon } from "./ui";
import { useT } from "./i18n";

type Mode = "orijinal" | "maskeli" | "kaydedilen";
type Box = { id: string; finding: PdfFinding; left: number; top: number; width: number; height: number; first: boolean };

const MODE_LABEL: Record<Mode, string> = {
  orijinal: "Bulgular",
  maskeli: "Maskeli önizleme",
  kaydedilen: "Kaydedilen dosya",
};
const ZOOMS = [1, 1.25, 1.5, 2];

/**
 * Word belgesini Word'deki gibi (sayfa, yazı tipi, tablo, üst/alt bilgi) çizer.
 * Çizim docx-preview kütüphanesiyle tamamen bilgisayarda yapılır.
 *
 * Bulgular belgenin üzerine kutu olarak çizilir: her bulgunun değeri çizilmiş
 * metinde aranır, bulunduğu yerin ekrandaki dikdörtgenleri alınır (Range).
 * Değer birden çok biçim parçasına bölünmüş olsa da Range bunları kapsar.
 * Aynı değer birkaç kez geçiyorsa sırayla eşleştirilir.
 */
export function WordPreview({
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
}) {
  const [modeState, setMode] = useState<Mode>("orijinal");
  const t = useT();
  // Görünüm dışarıdan verilirse (Önce/Sonra düğmesi ekranın kendisinde) sekmeler maskelenir.
  const mode = view ?? modeState;
  const [userZoom, setUserZoom] = useState(1);
  const [fit, setFit] = useState(1);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [boxes, setBoxes] = useState<Box[]>([]);
  const wrapRef = useRef<HTMLDivElement>(null);
  const docRef = useRef<HTMLDivElement>(null);
  const styleRef = useRef<HTMLDivElement>(null);

  useEffect(() => setMode(target ? "kaydedilen" : "orijinal"), [target]);

  const path = mode === "kaydedilen" && target ? target : source;
  const zoom = fit * userZoom;

  // Belgeyi motordan al ve çiz.
  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError(null);
    setBoxes([]);
    engineCall<{ data: string }>("doc.bytes", { path })
      .then(async ({ data }) => {
        const bytes = Uint8Array.from(atob(data), (c) => c.charCodeAt(0));
        if (!alive || !docRef.current) return;
        docRef.current.innerHTML = "";
        await renderAsync(new Blob([bytes]), docRef.current, styleRef.current ?? undefined, {
          className: "docx",
          inWrapper: true,
          breakPages: true,
          ignoreLastRenderedPageBreak: false,
          renderHeaders: true,
          renderFooters: true,
          renderFootnotes: true,
          renderEndnotes: true,
          // Görseller blob adresi yerine data: adresiyle; uygulamanın güvenlik politikası buna izin verir.
          useBase64URL: true,
          renderChanges: false,
          renderComments: false,
        });
        if (alive) setLoading(false);
      })
      .catch((e) => alive && (setError(String(e)), setLoading(false)));
    return () => {
      alive = false;
    };
  }, [path]);

  // Sayfayı alana sığdır.
  const measureFit = useCallback(() => {
    const page = docRef.current?.querySelector<HTMLElement>("section.docx");
    const wrap = wrapRef.current;
    if (!page || !wrap) return;
    const available = wrap.clientWidth - 32;
    setFit(Math.min(1, available / page.offsetWidth));
  }, []);

  useLayoutEffect(() => {
    if (loading) return;
    measureFit();
    const ro = new ResizeObserver(measureFit);
    if (wrapRef.current) ro.observe(wrapRef.current);
    return () => ro.disconnect();
  }, [loading, measureFit]);

  // Bulgu kutularını hesapla (kaydedilen dosyada bulgu gösterilmez).
  useLayoutEffect(() => {
    if (loading || mode === "kaydedilen" || !docRef.current) {
      setBoxes([]);
      return;
    }
    setBoxes(locate(docRef.current, findings, zoom));
  }, [loading, mode, findings, zoom]);

  useEffect(() => {
    if (!hovered || !wrapRef.current) return;
    wrapRef.current.querySelector(`[data-fid="${CSS.escape(hovered)}"]`)?.scrollIntoView({ block: "nearest" });
  }, [hovered]);

  const modes: Mode[] = target ? ["orijinal", "maskeli", "kaydedilen"] : ["orijinal", "maskeli"];
  const missing = useMemo(() => {
    const shown = new Set(boxes.map((b) => b.id));
    return findings.filter((f) => !shown.has(f.id)).length;
  }, [boxes, findings]);

  return (
    <div className="preview">
      <div className="preview-bar">
        {view ? null : plain ? (
          <span className="preview-title">{t("Belge önizlemesi")}</span>
        ) : (
          <div className="segmented" role="tablist">
            {modes.map((m) => (
              <button key={m} role="tab" aria-selected={mode === m} className={mode === m ? "on" : undefined} onClick={() => setMode(m)}>
                {t(MODE_LABEL[m])}
              </button>
            ))}
          </div>
        )}
        <div className="zoom" role="group" aria-label={t("Yakınlaştırma")}>
          <button className="icon-btn" aria-label={t("Uzaklaştır")} disabled={userZoom <= ZOOMS[0]} onClick={() => setUserZoom(ZOOMS[ZOOMS.indexOf(userZoom) - 1])}>
            <Icon name="minus" size={14} />
          </button>
          <button className="zoom-value" title={t("Sığdır")} onClick={() => setUserZoom(1)}>
            %{Math.round(zoom * 100)}
          </button>
          <button className="icon-btn" aria-label={t("Yakınlaştır")} disabled={userZoom >= ZOOMS[ZOOMS.length - 1]} onClick={() => setUserZoom(ZOOMS[ZOOMS.indexOf(userZoom) + 1])}>
            <Icon name="plus" size={14} />
          </button>
        </div>
        {onExpand && (
          <button className="icon-btn" aria-label={expanded ? t("Küçült") : t("Büyüt")} title={expanded ? t("Küçült") : t("Büyüt")} onClick={onExpand}>
            <Icon name={expanded ? "shrink" : "expand"} size={15} />
          </button>
        )}
      </div>

      <div className={expanded ? "sheet-wrap word-wrap tall" : "sheet-wrap word-wrap"} ref={wrapRef}>
        {error && <p className="field-error">{error}</p>}
        {loading && !error && <div className="sheet loading" style={{ aspectRatio: "595 / 842" }} />}
        <div ref={styleRef} />
        <div className="word-zoom" style={{ zoom, visibility: loading ? "hidden" : undefined }}>
          <div className="word-doc" ref={docRef} />
          <div className="word-boxes">
            {boxes.map((b, i) => {
              const f = b.finding;
              const off = excluded.has(f.id);
              const cls = [
                "box",
                `t-${f.type}`,
                off ? "off" : "on",
                mode === "maskeli" && !off ? `m-${methodOf(f.type)}` : "",
                hovered === f.id ? "hover" : "",
              ].join(" ");
              return (
                <div
                  key={`${b.id}:${i}`}
                  data-fid={b.first ? f.id : undefined}
                  role="button"
                  tabIndex={0}
                  className={cls}
                  style={{ left: b.left, top: b.top, width: b.width, height: b.height }}
                  title={`${t(f.type_label)} · ${off ? t("maskelenmeyecek") : t("maskelenecek")} ${t("(tıklayın)")}`}
                  onMouseEnter={() => onHover(f.id)}
                  onMouseLeave={() => onHover(null)}
                  onClick={() => onToggle(f.id)}
                  onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && onToggle(f.id)}
                >
                  {mode === "maskeli" && !off && b.first && f.replacement && <span>{f.replacement}</span>}
                </div>
              );
            })}
          </div>
        </div>
      </div>

      <p className="hint preview-hint">
        {plain
          ? t("Belge Word'deki gibi gösteriliyor. Tara'ya basınca bulgular üzerinde işaretlenir.")
          : mode === "kaydedilen"
            ? t("Diske yazılan maskeli Word dosyasının kendisi.")
            : mode === "maskeli"
              ? t("Kaydetmeden önce sonucun nasıl görüneceği; biçim, tablo ve yazı tipleri korunur.")
              : missing > 0
                ? t("Kutuya tıklayarak bulguyu dahil edin ya da çıkarın. {n} bulgu önizlemede gösterilemedi (gizli alan ya da bağlantı); listede yer alır ve yine maskelenir.", { n: missing })
                : t("Kutuya tıklayarak bulguyu dahil edin ya da çıkarın.")}
      </p>
    </div>
  );
}

/** Çizilmiş belgede bulgu değerlerini bulur, ekrandaki kutularını döndürür (yakınlaştırmasız px). */
function locate(root: HTMLElement, findings: PdfFinding[], zoom: number): Box[] {
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  const nodes: { node: Text; start: number }[] = [];
  let full = "";
  for (let n = walker.nextNode(); n; n = walker.nextNode()) {
    const tn = n as Text;
    nodes.push({ node: tn, start: full.length });
    full += tn.data.replace(/\s/g, " ");
  }
  const origin = root.getBoundingClientRect();
  const boxes: Box[] = [];
  const nextFrom = new Map<string, number>();

  const point = (offset: number): [Text, number] => {
    let lo = 0;
    let hi = nodes.length - 1;
    while (lo < hi) {
      const mid = (lo + hi + 1) >> 1;
      if (nodes[mid].start <= offset) lo = mid;
      else hi = mid - 1;
    }
    return [nodes[lo].node, offset - nodes[lo].start];
  };

  for (const f of findings) {
    const value = f.value.replace(/\s/g, " ");
    if (!value.trim()) continue;
    const at = full.indexOf(value, nextFrom.get(value) ?? 0);
    if (at < 0) continue;
    nextFrom.set(value, at + value.length);
    const range = document.createRange();
    const [sn, so] = point(at);
    const [en, eo] = point(at + value.length - 1);
    range.setStart(sn, so);
    range.setEnd(en, eo + 1);
    let first = true;
    for (const r of Array.from(range.getClientRects())) {
      if (r.width < 1 || r.height < 1) continue;
      boxes.push({
        id: f.id,
        finding: f,
        // getClientRects yakınlaştırılmış ekran koordinatı verir; kutular yakınlaştırılan kabın içinde.
        left: (r.left - origin.left) / zoom - 1,
        top: (r.top - origin.top) / zoom - 1,
        width: r.width / zoom + 2,
        height: r.height / zoom + 2,
        first,
      });
      first = false;
    }
  }
  return boxes;
}
