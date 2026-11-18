import { PointerEvent, useEffect, useMemo, useRef, useState } from "react";
import { engineCall, PdfFinding } from "./engine";
import { Icon } from "./ui";
import { useT } from "./i18n";

interface PageImage {
  image: string;
  width: number;
  height: number;
  pages: number;
}

export type PreviewMode = "orijinal" | "maskeli" | "kaydedilen";
export type Rect = [number, number, number, number];

const MODE_LABEL: Record<PreviewMode, string> = {
  orijinal: "Bulgular",
  maskeli: "Maskeli önizleme",
  kaydedilen: "Kaydedilen dosya",
};

// Bundan küçük çizimler (pt) yanlışlıkla tıklama sayılır.
const MIN_AREA_PT = 4;
// Yakınlaştırma basamakları (sayfanın önizleme genişliğine oranı).
const ZOOMS = [1, 1.5, 2, 3];

/**
 * Sayfa önizlemesi. Bulgular sayfanın üzerinde kutu olarak görünür; kutuya
 * tıklamak bulguyu dahil eder ya da çıkarır. "Alan seç" açıkken fareyle
 * sürükleyerek tespitin bulamadığı bir alan (etiketsiz imza, fotoğraf…)
 * eklenir. "Maskeli önizleme" sonucu kaydetmeden canlandırır, "Kaydedilen
 * dosya" gerçek çıktıyı gösterir. Sayfa görüntüleri yalnızca bellekte tutulur.
 */
