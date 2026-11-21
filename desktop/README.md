# BulutBelge masaüstü uygulaması

Tauri 2 kabuğu + React (Vite, TypeScript) arayüzü + Python motoru (yan süreç). Tasarım: `docs/mimari/` altındaki PDF, "Masaüstü uygulaması" bölümü.

## Yapı

| Yol | İçerik |
|---|---|
| `src/` | React arayüzü. Motora `engineCall()` (`src/engine.ts`) ile istek gönderir |
| `src-tauri/` | Rust kabuğu. `engine_call` komutu isteği motora iletir (`src/engine.rs`) |
| `engine/` | Python motoru. stdin/stdout üzerinden satır başına bir JSON mesaj |

Motor protokolü:

```
→ {"id": 1, "method": "version", "params": {}}
← {"id": 1, "result": {"engine": "0.1.0", "python": "3.12.10"}}
← {"id": 2, "error": {"code": "unknown_method", "message": "..."}}
```

stdout yalnızca protokol içindir; günlükler stderr'e gider ve belge içeriği ya da orijinal değer içermez. Yeni komut `engine/bulutbelge_engine/protocol.py` içindeki `HANDLERS` tablosuna eklenir. Tespit ve maskeleme `core/` kütüphanesindedir, motor onu çağırır.

| Komut | Ne yapar |
|---|---|
| `rules.types` | Veri türleri ve seçilebilir yöntemler (kural ekranı için) |
| `doc.formats` | Desteklenen uzantılar (PDF, görsel, XML/TXT/CSV) ve OCR'ın hazır olup olmadığı |
| `doc.scan` | `{path, rules}` → biçim, bulgular (sayfa, tür, orijinal, yerine yazılan, güven, PDF/görselde kutular, metinde karakter aralığı), uyarılar, önerilen hedef; metin belgede içerik de döner |
| `doc.mask` | `{source, target, rules, excluded_ids, manual_areas?, make_dirs?}` → maskeli kopyayı kaynakla aynı biçimde yazar; `manual_areas`: önizlemede çizilen alanlar `[{page, rect}]` (PDF ve görsel) |
| `batch.plan` | `{source_dir, target_dir?, recursive?}` → klasördeki desteklenen belgeler ve hedef yolları (dosyalara dokunmaz) |
| `doc.bytes` | `{path}` → Word belgesinin kendisi (base64; arayüz Word gibi çizer, yalnızca bellekte) |
| `doc.slides` | `{path}` → PowerPoint slayt tarifi: kutular, metin, görsel, tablo, notlar (önizleme) |
| `doc.sheets` | `{path}` → Excel sayfaları ve hücre ızgarası (önizleme) |
| `vault.pseudonyms` / `vault.pseudonym_lookup` / `vault.pseudonym_clear` | Takma ad tablosu: türlere göre sayılar, tek bir takma adın gerçek değeri (kasa açıkken), tabloyu silme |
| `doc.text` | `{path}` → XML/TXT/CSV dosyasının içeriği (taramadan önce önizleme, yalnızca bellekte) |
| `doc.page` | `{path, page, width}` → PDF sayfasının ya da görselin önizleme görüntüsü (yalnızca bellekte) |
| `rules.test` | `{rules, text}` → örnek metindeki eşleşmeler (Ayarlar'daki canlı deneme) |
| `settings.get` / `settings.save` | Profiller ve kullanımdaki profil (`settings.json`) |
| `vault.create` / `unlock` / `save` / `change_password` / `lock` / `delete` | Şifreli özel ifade kasası (`terms.bbvault`) |

`doc.mask` orijinal değerleri arayüzden geri almaz: belgeyi aynı kurallarla yeniden tarar, kullanıcının listeden çıkardığı bulguları kimlikleriyle eler.

## PDF akışı

1. **Kaynak:** PDF seçilir.
2. **Hedef:** Varsayılan `<ad>_maskeli.pdf`. Hedef kaynak olamaz, var olan dosyanın üzerine yazılmaz.
3. **Kurallar:** Kullanımdaki profil. Profiller Ayarlar sayfasında düzenlenir: veri türü başına aç/kapat ve yöntem (karartma, etiket, son 4 hane açık), imza ve kaşe etiketleri, özel ifadeler, özel kalıplar (canlı denemeli), beyaz liste.
4. **Tara → Maskele ve kaydet:** Bulgu listesinde istenmeyenin işareti kaldırılır. Maskeleme gerçek silmedir. Ayrıntı: `core/README.md`.

## Gereksinimler (Windows)

- Node.js 20+
- Rust (rustup, `stable-msvc`)
- Visual Studio 2022 Build Tools, "C++ ile masaüstü geliştirme" iş yükü
- Python 3.12+
- WebView2 (Windows 11'de hazır gelir)

## Kurulum (bir kez)

```bash
cd desktop
npm install
python -m venv engine/.venv
engine/.venv/Scripts/python -m pip install -e "../core[dev]" -e "engine[dev]"
```

## Geliştirme

```bash
npm run tauri dev
```

Geliştirme sürümü motoru `engine/.venv` içindeki Python ile doğrudan çalıştırır; motor kodundaki değişiklik uygulamayı yeniden başlatınca geçerli olur. Başka bir Python kullanmak için `BULUTBELGE_PYTHON` ortam değişkenini verin.

Motor testleri:

```bash
cd engine && .venv/Scripts/python -m pytest
```

## Kurulum paketi

```bash
npm run app:build
```

Önce motoru PyInstaller ile klasör (`--onedir`) olarak paketler (`src-tauri/binaries/engine/`, git'e girmez; tek dosyaya göre motorun açılışı 4,3 sn yerine 0,1 sn), sonra MSI ve NSIS kurulumlarını üretir. WebView2 çevrimdışı kurulum olarak pakete gömülür. Kullanıcının Python kurması gerekmez.

## Dil desteği

Arayüz dili Ayarlar'dan seçilir (Türkçe varsayılan, İngilizce). Kaynak dil Türkçedir: metinler `t("Türkçe metin")` ile çağrılır, diğer diller `src/locales/<kod>/` altında "Türkçe metin → çeviri" sözlüğüdür; çevirisi olmayan metin Türkçe görünür. Altyapı: `src/i18n.tsx`.

Yeni dil eklemek: `src/locales/<kod>/index.ts` (İngilizce klasörü örnek) yazılır, `src/i18n.tsx` içindeki `Lang`, `LANGUAGES` ve `DICTS`'e eklenir. Kullanılan her metnin her dilde çevirisi var mı diye bakmak için:

```bash
npm run i18n:kontrol
```

Motorun (Python) ürettiği Türkçe etiket ve uyarılar arayüzde aynı sözlükle çevrilir; maskelenen belge içeriği ve tespit kuralları dilden bağımsızdır.

## Güncelleme denetimi

Uygulama açılışta internet varsa `https://bulutbelge.com/surum.json` dosyasını okur (tek GET, veri göndermez) ve yeni sürüm varsa bilgi şeridi gösterir; indirmeyi kullanıcı yapar. Ayarlar'dan kapatılır. Kod: `src-tauri/src/guncelleme.rs`. Her yayında `site/surum.json` güncellenmelidir. Karar: `docs/kararlar/2026-11-13-dil-destegi-ve-guncelleme-denetimi.md`.

## Ayarlar ve kasa

Ayarlar uygulama veri klasöründe durur (Windows: `%APPDATA%\com.proteksistem.bulutbelge`). Rust kabuğu bu yolu motora `BULUTBELGE_DATA_DIR` ile verir.

- `settings.json`: profiller (kişisel veri içermez, düz metin).
- `terms.bbvault`: özel ifadeler, parolayla şifreli (AES-256-GCM, scrypt). Parola ve anahtar diske yazılmaz; uygulama kapanınca kasa kilitlenir. Parola kurtarılamaz. Karar: `docs/kararlar/2026-11-04-ozel-ifade-sifreli-saklama.md`.

## Kaldırma

NSIS kaldırıcısında "Uygulama verilerini sil" kutusu vardır; MSI ile kaldırmada ayarlar ve işlem günlüğü (`%APPDATA%\com.proteksistem.bulutbelge`) ile WebView2 önbelleği (`%LOCALAPPDATA%\com.proteksistem.bulutbelge`) kalır, elle silinir. Ayrıntı: `docs/kullanici/masaustu.md` bölüm 13.
