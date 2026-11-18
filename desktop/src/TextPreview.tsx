import { useEffect, useMemo, useRef, useState } from "react";
import { PdfFinding } from "./engine";
import { Icon } from "./ui";
import { useT } from "./i18n";

type Mode = "orijinal" | "maskeli";

interface Piece {
  text: string;
  finding?: PdfFinding;
  tag?: boolean; // XML etiketi (soluk gösterilir)
  embedded?: number; // gömülü dosya (base64) uzunluğu; önizlemede tek rozet olarak gösterilir
}

// e-Fatura'daki gömülü PDF/XSLT gibi uzun base64 metinler. Eşik motordakiyle aynı (textdoc._BASE64).
const BASE64_RUN = /[A-Za-z0-9+/=\s]{1000,}/g;

// Çok büyük dosyalarda tarayıcı yavaşlamasın; önizleme baştan bu kadarını gösterir.
const MAX_CHARS = 300_000;

/**
 * XML, TXT ve CSV önizlemesi. Bulgular metnin içinde renkli işaretlenir;
 * tıklamak bulguyu dahil eder ya da çıkarır. "Maskeli önizleme", kaydedilecek
 * dosyada yazacak olanı gösterir. Metin yalnızca bellekte tutulur.
 */
export function TextPreview({
  text,
  isXml,
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
  text: string;
  isXml: boolean;
  findings: PdfFinding[];
  excluded: Set<string>;
  methodOf: (type: string) => string;
  hovered: string | null;
  onHover: (id: string | null) => void;
  onToggle: (id: string) => void;
  /** Taramadan önce: yalnızca içeriği göster. */
  plain?: boolean;
  /** Görünüm dışarıdan yönetiliyorsa: sekmeler gösterilmez. */
  view?: "orijinal" | "maskeli" | "kaydedilen";
  expanded?: boolean;
  onExpand?: () => void;
}) {
  const [modeState, setMode] = useState<Mode>("orijinal");
  const t = useT();
  // Dışarıdan verilen görünüm (metin belgede kaydedilen dosya = maskeli görünüm).
  const mode: Mode = view ? (view === "orijinal" ? "orijinal" : "maskeli") : modeState;
  const bodyRef = useRef<HTMLDivElement>(null);
  const shown = text.length > MAX_CHARS ? text.slice(0, MAX_CHARS) : text;
  const lines = useMemo(() => buildLines(shown, findings, isXml), [shown, findings, isXml]);

  // Tablodan bir bulgunun üzerine gelince metinde o yere kaydır.
  useEffect(() => {
    if (!hovered) return;
    bodyRef.current?.querySelector(`[data-fid="${CSS.escape(hovered)}"]`)?.scrollIntoView({ block: "nearest" });
  }, [hovered]);

  return (
    <div className="preview">
      <div className="preview-bar">
        {view ? null : plain ? (
          <span className="preview-title">{t("Belge önizlemesi")}</span>
        ) : (
        <div className="segmented" role="tablist">
          {(["orijinal", "maskeli"] as Mode[]).map((m) => (
            <button key={m} role="tab" aria-selected={mode === m} className={mode === m ? "on" : undefined} onClick={() => setMode(m)}>
              {m === "orijinal" ? t("Bulgular") : t("Maskeli önizleme")}
            </button>
          ))}
        </div>
        )}
        {onExpand && (
          <button className="icon-btn" aria-label={expanded ? t("Küçült") : t("Büyüt")} title={expanded ? t("Küçült") : t("Büyüt")} onClick={onExpand}>
            <Icon name={expanded ? "shrink" : "expand"} size={15} />
          </button>
        )}
        <span className="pager">{t("{n} satır", { n: lines.length })}</span>
      </div>

      <div className={expanded ? "code-view tall" : "code-view"} ref={bodyRef}>
        {lines.map((line, i) => (
          <div className="code-line" key={i}>
            <span className="ln">{i + 1}</span>
            <span className="lc">
              {line.map((p, j) => {
                if (p.embedded)
                  return (
                    <span key={j} className="embedded" title={t("Taranamaz; maskeli kopyada içeriği silinir")}>
                      {t("gömülü dosya · {kb} KB · silinecek", { kb: Math.max(1, Math.round((p.embedded * 3) / 4 / 1024)) })}
                    </span>
                  );
                if (!p.finding) return p.tag ? <span key={j} className="tag">{p.text}</span> : p.text;
                const f = p.finding;
                const off = excluded.has(f.id);
                const masked = mode === "maskeli" && !off;
                return (
                  <mark
                    key={j}
                    data-fid={f.id}
                    role="button"
                    tabIndex={0}
                    className={["hit", `t-${f.type}`, off ? "off" : "on", masked ? `m-${methodOf(f.type)}` : "", hovered === f.id ? "hover" : ""].join(" ")}
                    title={`${t(f.type_label)} · ${off ? t("maskelenmeyecek") : t("maskelenecek")} ${t("(tıklayın)")}`}
                    onMouseEnter={() => onHover(f.id)}
                    onMouseLeave={() => onHover(null)}
                    onClick={() => onToggle(f.id)}
                    onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && onToggle(f.id)}
                  >
                    {masked ? (p.first ? f.replacement : "") : p.text}
                  </mark>
                );
              })}
              {line.length === 0 && "​"}
            </span>
          </div>
        ))}
      </div>

      <p className="hint preview-hint">
        {plain
          ? t("Dosyanın içeriği. Tara'ya basınca bulgular burada işaretlenir.")
          : text.length > MAX_CHARS
          ? t("Önizleme ilk {n} karakteri gösteriyor; maskeleme dosyanın tamamına uygulanır.", { n: MAX_CHARS.toLocaleString("tr") })
          : mode === "orijinal"
            ? t("İşarete tıklayarak bulguyu dahil edin ya da çıkarın.")
            : isXml
              ? t("Yalnızca değerler değişir; etiketler ve belge yapısı korunur. Gömülü dosyalar silinir.")
              : t("Kaydedilecek dosyada yazacak olan. Satır sonları ve karakter kodlaması korunur.")}
      </p>
    </div>
  );
}

