// İngilizce sözlük: "Türkçe metin" → "English text". Dosya başına bir modül; burada birleştirilir.
import app from "./app";
import ayarlar from "./ayarlar";
import guncelleme from "./guncelleme";
import kurallar from "./kurallar";
import motor from "./motor";
import onizleme from "./onizleme";
import paneller from "./paneller";
import tasarim from "./tasarim";

const en: Record<string, string> = { ...ayarlar, ...guncelleme, ...app, ...tasarim, ...paneller, ...onizleme, ...kurallar, ...motor };

export default en;
