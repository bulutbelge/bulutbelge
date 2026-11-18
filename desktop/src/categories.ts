import { DataTypeInfo, PdfFinding } from "./engine";
import { t } from "./i18n";

/**
 * Kullanıcıya gösterilen bilgi grupları. Motor 20'ye yakın veri türü bulur; ekranda bunlar
 * herkesin anlayacağı birkaç gruba toplanır ("TC kimlik no", "pasaport no" → "Kimlik numaraları").
 * Bir türün hangi gruba gittiği yalnızca burada tanımlıdır.
 */
export interface Category {
  key: string;
  label: string;
  icon: "user" | "idcard" | "phone" | "pin" | "card" | "calendar" | "pen" | "tag" | "lock";
  types: string[];
}

export const CATEGORIES: Category[] = [
  { key: "isim", label: "İsimler", icon: "user", types: ["kisi_adi", "kurum_unvani"] },
  { key: "kimlik", label: "Kimlik numaraları", icon: "idcard", types: ["tc_kimlik", "vkn", "vergi_dairesi", "pasaport", "ehliyet", "sgk", "mersis", "ticaret_sicil", "sicil_no"] },
  { key: "iletisim", label: "Telefon ve e-posta", icon: "phone", types: ["telefon", "eposta"] },
  { key: "adres", label: "Adres", icon: "pin", types: ["adres"] },
  { key: "banka", label: "Banka ve kart", icon: "card", types: ["iban", "banka_bilgisi", "kredi_karti"] },
  { key: "tarih", label: "Doğum tarihi", icon: "calendar", types: ["dogum_tarihi"] },
  { key: "gorsel", label: "İmza ve yüz", icon: "pen", types: ["imza", "yuz", "elle"] },
  { key: "ozel", label: "Özel ifadeler", icon: "lock", types: ["ozel_ifade", "ozel_kalip"] },
  { key: "diger", label: "Diğer bilgiler", icon: "tag", types: ["plaka", "ip", "imei", "mac", "sase_no", "gps", "kullanici_adi", "unvan_kurum", "tutar", "musteri_no", "ettn"] },
];

const BY_TYPE = new Map(CATEGORIES.flatMap((c) => c.types.map((ty) => [ty, c] as const)));
const OTHER = CATEGORIES[CATEGORIES.length - 1];

/** Grup adının geçerli dildeki hâli (CATEGORIES etiketleri modül sabitidir; çeviri çizim anında yapılır). */
export function categoryLabel(c: Category): string {
  return t(c.label);
}

export function categoryOf(type: string): Category {
  return BY_TYPE.get(type) ?? OTHER;
}

export interface CategoryGroup {
  category: Category;
  items: PdfFinding[];
  on: number; // maskelenecek olan sayısı
}

/** Bulguları gruplara ayırır (tanımdaki sırayla; bulgusu olmayan grup yok). */
export function groupFindings(findings: PdfFinding[], excluded: Set<string>): CategoryGroup[] {
  return CATEGORIES.map((category) => {
    const items = findings.filter((f) => categoryOf(f.type) === category);
    return { category, items, on: items.filter((f) => !excluded.has(f.id)).length };
  }).filter((g) => g.items.length > 0);
}

/** Seçili yöntemin sade dille anlatımı: "karartılır", "“İstanbul” gibi yazılır"… */
export function methodText(type: string, method: string, dataTypes: DataTypeInfo[]): string {
  if (method === "karartma") return t("karartılır");
  if (method === "bulanik") return t("bulanık dolguyla kapatılır");
  if (method === "takma_ad") return t("takma adla yazılır (Kişi-1…)");
  const info = dataTypes.find((d) => d.key === type);
  const m = info?.methods.find((x) => x.key === method);
  if (method === "etiket") return t("{etiket} yazılır", { etiket: info?.tag ?? "[GIZLI]" });
  if (method === "son4") return t("son 4 hane kalır");
  if (method === "genel" && type === "adres") return t("yalnızca il kalır");
  if (m?.sample) return t("“{ornek}” gibi yazılır", { ornek: m.sample });
  return t("maskelenir");
}

/** Kartın alt satırı: "2 tane · [AD SOYAD] yazılır" ya da "TC, pasaport · 3 tane". */
export function groupText(g: CategoryGroup, dataTypes: DataTypeInfo[], methodOf: (type: string) => string): string {
  const count = g.items.length;
  if (g.on === 0) return t("{n} tane · açık kalacak", { n: count });
  const types = [...new Set(g.items.map((f) => f.type))];
  const partial = g.on < count ? ` · ${t("{on}/{n} maskelenecek", { on: g.on, n: count })}` : "";
  if (types.length === 1) return `${t("{n} tane · {yontem}", { n: count, yontem: methodText(types[0], methodOf(types[0]), dataTypes) })}${partial}`;
  const names = types.map((ty) => shortName(ty, g.items.find((f) => f.type === ty)!.type_label));
  return `${t("{adlar} · {n} tane", { adlar: names.join(", "), n: count })}${partial}`;
}

const SHORT: Record<string, string> = {
  kurum_unvani: "unvan",
  tc_kimlik: "TC",
  vkn: "vergi no",
  vergi_dairesi: "vergi dairesi",
  pasaport: "pasaport",
  ehliyet: "ehliyet",
  sgk: "SGK",
  mersis: "MERSİS",
  ticaret_sicil: "ticaret sicil",
  telefon: "telefon",
  eposta: "e-posta",
  iban: "IBAN",
  banka_bilgisi: "banka",
  kredi_karti: "kart",
  imza: "imza",
  yuz: "yüz",
  elle: "elle seçilen",
  plaka: "plaka",
  ip: "IP",
  tutar: "tutar",
  musteri_no: "müşteri no",
  ettn: "ETTN",
  ozel_ifade: "özel ifade",
  ozel_kalip: "özel kalıp",
};

function shortName(type: string, label: string): string {
  return t(SHORT[type] ?? label);
}