interface LinePiece extends Piece {
  first?: boolean; // birden çok satıra bölünen bulgunun ilk parçası
}

/** Metni bulgu ve (XML'de) etiket parçalarına, sonra satırlara böler. */
function buildLines(text: string, findings: PdfFinding[], isXml: boolean): LinePiece[][] {
  const tags: [number, number][] = [];
  if (isXml) for (const m of text.matchAll(/<[^<>]+>/g)) tags.push([m.index!, m.index! + m[0].length]);

  const pieces: LinePiece[] = [];
  const plain = (a: number, b: number) => {
    if (!isXml) return plainTags(a, b);
    let pos = a;
    for (const m of text.slice(a, b).matchAll(BASE64_RUN)) {
      const s = a + m.index!;
      const e = s + m[0].length;
      // Yalnızca gerçekten base64 olan (boşluk dışında harf/rakam ağırlıklı) uzun bölümler.
      if (!m[0].trim() || /\s{40,}/.test(m[0])) continue;
      plainTags(pos, s);
      pieces.push({ text: "", embedded: m[0].replace(/\s/g, "").length });
      pos = e;
    }
    plainTags(pos, b);
  };
  const plainTags = (a: number, b: number) => {
    let pos = a;
    for (const [s, e] of tags) {
      if (e <= pos || s >= b) continue;
      if (s > pos) pieces.push({ text: text.slice(pos, s) });
      pieces.push({ text: text.slice(Math.max(s, pos), Math.min(e, b)), tag: true });
      pos = Math.min(e, b);
    }
    if (pos < b) pieces.push({ text: text.slice(pos, b) });
  };

  const spans = findings
    .filter((f) => f.span && f.span[1] <= text.length)
    .sort((x, y) => x.span![0] - y.span![0]);
  let cursor = 0;
  for (const f of spans) {
    const [s, e] = f.span!;
    if (s < cursor) continue;
    plain(cursor, s);
    pieces.push({ text: text.slice(s, e), finding: f });
    cursor = e;
  }
  plain(cursor, text.length);

  const lines: LinePiece[][] = [[]];
  for (const p of pieces) {
    p.text.split("\n").forEach((part, i) => {
      if (i > 0) lines.push([]);
      const clean = part.replace(/\r$/, "");
      if (clean || p.embedded || (p.finding && i === 0)) lines[lines.length - 1].push({ ...p, text: clean, first: i === 0 });
    });
  }
  return lines;
}
