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
  // Belge kapalı bir shadow root içinde çizilir (güvenlik taraması F12-F14, F28): belgenin CSS'i uygulamanın
  // geri kalanına ulaşmaz. Kök (host) bu öğedir; çizim ve stil kabı `docShadow` ile shadow root'ta oluşturulur.
  const docRef = useRef<HTMLDivElement>(null);

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
        const shadow = docShadow(docRef.current);
        shadow.root.adoptedStyleSheets = [];
        shadow.body.replaceChildren();
        await renderAsync(new Blob([bytes]), shadow.body, shadow.styles, {
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
        if (!alive || !docRef.current) return;
        neutralizeRenderedDoc(shadow.body);
        shadow.root.adoptedStyleSheets = [baseSheet(), ...adoptRenderedStyles(shadow.styles, shadow.body)];
        setLoading(false);
      })
      .catch((e) => alive && (setError(String(e)), setLoading(false)));
    return () => {
      alive = false;
    };
  }, [path]);

  // Sayfayı alana sığdır.
  const measureFit = useCallback(() => {
    const page = docRef.current && docShadow(docRef.current).body.querySelector<HTMLElement>("section.docx");
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
    setBoxes(locate(docShadow(docRef.current).body, docRef.current, findings, zoom));
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
        <div className="word-zoom" style={{ zoom, visibility: loading ? "hidden" : undefined }}>
          <div className="word-doc-frame">
            <div className="word-doc" ref={docRef} />
          </div>
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

type DocShadow = { root: ShadowRoot; body: HTMLDivElement; styles: HTMLDivElement };
const shadows = new WeakMap<HTMLElement, DocShadow>();

/** Önizleme kökünün kapalı shadow root'u (bir kez oluşturulur): çizim kabı ve docx-preview'un stil kabı. */
function docShadow(host: HTMLElement): DocShadow {
  let s = shadows.get(host);
  if (!s) {
    const root = host.attachShadow({ mode: "closed" });
    const styles = document.createElement("div");
    const body = document.createElement("div");
    root.append(styles, body);
    s = { root, body, styles };
    shadows.set(host, s);
  }
  return s;
}

let base: CSSStyleSheet | null = null;

/**
 * Shadow root'a uygulamanın kendi (güvenilir) kuralları: belge eskiden ana belgede çizildiği için uygulamanın genel
 * `* { box-sizing }` kuralı ve önizleme düzeltmeleri (gri çerçeve yerine uygulama zemini) ona da uygulanıyordu.
 * Aynı özgüllükle (`:host .x` = `.word-doc .x`) ve belge stillerinden önce eklenir; çizim aynı kalır.
 * Bağlantıların `href`'i kaldırıldığı için tarayıcının bağlantı görünümü (renk, alt çizgi) burada verilir.
 */
function baseSheet(): CSSStyleSheet {
  if (!base) {
    base = new CSSStyleSheet();
    base.replaceSync(`
      * { box-sizing: border-box; }
      a { color: LinkText; text-decoration: underline; }
      :host .docx-wrapper { padding: 0; gap: 16px; background: transparent; }
      :host .docx-wrapper > section.docx {
        margin-bottom: 16px;
        box-shadow: 0 1px 3px rgb(0 0 0 / 18%), 0 6px 20px rgb(0 0 0 / 10%);
      }
    `);
  }
  return base;
}

/**
 * İçerik Güvenlik Politikası (CSP) `style-src 'self'` (unsafe-inline yok, TAKIP 1.90): docx-preview'un ürettiği
 * `<style>` öğeleri ve `style="..."` öznitelikleri tarayıcı tarafından uygulanmaz. CSSOM ile verilen stiller ise
 * politikaya tabi değildir; bu yüzden çizimden sonra stiller CSSOM ile, ama yalnızca belgenin shadow root'unda
 * uygulanır (güvenlik taraması F13, F14, F28: belge CSS'i eskiden `document.adoptedStyleSheets`e, yani bütün
 * uygulamaya giriyordu):
 *  - docx-preview'un stil kabındaki `<style>` metinleri `CSSStyleSheet`e çevrilip döndürülür (çağıran shadow
 *    root'a ekler). Çizim kabında bulunan `<style>` docx-preview'un değil, belgeden sızan işaretlemedir (F12):
 *    uygulanmadan silinir.
 *  - `style` öznitelikleri ham metin olarak kopyalanmaz (F26, F27): bildirimler ayrıştırılır, yalnızca izin
 *    verilenler `style.setProperty` ile yeniden yazılır (bkz. `safeDeclarations`).
 * Shadow root'un kabı (`.word-doc-frame`) `contain: layout` ile sabit konumlu öğeleri de önizleme alanında tutar.
 */
export function adoptRenderedStyles(styleContainer: HTMLElement, docRoot: HTMLElement): CSSStyleSheet[] {
  for (const el of Array.from(docRoot.querySelectorAll("style"))) el.remove();
  const sheets: CSSStyleSheet[] = [];
  for (const el of Array.from(styleContainer.querySelectorAll("style"))) {
    const css = el.textContent ?? "";
    el.remove();
    if (!css.trim()) continue;
    const sheet = new CSSStyleSheet();
    try {
      sheet.replaceSync(css);
    } catch {
      continue; // bozuk/desteklenmeyen kural: önizleme stilsiz kalır, uygulama çalışmaya devam eder
    }
    sheets.push(sheet);
  }
  for (const el of Array.from(docRoot.querySelectorAll<HTMLElement | SVGElement>("[style]"))) {
    const decls = safeDeclarations(el.getAttribute("style") ?? "", el instanceof SVGElement);
    el.removeAttribute("style");
    for (const [name, value, priority] of decls) el.style.setProperty(name, value, priority);
  }
  return sheets;
}

// VML şekilleri (docx-preview bunları `setAttribute("style", ...)` ile svg'ye ham kopyalar): yalnızca yer ve boyut.
const SVG_PROPS = new Set([
  "position", "left", "top", "right", "bottom", "width", "height",
  "margin-left", "margin-top", "margin-right", "margin-bottom", "z-index", "visibility", "rotate",
]);
// HTML öğelerinin stilleri docx-preview'da CSSOM ile tek tek verilir; burada yalnızca tehlikeli olanlar atılır.
const DENY_PROPS = new Set(["content", "pointer-events", "behavior", "-moz-binding"]);
const POSITIONS = new Set(["static", "relative", "absolute"]);

/** Stil metnini tarayıcının CSS ayrıştırıcısıyla bildirimlere ayırır ve izin verilenleri döndürür. */
export function safeDeclarations(css: string, svg: boolean): [string, string, string][] {
  // Bağlantısız bir öğenin CSSOM'u yalnızca ayrıştırıcı olarak kullanılır; öğe sayfaya eklenmez.
  const parser = document.createElement("div").style;
  parser.cssText = css;
  const out: [string, string, string][] = [];
  for (let i = 0; i < parser.length; i++) {
    const name = parser.item(i);
    const value = parser.getPropertyValue(name);
    if (svg ? !SVG_PROPS.has(name) : DENY_PROPS.has(name)) continue;
    if (name === "position" && !POSITIONS.has(value.trim().toLowerCase())) continue;
    if (/url\(|image-set\(|expression\(/i.test(value)) continue;
    // Görünüm alanı birimleri (100vw gibi) belgeyi pencere boyutuna gerer; docx-preview bunları üretmez.
    if (/\d(?:[sld]?v(?:w|h|min|max))\b/i.test(value)) continue;
    out.push([name, value, parser.getPropertyPriority(name)]);
  }
  return out;
}

// docx-preview'un kendisinin üretmediği, belgeden sızabilecek (F12: `w:sym w:char` → innerHTML) etkin öğeler.
const DROP_TAGS = "script, style, link, meta, base, form, input, button, textarea, select, object, embed, frame, frameset, template, portal";

/**
 * Çizilen belgeyi etkisizleştirir (F12, F16, F25):
 *  - belge içinden sızan etkin öğeler ve satır içi olay öznitelikleri silinir,
 *  - bağlantıların `href`'i kaldırılır (metin ve görünüm kalır; tıklama uygulama penceresini götüremez),
 *  - altChunk (gömülü HTML) çerçeveleri betiksiz, gezinmesiz kum havuzlu bir kopyayla değiştirilir.
 */
export function neutralizeRenderedDoc(root: HTMLElement) {
  for (const el of Array.from(root.querySelectorAll(DROP_TAGS))) el.remove();
  for (const el of Array.from(root.querySelectorAll("*"))) {
    for (const attr of Array.from(el.attributes)) {
      if (/^on/i.test(attr.name) || /^(formaction|srcset|ping)$/i.test(attr.name)) el.removeAttribute(attr.name);
    }
  }
  for (const a of Array.from(root.querySelectorAll("a"))) {
    a.removeAttribute("href");
    a.removeAttributeNS("http://www.w3.org/1999/xlink", "href");
    a.removeAttribute("target");
  }
  for (const frame of Array.from(root.querySelectorAll("iframe"))) {
    const safe = document.createElement("iframe");
    safe.setAttribute("sandbox", "");
    safe.setAttribute("referrerpolicy", "no-referrer");
    safe.srcdoc = frame.srcdoc;
    frame.replaceWith(safe);
  }
  if (!guarded.has(root)) {
    guarded.add(root);
    // Ek güvence: belge içindeki hiçbir tıklama gezinmeye dönüşmez.
    root.addEventListener("click", (e) => {
      if (e.composedPath().some((n) => n instanceof Element && n.closest("a"))) e.preventDefault();
    });
  }
}

const guarded = new WeakSet<HTMLElement>();

/** Çizilmiş belgede bulgu değerlerini bulur, ekrandaki kutularını döndürür (yakınlaştırmasız px). */
function locate(root: HTMLElement, originEl: HTMLElement, findings: PdfFinding[], zoom: number): Box[] {
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  const nodes: { node: Text; start: number }[] = [];
  let full = "";
  for (let n = walker.nextNode(); n; n = walker.nextNode()) {
    const tn = n as Text;
    nodes.push({ node: tn, start: full.length });
    full += tn.data.replace(/\s/g, " ");
  }
  const origin = originEl.getBoundingClientRect();
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
