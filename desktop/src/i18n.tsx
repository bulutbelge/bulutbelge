import { useEffect, useState } from "react";
import en from "./locales/en";

/**
 * Dil desteği.
 *
 * Anahtar, metnin Türkçe hâlidir: t ile çağrılır (örnek: Kaydet metni). Türkçe kaynak dildir, sözlük gerekmez;
 * diğer diller `locales/<kod>/` altında "Türkçe metin → çeviri" sözlüğü olarak tutulur.
 * Sözlükte bulunmayan metin Türkçe görünür (uygulama hiçbir zaman boş metin göstermez).
 * Çeviride çoğul için {n:tekil|çoğul} yazılabilir (ör. İngilizce "{n:finding|findings}"); değer 1 ise tekil seçilir.
 * Değişken: {n} yer tutucusu ikinci parametreyle doldurulur.
 *
 * Yeni dil eklemek: `locales/<kod>/index.ts` yazıp aşağıdaki LANGUAGES ve DICTS'e eklemek.
 * Eksik çeviri denetimi: `npm run i18n:kontrol`.
 */
export type Lang = "tr" | "en";

export const LANGUAGES: { code: Lang; name: string }[] = [
  { code: "tr", name: "Türkçe" },
  { code: "en", name: "English" },
];

const DICTS: Record<Lang, Record<string, string>> = { tr: {}, en };

const KEY = "bulutbelge.lang";
const EVENT = "bulutbelge-lang";

function readLang(): Lang {
  try {
    const v = localStorage.getItem(KEY);
    if (LANGUAGES.some((l) => l.code === v)) return v as Lang;
  } catch {
    // depolama kapalıysa varsayılan dil
  }
  return "tr";
}

let current: Lang = readLang();
if (typeof document !== "undefined") document.documentElement.lang = current;

const KALIP_CACHE: Partial<Record<Lang, { re: RegExp; names: string[]; value: string }[]>> = {};

/** `{ad}` içeren sözlük anahtarları, birebir eşleşme yoksa kalıp olarak denenir (motorun sayı/ad içeren mesajları). */
function kaliplar(lang: Lang) {
  let list = KALIP_CACHE[lang];
  if (!list) {
    list = [];
    for (const [key, value] of Object.entries(DICTS[lang])) {
      if (!/\{\w+\}/.test(key)) continue;
      // Çok kısa kalıplar ("{n} belge") sıradan metinleri yanlış yakalamasın.
      if (key.replace(/\{\w+\}/g, "").trim().length < 10) continue;
      const names: string[] = [];
      const src = key
        .split(/(\{\w+\})/)
        .map((part) => {
          const m = /^\{(\w+)\}$/.exec(part);
          if (m) {
            names.push(m[1]);
            return "([\\s\\S]+?)";
          }
          return part.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
        })
        .join("");
      list.push({ re: new RegExp(`^${src}$`), names, value });
    }
    KALIP_CACHE[lang] = list;
  }
  return list;
}

function doldur(text: string, vars: Record<string, string | number>): string {
  // Çoğul: {n:tekil|çoğul}; değer 1 ise tekil seçilir. Değişken: {n}.
  text = text.replace(/\{(\w+):([^|{}]*)\|([^{}]*)\}/g, (m, name: string, one: string, many: string) =>
    name in vars ? (Number(vars[name]) === 1 ? one : many) : m,
  );
  return text.replace(/\{(\w+)\}/g, (m, name: string) => (name in vars ? String(vars[name]) : m));
}

/**
 * Metni geçerli dile çevirir. Türkçe ya da sözlükte olmayan metin olduğu gibi döner.
 * Motorun ürettiği değişkenli mesajlar (ör. "Belgede 3 görsel var…") için sözlükteki `{n}` kalıpları denenir.
 */
export function t(key: string, vars?: Record<string, string | number>): string {
  const exact = DICTS[current][key];
  if (exact !== undefined) return vars ? doldur(exact, vars) : exact;
  if (current === "tr") return vars ? doldur(key, vars) : key;
  for (const k of kaliplar(current)) {
    const m = k.re.exec(key);
    if (m) {
      const got: Record<string, string> = {};
      // Yakalanan değer virgülle ayrılmış sözlük sözcükleri olabilir (ör. kaçak iletisindeki tür adları).
      k.names.forEach((n, i) => (got[n] = m[i + 1].split(", ").map((p) => DICTS[current][p] ?? p).join(", ")));
      return doldur(k.value, { ...got, ...vars });
    }
  }
  return vars ? doldur(key, vars) : key;
}

/** Tarih ve saat biçimi için geçerli dilin yerel kodu. */
export function localeCode(): string {
  return current === "en" ? "en-GB" : "tr-TR";
}

export function currentLang(): Lang {
  return current;
}

export function setLang(lang: Lang) {
  current = lang;
  try {
    localStorage.setItem(KEY, lang);
  } catch {
    // yok say
  }
  document.documentElement.lang = lang;
  window.dispatchEvent(new Event(EVENT));
}

/** Dil durumu; değişince bileşen yeniden çizilir. */
export function useLang(): [Lang, (l: Lang) => void] {
  const [lang, setState] = useState<Lang>(current);
  useEffect(() => {
    const onChange = () => setState(current);
    window.addEventListener(EVENT, onChange);
    return () => window.removeEventListener(EVENT, onChange);
  }, []);
  return [lang, setLang];
}

/** Bileşenlerde: `const t = useT();`. Dil değişince bileşen yeniden çizilir. */
export function useT() {
  useLang();
  return t;
}
