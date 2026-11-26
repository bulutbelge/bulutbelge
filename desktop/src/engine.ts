import { invoke } from "@tauri-apps/api/core";
import { hataKaydet } from "./SorunBildir";

/**
 * Python motoruna istek gönderir. Hata durumunda motorun mesajıyla reddeder.
 * Hata, "Sorun bildir" metni için bellekte tutulur (yollar ve e-postalar silinerek); `kaydet` false ise tutulmaz.
 */
export function engineCall<T>(method: string, params?: Record<string, unknown>, kaydet = true): Promise<T> {
  return invoke<T>("engine_call", { method, params })
    .catch((err) => {
      const msg = String(err);
      if (msg.includes("motor beklenmedik") || msg.includes("motora yazılamadı")) {
        return invoke<T>("engine_call", { method, params });
      }
      throw err;
    })
    .catch((err) => {
      if (kaydet) hataKaydet(method, err);
      throw err;
    });
}

export interface EngineVersion {
  engine: string;
  core: string;
  python: string;
}

export interface MethodOption {
  key: string;
  label: string;
  /** Türün örnek değerine bu yöntem uygulanınca yazılan (motor üretir); karartmada yok. */
  sample?: string | null;
}

export interface DataTypeInfo {
  key: string;
  label: string;
  default_method: string;
  tag: string;
  /** Açılıp kapatılmayan tür (elle seçilen alan): yalnızca yöntemi seçilir. */
  always_on: boolean;
  methods: MethodOption[];
}

export interface TypeRule {
  enabled: boolean;
  method: string;
}

export interface ColumnRule {
  header: string;
  type?: string;
  action?: string;
}

export interface CustomPattern {
  name: string;
  pattern: string;
  /** Hangi kategori grubunda yer alacağı (kisi, iletisim, finans, sirket, gorsel, teknik, diger) */
  group?: string;
  /** Bu özel alanın ilgili kural takımında açık olup olmadığı */
  enabled?: boolean;
  /** Maskeleme yöntemi: karartma | etiket | son4 | bulanik */
  method?: string;
  /** Kontrol yöntemi: etiket | ornek | kelime | regex */
  mode?: string;
  /** Kullanıcının girdiği etiket/örnek/kelime değeri */
  hint?: string;
}

export interface Rules {
  types: Record<string, TypeRule>;
  terms: string[];
  patterns: CustomPattern[];
  whitelist: string[];
  /** Kurum sözlüğü: kurum adları ve genel unvanlar; kişi adı/adres bulgusu bunların içindeyse atlanır. */
  institutions?: string[];
  /** Excel/CSV sütun kuralları: başlık → tür (ya da eylem). */
  column_rules?: ColumnRule[];
  signature_labels: string[];
  /** Takma ad kapsamı: yoksa ortak; "belge" ise her belgede yeni numara. */
  pseudonym_scope?: "belge";
  /** Kural takımının adı; yalnızca işlem günlüğüne yazılır. */
  profile_name?: string;
}

export interface TestSpan {
  start: number;
  end: number;
  type: string;
  type_label: string;
}

export interface PdfFinding {
  id: string;
  page: number;
  type: string;
  type_label: string;
  source: string;
  value: string;
  replacement: string;
  /** "dusuk": kişisel bilgi olabilir ama doğrulanamadı; "Emin olamadıklarımız" kartında gelir. */
  confidence: "yuksek" | "orta" | "dusuk";
  locatable: boolean;
  kind: "metin" | "gorsel" | "cizim" | "alan" | "yuz";
  /** İmza önizlemesi (data URL); yalnızca bellekte, göz düğmesiyle gösterilir. */
  preview: string | null;
  /** Sayfadaki konum (pt): [x0, y0, x1, y1] */
  rects: [number, number, number, number][];
  /** Metin belgede (XML/TXT/CSV) ya da Office biriminde karakter aralığı: [başlangıç, bitiş) */
  span?: [number, number];
  /** Office belgelerinde metnin bulunduğu birim (paragraf, hücre): "parça:sıra" */
  unit?: string;
}

/** "pdf" | "gorsel" (fotoğraf, taranmış görsel) | "metin" (XML, CSV, JSON, TXT, LOG) | "word" (DOCX) */
export type DocFormat = "pdf" | "gorsel" | "metin" | "word" | "sunum" | "tablo" | "arsiv";

export interface FormatsInfo {
  pdf: string[];
  gorsel: string[];
  metin: string[];
  word: string[];
  sunum: string[];
  tablo: string[];
  /** E-posta (.eml); önizlemesi metin belge gibidir */
  eposta?: string[];
  /** UYAP belgesi (.udf); önizlemesi metin belge gibidir */
  udf?: string[];
  arsiv?: string[];
  all: string[];
  /** OCR dil dosyaları kurulu mu (fotoğraf ve taranmış sayfalarda otomatik tespit) */
  ocr: boolean;
}

export function extOf(path: string): string {
  const name = path.slice(Math.max(path.lastIndexOf("\\"), path.lastIndexOf("/")) + 1);
  const i = name.lastIndexOf(".");
  return i > 0 ? name.slice(i + 1).toLowerCase() : "";
}

export function formatOf(path: string, formats: FormatsInfo | null): DocFormat | null {
  const ext = extOf(path);
  if (!formats) return ext === "pdf" ? "pdf" : null;
  if (formats.pdf.includes(ext)) return "pdf";
  if (formats.gorsel.includes(ext)) return "gorsel";
  if (formats.metin.includes(ext) || formats.eposta?.includes(ext) || formats.udf?.includes(ext)) return "metin";
  if (formats.word.includes(ext)) return "word";
  if (formats.sunum.includes(ext)) return "sunum";
  if (formats.tablo.includes(ext)) return "tablo";
  if (formats.arsiv?.includes(ext)) return "arsiv";
  return null;
}

export interface ScanResult {
  format: DocFormat;
  /** Metin belgenin içeriği (önizleme için, yalnızca bellekte) */
  text?: string;
  /** OCR ile okunan sayfalar */
  ocr_pages?: number[];
  pages: number;
  warnings: string[];
  default_target: string;
  /** Dosya adı kişi adı taşıyorsa adsız önerilen hedef yolu */
  suggested_target?: string;
  findings: PdfFinding[];
}

export interface MaskResult {
  target: string;
  masked: number;
  warnings: string[];
  /** Kopyadan çıkarılan sayfa sayısı (yalnızca PDF) */
  dropped?: number;
  /** Kopya parolayla korundu (yalnızca PDF) */
  encrypted?: boolean;
  /** Kaydedilen yol seçilenden farklıysa nedeni (var olan dosya, uzantı) */
  changed?: string | null;
  /** Kaçağa rağmen kaydedildiyse kopyada açık kalan türler (değer değil) */
  leaked?: string[];
}
