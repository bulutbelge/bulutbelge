import { ReactNode } from "react";
import { PdfFinding } from "./engine";
import { t } from "./i18n";

/** Bulgu işaretleme ayarları (slayt, tablo ve metin önizlemelerinde ortak). */
export interface MarkOptions {
  excluded: Set<string>;
  masked: boolean;
  methodOf: (type: string) => string;
  hovered: string | null;
  onHover: (id: string | null) => void;
  onToggle: (id: string) => void;
}

/** Birim anahtarına göre bulgular ("parça:sıra" → bulgular). */
export function byUnit(findings: PdfFinding[]): Map<string, PdfFinding[]> {
  const m = new Map<string, PdfFinding[]>();
  for (const f of findings) {
    if (!f.unit || !f.span) continue;
    const list = m.get(f.unit) ?? [];
    list.push(f);
    m.set(f.unit, list);
  }
  return m;
}

/**
 * Bir metin parçasını (birim içinde `offset`ten başlayan) bulgu işaretleriyle çizer.
 * Bulgu birden çok parçaya yayılıyorsa her parçada işaretlenir; maskeli görünümde yerine
 * yazılacak metin yalnızca bulgunun ilk parçasında gösterilir.
 */
export function marked(text: string, offset: number, findings: PdfFinding[] | undefined, o: MarkOptions): ReactNode[] {
  if (!findings?.length) return [text];
  const out: ReactNode[] = [];
  let pos = 0;
  const end = offset + text.length;
  const hits = findings
    .filter((f) => f.span![0] < end && f.span![1] > offset)
    .sort((a, b) => a.span![0] - b.span![0]);
  for (const f of hits) {
    const s = Math.max(f.span![0], offset) - offset;
    const e = Math.min(f.span![1], end) - offset;
    if (s < pos) continue;
    if (s > pos) out.push(text.slice(pos, s));
    const off = o.excluded.has(f.id);
    const showMask = o.masked && !off;
    const first = f.span![0] >= offset;
    out.push(
      <mark
        key={`${f.id}:${offset}`}
        data-fid={f.id}
        role="button"
        tabIndex={0}
        className={[
          "hit",
          `t-${f.type}`,
          off ? "off" : "on",
          showMask ? `m-${o.methodOf(f.type)}` : "",
          o.hovered === f.id ? "hover" : "",
        ].join(" ")}
        title={`${t(f.type_label)} · ${off ? t("maskelenmeyecek") : t("maskelenecek")} ${t("(tıklayın)")}`}
        onMouseEnter={() => o.onHover(f.id)}
        onMouseLeave={() => o.onHover(null)}
        onClick={(ev) => {
          ev.stopPropagation();
          o.onToggle(f.id);
        }}
        onKeyDown={(ev) => (ev.key === "Enter" || ev.key === " ") && o.onToggle(f.id)}
      >
        {showMask ? (first ? f.replacement || "█████" : "") : text.slice(s, e)}
      </mark>,
    );
    pos = e;
  }
  if (pos < text.length) out.push(text.slice(pos));
  return out;
}