export function PagePreview({
  source,
  target,
  pages,
  findings,
  excluded,
  methodOf,
  hovered,
  onHover,
  onToggle,
  onAddArea,
  onRemoveArea,
  page,
  onPage,
  plain = false,
  view,
  expanded = false,
  onExpand,
  dropped,
  onToggleDrop,
  readOnly = false,
}: {
  source: string;
  target: string | null;
  /** Bilinmiyorsa (taramadan önce) sayfa görüntüsüyle gelen sayı kullanılır. */
  pages?: number;
  findings: PdfFinding[];
  excluded: Set<string>;
  methodOf: (type: string) => string;
  hovered: string | null;
  onHover: (id: string | null) => void;
  onToggle: (id: string) => void;
  onAddArea: (page: number, rect: Rect) => void;
  onRemoveArea: (id: string) => void;
  page: number;
  onPage: (page: number) => void;
  /** Taramadan önce: yalnızca belgeyi göster (görünüm sekmeleri ve alan seçimi yok). */
  plain?: boolean;
  /** Görünüm dışarıdan yönetiliyorsa: sekmeler gösterilmez. */
  view?: "orijinal" | "maskeli" | "kaydedilen";
  expanded?: boolean;
  onExpand?: () => void;
  /** Paylaşılacak kopyadan çıkarılacak sayfalar (1'den); yalnızca çok sayfalı PDF. */
  dropped?: Set<number>;
  onToggleDrop?: (page: number) => void;
  /** Yalnızca bakmak için (ör. kaydedildikten sonra): alan seçimi yok. */
  readOnly?: boolean;
}) {
  const [modeState, setMode] = useState<PreviewMode>("orijinal");
  const t = useT();
  // Görünüm dışarıdan verilirse (Önce/Sonra düğmesi ekranın kendisinde) sekmeler maskelenir.
  const mode = view ?? modeState;
  const [zoom, setZoom] = useState(1);
  const [cache, setCache] = useState<Record<string, PageImage>>({});
  const [error, setError] = useState<string | null>(null);
  const [drawing, setDrawing] = useState(false);
  const [draft, setDraftState] = useState<{ x0: number; y0: number; x1: number; y1: number } | null>(null);
  // Olaylar arka arkaya gelince durum henüz güncellenmemiş olabilir; güncel taslak referansta.
  const draftRef = useRef<typeof draft>(null);
  const setDraft = (d: typeof draft) => {
    draftRef.current = d;
    setDraftState(d);
  };
  const sheetRef = useRef<HTMLDivElement>(null);

  // Kaydedilen dosya yalnızca maskeleme bittiğinde seçilebilir.
  useEffect(() => {
    setMode(target ? "kaydedilen" : "orijinal");
  }, [target]);

  const path = mode === "kaydedilen" && target ? target : source;
  // Yakınlaştırınca bulanık görünmesin diye daha büyük görüntü istenir (motor 1800 px ile sınırlar).
  const width = Math.min(1800, Math.round(1000 * Math.max(1, zoom * (expanded ? 1.4 : 1))));
  const key = `${path}#${page}@${width}`;
  const img = cache[key];

  useEffect(() => {
    if (img) return;
    let alive = true;
    setError(null);
    engineCall<PageImage>("doc.page", { path, page, width })
      .then((r) => alive && setCache((c) => ({ ...c, [key]: r })))
      .catch((e) => alive && setError(String(e)));
    return () => {
      alive = false;
    };
  }, [key, img, path, page, width]);

  // Kaynak değişince eski sayfa görüntülerini bellekten at.
  useEffect(() => setCache({}), [source]);

  // Esc ile alan seçimini bırak.
  useEffect(() => {
    if (!drawing) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && (setDrawing(false), setDraft(null));
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [drawing]);

  const onPageFindings = useMemo(() => findings.filter((f) => f.page === page), [findings, page]);
  const modes: PreviewMode[] = target ? ["orijinal", "maskeli", "kaydedilen"] : ["orijinal", "maskeli"];
  const canDraw = !plain && !readOnly && mode !== "kaydedilen" && !!img;
  // Kaydedilen kopyadan sayfa çıkarılmış olabilir; o görünümde sayı dosyanın kendisinden gelir.
  const pageCount = (mode === "kaydedilen" ? img?.pages : undefined) ?? pages ?? img?.pages ?? 1;

  /** Ekran koordinatını sayfa koordinatına (pt) çevirir. */
  function toPt(e: PointerEvent): [number, number] {
    const r = sheetRef.current!.getBoundingClientRect();
    const x = Math.min(Math.max(e.clientX - r.left, 0), r.width);
    const y = Math.min(Math.max(e.clientY - r.top, 0), r.height);
    return [(x / r.width) * img!.width, (y / r.height) * img!.height];
  }

  function onPointerDown(e: PointerEvent) {
    if (!drawing || !img || e.button !== 0) return;
    e.preventDefault();
    try {
      (e.currentTarget as Element).setPointerCapture(e.pointerId);
    } catch {
      // yakalama desteklenmezse sürükleme yine çalışır
    }
    const [x, y] = toPt(e);
    setDraft({ x0: x, y0: y, x1: x, y1: y });
  }

  function onPointerMove(e: PointerEvent) {
    const d = draftRef.current;
    if (!d) return;
    const [x, y] = toPt(e);
    setDraft({ ...d, x1: x, y1: y });
  }

  function onPointerUp() {
    const draft = draftRef.current;
    if (!draft) return;
    const rect: Rect = [
      Math.min(draft.x0, draft.x1),
      Math.min(draft.y0, draft.y1),
      Math.max(draft.x0, draft.x1),
      Math.max(draft.y0, draft.y1),
    ];
    setDraft(null);
    if (rect[2] - rect[0] >= MIN_AREA_PT && rect[3] - rect[1] >= MIN_AREA_PT) onAddArea(page, rect);
  }

  function pct([x0, y0, x1, y1]: Rect) {
    return {
      left: `${(x0 / img!.width) * 100}%`,
      top: `${(y0 / img!.height) * 100}%`,
      width: `${((x1 - x0) / img!.width) * 100}%`,
      height: `${((y1 - y0) / img!.height) * 100}%`,
    };
  }

  return (
    <div className="preview">
      <div className="preview-bar">
        {view ? null : plain ? (
          <span className="preview-title">{t("Belge önizlemesi")}</span>
        ) : (
        <div className="segmented" role="tablist">
          {modes.map((m) => (
            <button
              key={m}
              role="tab"
              aria-selected={mode === m}
              className={mode === m ? "on" : undefined}
              onClick={() => {
                setMode(m);
                if (m === "kaydedilen") setDrawing(false);
              }}
            >
              {t(MODE_LABEL[m])}
            </button>
          ))}
        </div>
        )}
        {!plain && !readOnly && (
        <button
          className={drawing ? "btn small on" : "btn small"}
          disabled={!canDraw}
          aria-pressed={drawing}
          title={t("Fareyle sürükleyerek maskelenecek bir alan seçin (Esc: bırak)")}
          onClick={() => setDrawing(!drawing)}
        >
          <Icon name="crop" size={14} /> {drawing ? t("Seçim açık") : t("Alan seç")}
        </button>
        )}
        <div className="zoom" role="group" aria-label={t("Yakınlaştırma")}>
          <button className="icon-btn" aria-label={t("Uzaklaştır")} disabled={zoom <= ZOOMS[0]} onClick={() => setZoom(ZOOMS[ZOOMS.indexOf(zoom) - 1])}>
            <Icon name="minus" size={14} />
          </button>
          <button className="zoom-value" title={t("Sığdır")} onClick={() => setZoom(1)}>
            %{Math.round(zoom * 100)}
          </button>
          <button className="icon-btn" aria-label={t("Yakınlaştır")} disabled={zoom >= ZOOMS[ZOOMS.length - 1]} onClick={() => setZoom(ZOOMS[ZOOMS.indexOf(zoom) + 1])}>
            <Icon name="plus" size={14} />
          </button>
        </div>
        {onExpand && (
          <button className="icon-btn" aria-label={expanded ? t("Küçült") : t("Büyüt")} title={expanded ? t("Küçült") : t("Büyüt")} onClick={onExpand}>
            <Icon name={expanded ? "shrink" : "expand"} size={15} />
          </button>
        )}
        <div className="pager">
          <button className="icon-btn prev" aria-label={t("Önceki sayfa")} disabled={page <= 1} onClick={() => onPage(page - 1)}>
            <Icon name="chevron" size={14} />
          </button>
          <span>
            {page} / {pageCount}
          </span>
          <button className="icon-btn" aria-label={t("Sonraki sayfa")} disabled={page >= pageCount} onClick={() => onPage(page + 1)}>
            <Icon name="chevron" size={14} />
          </button>
        </div>
      </div>

      {onToggleDrop && pageCount > 1 && mode !== "kaydedilen" && (
        <div className="page-drop-bar">
          <span>
            {dropped?.has(page) ? t("Sayfa {page} kopyada olmayacak", { page }) : t("Sayfa {page} kopyada yer alacak", { page })}
          </span>
          <button className={dropped?.has(page) ? "btn small" : "btn small subtle"} onClick={() => onToggleDrop(page)}>
            <Icon name={dropped?.has(page) ? "undo" : "trash"} size={14} />
            {dropped?.has(page) ? t("Sayfayı geri al") : t("Bu sayfayı kopyadan çıkar")}
          </button>
        </div>
      )}

      <div className={expanded ? "sheet-wrap tall" : "sheet-wrap"}>
        {error ? (
          <p className="field-error">{error}</p>
        ) : !img ? (
          <div className="sheet loading" style={{ aspectRatio: "595 / 842" }} />
        ) : (
          <div
            ref={sheetRef}
            className={drawing ? "sheet drawing" : "sheet"}
            style={{ aspectRatio: `${img.width} / ${img.height}`, width: `${zoom * 100}%` }}
            onPointerDown={onPointerDown}
            onPointerMove={onPointerMove}
            onPointerUp={onPointerUp}
          >
            <img src={img.image} alt={t("Sayfa {page}", { page })} draggable={false} />
            {dropped?.has(page) && mode !== "kaydedilen" && (
              <div className="page-dropped">
                <Icon name="trash" size={28} />
                <b>{t("Bu sayfa paylaşılacak kopyada olmayacak")}</b>
              </div>
            )}
            {mode !== "kaydedilen" &&
              onPageFindings.flatMap((f) =>
                f.rects.map((r, i) => {
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
                      key={`${f.id}:${i}`}
                      role="button"
                      tabIndex={0}
                      className={cls}
                      style={pct(r)}
                      title={`${t(f.type_label)} · ${off ? t("maskelenmeyecek") : t("maskelenecek")} ${t("(tıklayın)")}`}
                      onMouseEnter={() => onHover(f.id)}
                      onMouseLeave={() => onHover(null)}
                      onPointerDown={(e) => drawing || e.stopPropagation()}
                      onClick={() => !drawing && onToggle(f.id)}
                      onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && onToggle(f.id)}
                    >
                      {mode === "maskeli" && !off && i === 0 && f.replacement && <span>{f.replacement}</span>}
                      {f.kind === "alan" && mode === "orijinal" && (
                        <button
                          className="box-remove"
                          aria-label={t("Alanı kaldır")}
                          onPointerDown={(e) => e.stopPropagation()}
                          onClick={(e) => {
                            e.stopPropagation();
                            onRemoveArea(f.id);
                          }}
                        >
                          <Icon name="x" size={10} />
                        </button>
                      )}
                    </div>
                  );
                }),
              )}
            {draft && (
              <div
                className="box draft"
                style={pct([
                  Math.min(draft.x0, draft.x1),
                  Math.min(draft.y0, draft.y1),
                  Math.max(draft.x0, draft.x1),
                  Math.max(draft.y0, draft.y1),
                ])}
              />
            )}
          </div>
        )}
      </div>

      <p className="hint preview-hint">
        {readOnly
          ? t("Kaydedilmeden önceki görünüm; kaydedilen kopyayla aynı içeriktedir.")
          : plain
          ? t("Belgenin kendisi. Tara'ya basınca bulgular burada işaretlenir.")
          : drawing
          ? t("Maskelenecek alanı fareyle sürükleyerek çizin. Alandaki metin, görsel ve çizim silinir. Bitirince “Seçim açık”a basın ya da Esc.")
          : mode === "orijinal"
            ? t("Kutuya tıklayarak bulguyu dahil edin ya da çıkarın. Tespitin bulamadığı yerler için “Alan seç”.")
            : mode === "maskeli"
              ? t("Kaydetmeden önce sonucun nasıl görüneceği. Bulanık dolgu, orijinalden bilgi taşımaz.")
              : t("Diske yazılan maskeli dosyanın kendisi.")}
      </p>
    </div>
  );
}
