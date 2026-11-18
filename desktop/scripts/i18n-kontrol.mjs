// Dil denetimi: kaynakta t("...") ile kullanılan her Türkçe metnin her dilde çevirisi var mı,
// çevirideki {değişken} adları anahtarla uyuşuyor mu. Eksik varsa hata koduyla çıkar.
// Kullanım: npm run i18n:kontrol
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const kok = fileURLToPath(new URL("../src/", import.meta.url));

function dosyalar(dir) {
  return readdirSync(dir, { withFileTypes: true }).flatMap((e) => {
    const yol = join(dir, e.name);
    if (e.isDirectory()) return e.name === "locales" ? [] : dosyalar(yol);
    return /\.(ts|tsx)$/.test(e.name) ? [yol] : [];
  });
}

const STR = String.raw`"(?:[^"\\\n]|\\.)*"`;
const kullanim = new RegExp(String.raw`(?<![\w.$])(?:t|tt)\(\s*(${STR})`, "g");
const cift = new RegExp(String.raw`(${STR})\s*:\s*(${STR})`, "g");

const kullanilan = new Map(); // anahtar -> ilk dosya
for (const d of dosyalar(kok)) {
  const metin = readFileSync(d, "utf8");
  for (const m of metin.matchAll(kullanim)) {
    const anahtar = JSON.parse(m[1]);
    if (!kullanilan.has(anahtar)) kullanilan.set(anahtar, d.replace(kok, "src/"));
  }
}

const degiskenler = (s) => [...s.matchAll(/\{(\w+)(?::[^{}]*)?\}/g)].map((m) => m[1]).filter((v, i, a) => a.indexOf(v) === i).sort().join(",");
let hata = 0;
const diller = readdirSync(join(kok, "locales"), { withFileTypes: true }).filter((e) => e.isDirectory());
for (const dil of diller) {
  const sozluk = new Map();
  for (const f of readdirSync(join(kok, "locales", dil.name))) {
    if (f === "index.ts") continue;
    const metin = readFileSync(join(kok, "locales", dil.name, f), "utf8");
    for (const m of metin.matchAll(cift)) sozluk.set(JSON.parse(m[1]), JSON.parse(m[2]));
  }
  const eksik = [...kullanilan].filter(([k]) => !sozluk.has(k));
  const bozuk = [...sozluk].filter(([k, v]) => degiskenler(k) !== degiskenler(v));
  const kullanilmayan = [...sozluk.keys()].filter((k) => !kullanilan.has(k));
  console.log(`[${dil.name}] kullanılan ${kullanilan.size}, çeviri ${sozluk.size}, eksik ${eksik.length}, değişken uyuşmazlığı ${bozuk.length}, kullanılmayan ${kullanilmayan.length}`);
  for (const [k, d] of eksik) console.log(`  EKSİK (${d}): ${k}`);
  for (const [k, v] of bozuk) console.log(`  DEĞİŞKEN UYUŞMUYOR: ${k} -> ${v}`);
  if (process.argv.includes("--kullanilmayan")) for (const k of kullanilmayan) console.log(`  kullanılmıyor: ${k}`);
  hata += eksik.length + bozuk.length;
}
process.exit(hata ? 1 : 0);
